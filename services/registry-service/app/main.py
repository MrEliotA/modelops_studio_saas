from __future__ import annotations
from fastapi import APIRouter, Request
import asyncpg
from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError
from mlops_common.nats_client import connect as nats_connect, ensure_streams, publish
import os

# Optional MLflow integration
try:
    import mlflow
    from mlflow.tracking import MlflowClient
except Exception:  # pragma: no cover
    mlflow = None
    MlflowClient = None

app = create_app("registry-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")

@app.on_event("startup")
async def _startup_nats():
    nc = await nats_connect()
    app.state.nats = nc
    app.state.js = nc.jetstream()
    await ensure_streams(app.state.js)

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if tracking_uri and MlflowClient:
        mlflow.set_tracking_uri(tracking_uri)
        app.state.mlflow = MlflowClient(tracking_uri=tracking_uri)
    else:
        app.state.mlflow = None

@app.on_event("shutdown")
async def _shutdown_nats():
    nc = getattr(app.state, "nats", None)
    if nc:
        await nc.drain()

def _scoped_model_name(tenant_id: str, project_id: str, name: str) -> str:
    # Avoid collisions across tenants/projects
    return f"{tenant_id}.{project_id}.{name}"

@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}

# --- Models ---
@router.post("/models", status_code=201)
async def create_model(request: Request, payload: dict):
    t = request.state.tenancy
    name = payload.get("name")
    if not name:
        raise ApiError("BadRequest", "Missing name", 400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO models(tenant_id, project_id, name, description, created_by)
                   VALUES ($1,$2,$3,$4,$5)
                   RETURNING id, name, description, created_by, created_at, updated_at""",
                t.tenant_id, t.project_id, name, payload.get("description"), t.user_id
            )
        except asyncpg.UniqueViolationError:
            raise ApiError("Conflict", "Model name already exists.", 409)

    # Optional: ensure MLflow registered model exists
    client = request.app.state.mlflow
    if client:
        scoped = _scoped_model_name(str(t.tenant_id), str(t.project_id), name)
        try:
            client.create_registered_model(scoped)
        except Exception:
            # ignore if exists
            pass

    return dict(row)

@router.get("/models")
async def list_models(request: Request):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, name, description, created_by, created_at, updated_at
               FROM models WHERE tenant_id=$1 AND project_id=$2 ORDER BY created_at DESC""",
            t.tenant_id, t.project_id
        )
    return {"items":[dict(r) for r in rows]}

@router.get("/models/{model_id}")
async def get_model(request: Request, model_id: str):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, name, description, created_by, created_at, updated_at
               FROM models WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id, t.project_id, model_id
        )
    if not row:
        raise ApiError("NotFound", "Model not found", 404)
    return dict(row)

