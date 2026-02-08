from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path

import yaml

import asyncpg
from fastapi import APIRouter, Request
from fastapi.responses import Response

from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError

app = create_app("template-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")

# Built-in YAML-only catalog (mounted in the service image)
_CATALOG_ROOT = (Path(__file__).resolve().parent.parent / "catalog").resolve()


# Template mode:
# - db: templates are managed via API + stored in DB
# - catalog: templates are read-only and seeded from services/template-service/catalog/catalog.yaml
TEMPLATE_MODE = os.getenv("TEMPLATE_MODE", "db").strip().lower()
_CATALOG_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "mlops-saas:template-catalog:v2")


def _read_catalog_index() -> dict:
    idx_path = (_CATALOG_ROOT / "catalog.yaml").resolve()
    if not idx_path.exists():
        return {"templates": []}
    data = yaml.safe_load(idx_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {"templates": []}
    data.setdefault("templates", [])
    return data


async def _seed_catalog(conn: asyncpg.Connection, tenant_id: str, project_id: str, created_by: str) -> None:
    """Upsert built-in templates into the DB for the given tenant/project.

    This keeps the REST API contract stable (template_id remains a DB UUID), while ensuring the
    platform is "YAML-only" for supply-chain safety.
    """
    idx = _read_catalog_index()
    templates = idx.get("templates") or []
    if not isinstance(templates, list) or not templates:
        return

    git_ref = str(idx.get("version") or "v2")
    default_compiler = str(idx.get("compiler") or "kfp-yaml")

    for t in templates:
        if not isinstance(t, dict):
            continue
        key = str(t.get("key") or "").strip()
        name = str(t.get("name") or key).strip()
        if not key or not name:
            continue

        rel_entry = str(t.get("entrypoint") or "").lstrip("/")
        entrypoint = f"catalog://{rel_entry}"
        compiler = str(t.get("compiler") or default_compiler)
        description = t.get("description")

        default_params = dict(t.get("default_parameters") or {})

        # Auto-inject tenancy context so pipelines can call internal APIs without manual headers.
        default_params.setdefault("tenant_id", str(tenant_id))
        default_params.setdefault("project_id", str(project_id))
        default_params.setdefault("user_id", str(created_by))

        template_id = uuid.uuid5(_CATALOG_NAMESPACE, f"{tenant_id}:{project_id}:{key}")

        await conn.execute(
            """INSERT INTO templates(id, tenant_id, project_id, name, description, git_repo, git_ref, entrypoint, compiler, default_parameters, created_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
               ON CONFLICT (tenant_id, project_id, name)
               DO UPDATE SET description=EXCLUDED.description,
                             git_repo=EXCLUDED.git_repo,
                             git_ref=EXCLUDED.git_ref,
                             entrypoint=EXCLUDED.entrypoint,
                             compiler=EXCLUDED.compiler,
                             default_parameters=EXCLUDED.default_parameters,
                             updated_at=now()""",
            str(template_id),
            tenant_id,
            project_id,
            name,
            description,
            "catalog",
            git_ref,
            entrypoint,
            compiler,
            default_params,
            created_by,
        )



def _load_catalog_entry(rel_path: str) -> str:
    # Prevent path traversal.
    p = (_CATALOG_ROOT / rel_path).resolve()
    if not str(p).startswith(str(_CATALOG_ROOT)):
        raise ApiError("BadRequest", "Invalid catalog entrypoint", 400)
    if not p.exists() or not p.is_file():
        raise ApiError("NotFound", f"Catalog template not found: {rel_path}", 404)
    return p.read_text(encoding="utf-8")


def _load_pipeline_package(entrypoint: str) -> str:
    ep = (entrypoint or "").strip()

    # catalog://pipelines/hello-world.yaml
    if ep.startswith("catalog://"):
        rel = ep[len("catalog://") :].lstrip("/")
        return _load_catalog_entry(rel)

    # inline://<base64-encoded-yaml>
    if ep.startswith("inline://"):
        b64 = ep[len("inline://") :]
        try:
            raw = base64.b64decode(b64.encode("utf-8"), validate=False)
            return raw.decode("utf-8")
        except Exception:
            raise ApiError("BadRequest", "Invalid inline pipeline package (base64)", 400)

    # For v2, only YAML-only sources are supported.
    raise ApiError(
        "BadRequest",
        "Unsupported entrypoint. Use catalog://... or inline://<base64-yaml>.",
        400,
    )


@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}


