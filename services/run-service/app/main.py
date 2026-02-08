from __future__ import annotations
from fastapi import APIRouter, Request
import asyncpg
from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError
from mlops_common.nats_client import connect as nats_connect, ensure_streams, publish

app = create_app("run-service", enable_idempotency=True)
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
    return {"ok": True}

@router.post("/runs", status_code=201)
async def create_run(request: Request, payload: dict):
    t = request.state.tenancy
    template_id = payload.get("template_id")
    if not template_id:
        raise ApiError("BadRequest", "Missing template_id", 400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO runs(tenant_id, project_id, template_id, status, parameters, compute_profile, created_by)
               VALUES ($1,$2,$3,'QUEUED',$4,$5,$6)
               RETURNING id, template_id, status, parameters, compute_profile, created_by, created_at, updated_at""",
            t.tenant_id, t.project_id, template_id, payload.get("parameters", {}), payload.get("compute_profile"), t.user_id
        )

    run = dict(row)
    # Publish event for workers
    await publish(request.app.state.js, "mlops.runs.requested", {
        "tenant_id": str(t.tenant_id),
        "project_id": str(t.project_id),
        "run_id": str(run["id"]),
        "template_id": str(template_id),
        "compute_profile": run.get("compute_profile"),
        "parameters": run.get("parameters", {}),
        "requested_by": t.user_id,
        "requested_at": run["created_at"].isoformat(),
    })
    return run

@router.get("/runs")
async def list_runs(request: Request):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, template_id, status, parameters, compute_profile, kfp_run_id, created_by, created_at, updated_at
               FROM runs WHERE tenant_id=$1 AND project_id=$2 ORDER BY created_at DESC""",
            t.tenant_id, t.project_id
        )
    return {"items":[dict(r) for r in rows]}

@router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: str):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, template_id, status, parameters, compute_profile, kfp_run_id, created_by, created_at, updated_at
               FROM runs WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id, t.project_id, run_id
        )
    if not row:
        raise ApiError("NotFound", "Run not found", 404)
    return dict(row)

app.include_router(router)