# --- Versions ---
@router.post("/models/{model_id}/versions", status_code=201)
async def create_model_version(request: Request, model_id: str, payload: dict):
    t = request.state.tenancy
    artifact_uri = payload.get("artifact_uri")
    if not artifact_uri:
        raise ApiError("BadRequest", "Missing artifact_uri", 400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        # Ensure model exists
        model = await conn.fetchrow(
            """SELECT id, name FROM models WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id, t.project_id, model_id
        )
        if not model:
            raise ApiError("NotFound", "Model not found", 404)

        # Next version number
        last = await conn.fetchrow("""SELECT COALESCE(MAX(version),0) AS v FROM model_versions WHERE model_id=$1""", model_id)
        next_v = int(last["v"]) + 1

        row = await conn.fetchrow(
            """INSERT INTO model_versions(tenant_id, project_id, model_id, version, artifact_uri, source_run_id, metrics, stage, created_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
               RETURNING id, model_id, version, artifact_uri, source_run_id, metrics, stage, created_by, created_at, updated_at""",
            t.tenant_id, t.project_id, model_id, next_v, artifact_uri, payload.get("source_run_id"),
            payload.get("metrics", {}), payload.get("stage"), t.user_id
        )

    # Optional MLflow registration
    client = request.app.state.mlflow
    if client:
        scoped = _scoped_model_name(str(t.tenant_id), str(t.project_id), model["name"])
        # We don't have a real MLflow run artifact in this demo; we still register the uri for traceability
        try:
            # MLflow expects model uri like "runs:/<run_id>/model"; in on-prem we might use custom.
            # Here we store only internal DB; MLflow integration is optional and may be extended later.
            pass
        except Exception:
            pass

    return dict(row)

@router.get("/models/{model_id}/versions")
async def list_versions(request: Request, model_id: str):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, version, artifact_uri, source_run_id, metrics, stage, created_by, created_at, updated_at
               FROM model_versions
               WHERE tenant_id=$1 AND project_id=$2 AND model_id=$3
               ORDER BY version DESC""",
            t.tenant_id, t.project_id, model_id
        )
    return {"items":[dict(r) for r in rows]}

# --- Endpoints (deployment intent) ---
@router.post("/endpoints", status_code=201)
async def create_endpoint(request: Request, payload: dict):
    t = request.state.tenancy
    name = payload.get("name")
    if not name:
        raise ApiError("BadRequest", "Missing name", 400)

    runtime = payload.get("runtime", "kserve")
    traffic = payload.get("traffic", {})
    autoscaling = payload.get("autoscaling", {})
    runtime_config = payload.get("runtime_config", {})

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO endpoints(
                      tenant_id, project_id, name, status, url, runtime,
                      model_id, model_version_id, traffic, autoscaling, runtime_config,
                      created_by
                   )
                   VALUES ($1,$2,$3,'CREATING',NULL,$4,$5,$6,$7,$8,$9,$10)
                   RETURNING id, name, status, url, runtime, model_id, model_version_id,
                             traffic, autoscaling, runtime_config, created_by, created_at, updated_at""",
                t.tenant_id, t.project_id, name,
                runtime,
                payload.get("model_id"), payload.get("model_version_id"),
                traffic, autoscaling, runtime_config,
                t.user_id
            )
        except asyncpg.UniqueViolationError:
            raise ApiError("Conflict", "Endpoint name already exists.", 409)

    ep = dict(row)
    await publish(request.app.state.js, "mlops.serving.deploy_requested", {
        "tenant_id": str(t.tenant_id),
        "project_id": str(t.project_id),
        "endpoint_id": str(ep["id"]),
        "name": ep["name"],
        "model_id": ep.get("model_id"),
        "model_version_id": ep.get("model_version_id"),
    })
    return ep


@router.patch("/endpoints/{endpoint_id}")
async def patch_endpoint(request: Request, endpoint_id: str, payload: dict):
    """Patch an endpoint and trigger a redeploy if serving-relevant fields change.

    Supported fields:
      - model_version_id
      - traffic (e.g., {"canaryTrafficPercent": 10})
      - autoscaling
      - runtime
      - runtime_config
      - status (optional; typically managed by deploy-worker)
    """
    t = request.state.tenancy
    pool = request.app.state.db_pool

    allowed = {"model_version_id", "traffic", "autoscaling", "runtime", "runtime_config", "status"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise ApiError("BadRequest", "No valid fields to update", 400)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, name, model_id, model_version_id, traffic, autoscaling, runtime, runtime_config
               FROM endpoints
               WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id, t.project_id, endpoint_id
        )
        if not row:
            raise ApiError("NotFound", "Endpoint not found", 404)

        before = dict(row)

        set_parts = []
        args = [t.tenant_id, t.project_id, endpoint_id]
        idx = 4
        for k, v in updates.items():
            set_parts.append(f"{k}=${idx}")
            args.append(v)
            idx += 1
        set_sql = ", ".join(set_parts)

        await conn.execute(
            f"UPDATE endpoints SET {set_sql}, updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND id=$3::uuid",
            *args
        )

        after = await conn.fetchrow(
            """SELECT id, name, status, url, runtime, model_id, model_version_id,
                      traffic, autoscaling, runtime_config, created_by, created_at, updated_at
               FROM endpoints
               WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id, t.project_id, endpoint_id
        )

    changed_serving = any(
        k in updates and updates.get(k) != before.get(k)
        for k in ("model_version_id", "traffic", "autoscaling", "runtime", "runtime_config")
    )

    if changed_serving:
        await publish(request.app.state.js, "mlops.serving.deploy_requested", {
            "tenant_id": str(t.tenant_id),
            "project_id": str(t.project_id),
            "endpoint_id": str(endpoint_id),
            "name": before["name"],
            "model_id": str(before.get("model_id")) if before.get("model_id") else None,
            "model_version_id": str((updates.get("model_version_id") or before.get("model_version_id"))) if (updates.get("model_version_id") or before.get("model_version_id")) else None,
        })

    return dict(after)


@router.get("/endpoints")
async def list_endpoints(request: Request):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, name, status, url, runtime, model_id, model_version_id,
                      traffic, autoscaling, runtime_config,
                      created_by, created_at, updated_at
               FROM endpoints WHERE tenant_id=$1 AND project_id=$2 ORDER BY created_at DESC""",
            t.tenant_id, t.project_id
        )
    return {"items":[dict(r) for r in rows]}


@router.get("/endpoints/{endpoint_id}")
async def get_endpoint(request: Request, endpoint_id: str):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, name, status, url, runtime, model_id, model_version_id,
                      traffic, autoscaling, runtime_config,
                      created_by, created_at, updated_at
               FROM endpoints WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id, t.project_id, endpoint_id
        )
    if not row:
        raise ApiError("NotFound", "Endpoint not found", 404)
    return dict(row)

app.include_router(router)