@router.post("/templates", status_code=201)
async def create_template(request: Request, payload: dict):
    t = request.state.tenancy
    if TEMPLATE_MODE == "catalog":
        raise ApiError("Forbidden", "Catalog mode: templates are read-only.", 403)
    for k in ["name", "git_repo", "git_ref", "entrypoint", "compiler"]:
        if not payload.get(k):
            raise ApiError("BadRequest", f"Missing field: {k}", 400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO templates(tenant_id, project_id, name, description, git_repo, git_ref, entrypoint, compiler, default_parameters, created_by)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                    RETURNING id, name, description, git_repo, git_ref, entrypoint, compiler, default_parameters, created_by, created_at, updated_at""",
                t.tenant_id,
                t.project_id,
                payload["name"],
                payload.get("description"),
                payload["git_repo"],
                payload["git_ref"],
                payload["entrypoint"],
                payload["compiler"],
                payload.get("default_parameters", {}),
                t.user_id,
            )
        except asyncpg.UniqueViolationError:
            raise ApiError("Conflict", "Template name already exists in this tenant/project.", 409)
    return dict(row)


@router.get("/templates")
async def list_templates(request: Request):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        if TEMPLATE_MODE == "catalog":
            await _seed_catalog(conn, str(t.tenant_id), str(t.project_id), t.user_id)
        rows = await conn.fetch(
            """SELECT id, name, description, git_repo, git_ref, entrypoint, compiler, default_parameters, created_by, created_at, updated_at
               FROM templates WHERE tenant_id=$1 AND project_id=$2 ORDER BY created_at DESC""",
            t.tenant_id,
            t.project_id,
        )
    return {"items": [dict(r) for r in rows]}


@router.get("/templates/{template_id}")
async def get_template(request: Request, template_id: str):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        if TEMPLATE_MODE == "catalog":
            await _seed_catalog(conn, str(t.tenant_id), str(t.project_id), t.user_id)
        row = await conn.fetchrow(
            """SELECT id, name, description, git_repo, git_ref, entrypoint, compiler, default_parameters, created_by, created_at, updated_at
               FROM templates WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id,
            t.project_id,
            template_id,
        )
    if not row:
        raise ApiError("NotFound", "Template not found", 404)
    return dict(row)


@router.get("/templates/{template_id}/package")
async def get_template_package(request: Request, template_id: str):
    """Return a YAML-only pipeline package.

    v2 security goal: run-orchestrator must not git-clone or compile user code.
    Only YAML sources are allowed:
      - catalog://... (bundled with template-service image)
      - inline://<base64-yaml>
    """
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        if TEMPLATE_MODE == "catalog":
            await _seed_catalog(conn, str(t.tenant_id), str(t.project_id), t.user_id)
        row = await conn.fetchrow(
            """SELECT id, entrypoint, compiler
               FROM templates WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id,
            t.project_id,
            template_id,
        )

    if not row:
        raise ApiError("NotFound", "Template not found", 404)

    compiler = str(row["compiler"] or "")
    if not compiler.lower().startswith("kfp"):
        raise ApiError("BadRequest", f"Unsupported template compiler for YAML-only mode: {compiler}", 400)

    yaml_text = _load_pipeline_package(str(row["entrypoint"]))
    return Response(content=yaml_text, media_type="application/yaml")


@router.put("/templates/{template_id}")
async def update_template(request: Request, template_id: str, payload: dict):
    """Update a template.

    This endpoint is intentionally forgiving ("PUT" semantics but partial updates are allowed)
    to keep clients simple.

    Updatable fields:
      - name
      - description
      - git_repo
      - git_ref
      - entrypoint
      - compiler
      - default_parameters
    """
    t = request.state.tenancy

    if TEMPLATE_MODE == "catalog":
        raise ApiError("Forbidden", "Catalog mode: templates are read-only.", 403)

    allowed = {"name", "description", "git_repo", "git_ref", "entrypoint", "compiler", "default_parameters"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise ApiError("BadRequest", "No valid fields to update", 400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        exists = await conn.fetchrow(
            """SELECT id FROM templates WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id,
            t.project_id,
            template_id,
        )
        if not exists:
            raise ApiError("NotFound", "Template not found", 404)

        set_parts = []
        args = [t.tenant_id, t.project_id, template_id]
        idx = 4
        for k, v in updates.items():
            set_parts.append(f"{k}=${idx}")
            args.append(v)
            idx += 1

        set_sql = ", ".join(set_parts)
        try:
            await conn.execute(
                f"UPDATE templates SET {set_sql}, updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND id=$3::uuid",
                *args,
            )
        except asyncpg.UniqueViolationError:
            raise ApiError("Conflict", "Template name already exists in this tenant/project.", 409)

        row = await conn.fetchrow(
            """SELECT id, name, description, git_repo, git_ref, entrypoint, compiler, default_parameters,
                      created_by, created_at, updated_at
               FROM templates WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id,
            t.project_id,
            template_id,
        )
    return dict(row)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(request: Request, template_id: str):
    t = request.state.tenancy
    if TEMPLATE_MODE == "catalog":
        raise ApiError("Forbidden", "Catalog mode: templates are read-only.", 403)
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        res = await conn.execute(
            "DELETE FROM templates WHERE tenant_id=$1 AND project_id=$2 AND id=$3::uuid",
            t.tenant_id,
            t.project_id,
            template_id,
        )

    # asyncpg returns strings like "DELETE 1"
    if not str(res).endswith(" 1"):
        raise ApiError("NotFound", "Template not found", 404)
    return None


app.include_router(router)
