from __future__ import annotations

import os
from fastapi import APIRouter, Request
import asyncpg

from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError
from mlops_common.nats_client import connect as nats_connect, ensure_streams, publish


app = create_app("deployment-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")


@app.on_event("startup")
async def _startup_nats():
    nc = await nats_connect()
    app.state.nats = nc
    app.state.js = nc.jetstream()
    await ensure_streams(app.state.js)


@app.on_event("shutdown")
async def _shutdown_nats():
    nc = getattr(app.state, "nats", None)
    if nc:
        await nc.drain()


@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True, "service": "deployment-service"}


def _deployment_select_sql(where_extra: str = "") -> str:
    # Keep columns stable for the API.
    return (
        "SELECT id, name, status, url, runtime, model_id, model_version_id, "
        "traffic, autoscaling, runtime_config, created_by, created_at, updated_at "
        "FROM endpoints "
        + where_extra
    )


@router.post("/deployments", status_code=201)
async def create_deployment(request: Request, payload: dict):
    """Create a deployment intent (maps to endpoints table).

    This service is the canonical API for deployment lifecycle. The deploy-worker
    consumes `mlops.serving.deploy_requested` and updates endpoint status.
    """
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
                """
                INSERT INTO endpoints(
                    tenant_id, project_id, name, status, url, runtime,
                    model_id, model_version_id, traffic, autoscaling, runtime_config,
                    created_by
                )
                VALUES ($1,$2,$3,'CREATING',NULL,$4,$5,$6,$7,$8,$9,$10)
                RETURNING id, name, status, url, runtime, model_id, model_version_id,
                          traffic, autoscaling, runtime_config, created_by, created_at, updated_at
                """,
                t.tenant_id,
                t.project_id,
                name,
                runtime,
                payload.get("model_id"),
                payload.get("model_version_id"),
                traffic,
                autoscaling,
                runtime_config,
                t.user_id,
            )
        except asyncpg.UniqueViolationError:
            raise ApiError("Conflict", "Deployment name already exists.", 409)

    dep = dict(row)

    # Trigger async deploy.
    await publish(
        request.app.state.js,
        "mlops.serving.deploy_requested",
        {
            "tenant_id": str(t.tenant_id),
            "project_id": str(t.project_id),
            "endpoint_id": str(dep["id"]),
            "name": dep["name"],
            "model_id": str(dep.get("model_id")) if dep.get("model_id") else None,
            "model_version_id": str(dep.get("model_version_id")) if dep.get("model_version_id") else None,
        },
    )

    return dep


@router.get("/deployments")
async def list_deployments(request: Request, limit: int = 50, include_deleted: bool = False):
    t = request.state.tenancy
    limit = max(1, min(200, int(limit)))

    where = "WHERE tenant_id=$1 AND project_id=$2"
    if not include_deleted:
        where += " AND status <> 'DELETED'"

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _deployment_select_sql(f"{where} ORDER BY created_at DESC LIMIT $3"),
            t.tenant_id,
            t.project_id,
            limit,
        )
    return {"items": [dict(r) for r in rows]}


@router.get("/deployments/{deployment_id}")
async def get_deployment(request: Request, deployment_id: str):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            _deployment_select_sql("WHERE tenant_id=$1 AND project_id=$2 AND id=$3"),
            t.tenant_id,
            t.project_id,
            deployment_id,
        )
    if not row:
        raise ApiError("NotFound", "Deployment not found", 404)
    return dict(row)


@router.put("/deployments/{deployment_id}")
async def update_deployment(request: Request, deployment_id: str, payload: dict):
    """Update a deployment intent.

    We allow partial updates (client-friendly). If serving-relevant fields change,
    the service publishes a deploy_requested event.
    """
    t = request.state.tenancy
    pool = request.app.state.db_pool

    allowed = {"name", "model_id", "model_version_id", "traffic", "autoscaling", "runtime", "runtime_config", "status", "url"}
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise ApiError("BadRequest", "No valid fields to update", 400)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name, status, url, runtime, model_id, model_version_id,
                   traffic, autoscaling, runtime_config
            FROM endpoints
            WHERE tenant_id=$1 AND project_id=$2 AND id=$3
            """,
            t.tenant_id,
            t.project_id,
            deployment_id,
        )
        if not row:
            raise ApiError("NotFound", "Deployment not found", 404)

        before = dict(row)

        set_parts = []
        args = [t.tenant_id, t.project_id, deployment_id]
        idx = 4
        for k, v in updates.items():
            set_parts.append(f"{k}=${idx}")
            args.append(v)
            idx += 1

        set_sql = ", ".join(set_parts)
        try:
            await conn.execute(
                f"UPDATE endpoints SET {set_sql}, updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND id=$3::uuid",
                *args,
            )
        except asyncpg.UniqueViolationError:
            raise ApiError("Conflict", "Deployment name already exists.", 409)

        after = await conn.fetchrow(
            _deployment_select_sql("WHERE tenant_id=$1 AND project_id=$2 AND id=$3"),
            t.tenant_id,
            t.project_id,
            deployment_id,
        )

    changed_serving = any(
        k in updates and updates.get(k) != before.get(k)
        for k in ("model_version_id", "traffic", "autoscaling", "runtime", "runtime_config")
    )

    if changed_serving:
        await publish(
            request.app.state.js,
            "mlops.serving.deploy_requested",
            {
                "tenant_id": str(t.tenant_id),
                "project_id": str(t.project_id),
                "endpoint_id": str(deployment_id),
                "name": (updates.get("name") or before.get("name")),
                "model_id": str((updates.get("model_id") or before.get("model_id"))) if (updates.get("model_id") or before.get("model_id")) else None,
                "model_version_id": str((updates.get("model_version_id") or before.get("model_version_id"))) if (updates.get("model_version_id") or before.get("model_version_id")) else None,
            },
        )

    return dict(after)


@router.delete("/deployments/{deployment_id}")
async def delete_deployment(request: Request, deployment_id: str):
    """Delete a deployment.

    We soft-delete by:
      1) marking status=DELETING
      2) publishing mlops.serving.delete_requested
      3) renaming the endpoint to free the UNIQUE(name) constraint, then setting status=DELETED
    """
    t = request.state.tenancy
    pool = request.app.state.db_pool

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name, status
            FROM endpoints
            WHERE tenant_id=$1 AND project_id=$2 AND id=$3
            """,
            t.tenant_id,
            t.project_id,
            deployment_id,
        )
        if not row:
            raise ApiError("NotFound", "Deployment not found", 404)

        name = str(row["name"])
        deleted_name = f"{name}.deleted.{str(deployment_id)[:8]}"

        await conn.execute(
            "UPDATE endpoints SET status='DELETING', updated_at=now() WHERE tenant_id=$1 AND project_id=$2 AND id=$3::uuid",
            t.tenant_id,
            t.project_id,
            deployment_id,
        )

        # Publish best-effort delete event (k8s mode can clean up runtime resources).
        await publish(
            request.app.state.js,
            "mlops.serving.delete_requested",
            {
                "tenant_id": str(t.tenant_id),
                "project_id": str(t.project_id),
                "endpoint_id": str(deployment_id),
                "name": name,
            },
        )

        await conn.execute(
            """
            UPDATE endpoints
            SET status='DELETED', url=NULL, name=$4, updated_at=now()
            WHERE tenant_id=$1 AND project_id=$2 AND id=$3::uuid
            """,
            t.tenant_id,
            t.project_id,
            deployment_id,
            deleted_name,
        )

    return {"ok": True}


app.include_router(router)
