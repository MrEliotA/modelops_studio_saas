from __future__ import annotations

from fastapi import APIRouter, Request

from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError
from mlops_common.nats_client import connect as nats_connect, ensure_streams, publish

DEFAULT_POLICY = {
    "plan": "free",
    "t4_max_concurrency": 1,
    "mig_max_concurrency": 0,
    "max_queued_jobs": 50,
    "priority_boost": 0,
}


async def _ensure_policy(conn, tenant_id: str) -> dict:
    row = await conn.fetchrow(
        "SELECT tenant_id, plan, t4_max_concurrency, mig_max_concurrency, max_queued_jobs, priority_boost "
        "FROM tenant_gpu_policies WHERE tenant_id=$1",
        tenant_id,
    )
    if row:
        return dict(row)
    await conn.execute(
        "INSERT INTO tenant_gpu_policies(tenant_id) VALUES ($1) ON CONFLICT DO NOTHING",
        tenant_id,
    )
    return DEFAULT_POLICY.copy()


app = create_app("gpu-jobs-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")


@app.on_event("startup")
async def _startup():
    nc = await nats_connect()
    app.state.nats = nc
    app.state.js = nc.jetstream()
    await ensure_streams(app.state.js)


@app.on_event("shutdown")
async def _shutdown():
    nc = getattr(app.state, "nats", None)
    if nc:
        await nc.drain()


@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True, "service": "gpu-jobs-service"}


@router.post("/gpu-jobs", status_code=201)
async def create_job(request: Request, payload: dict):
    t = request.state.tenancy

    target_url = payload.get("target_url")
    req_json = payload.get("request_json")
    if not target_url or not isinstance(req_json, dict):
        raise ApiError("BadRequest", "target_url and request_json are required", 400)

    gpu_pool_requested = (payload.get("gpu_pool_requested") or "t4").lower().strip()  # t4|mig|auto
    isolation = (payload.get("isolation_level") or "shared").lower().strip()  # shared|exclusive

    # Backward-compatible alias: 'isolated' -> 'exclusive'
    if isolation in ("isolated", "exclusive"):
        isolation = "exclusive"
    elif isolation != "shared":
        raise ApiError("BadRequest", "isolation_level must be shared or exclusive", 400)

    priority = int(payload.get("priority") or 0)

    if gpu_pool_requested not in ("t4", "mig", "auto"):
        raise ApiError("BadRequest", "gpu_pool_requested must be t4, mig, or auto", 400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        policy = await _ensure_policy(conn, str(t.tenant_id))

        queued_count = await conn.fetchval(
            "SELECT COUNT(1) FROM gpu_jobs WHERE tenant_id=$1 AND status IN ('QUEUED','DISPATCHED')",
            t.tenant_id,
        )
        if queued_count >= int(policy.get("max_queued_jobs", 50)):
            raise ApiError("TooManyRequests", "GPU queue limit exceeded for tenant", 429)

        effective_priority = priority + int(policy.get("priority_boost", 0))

        row = await conn.fetchrow(
            """
            INSERT INTO gpu_jobs(
              tenant_id, project_id, status,
              gpu_pool_requested, target_url, request_json,
              isolation_level, priority, created_by
            )
            VALUES ($1,$2,'QUEUED',$3,$4,$5,$6,$7,$8)
            RETURNING id, status, gpu_pool_requested, isolation_level, priority,
                      target_url, request_json, requested_at, updated_at
            """,
            t.tenant_id,
            t.project_id,
            gpu_pool_requested,
            target_url,
            req_json,
            isolation,
            effective_priority,
            t.user_id,
        )

    job = dict(row)

    await publish(
        request.app.state.js,
        "mlops.gpu.jobs.enqueued",
        {
            "tenant_id": str(t.tenant_id),
            "project_id": str(t.project_id),
            "job_id": str(job["id"]),
            "gpu_pool_requested": job["gpu_pool_requested"],
            "isolation_level": job["isolation_level"],
            "priority": job["priority"],
        },
    )
    return job


@router.get("/gpu-jobs")
async def list_jobs(request: Request, limit: int = 50):
    t = request.state.tenancy
    limit = max(1, min(200, int(limit)))
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, status, gpu_pool_requested, gpu_pool_assigned,
                   isolation_level, target_url,
                   requested_at, started_at, finished_at, updated_at
            FROM gpu_jobs
            WHERE tenant_id=$1 AND project_id=$2
            ORDER BY requested_at DESC
            LIMIT $3
            """,
            t.tenant_id,
            t.project_id,
            limit,
        )
    return {"items": [dict(r) for r in rows]}


@router.get("/gpu-jobs/{job_id}")
async def get_job(request: Request, job_id: str):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, status, gpu_pool_requested, gpu_pool_assigned,
                   isolation_level, priority, target_url, request_json,
                   response_json, error, requested_at, dispatched_at,
                   started_at, finished_at, updated_at
            FROM gpu_jobs
            WHERE tenant_id=$1 AND project_id=$2 AND id=$3
            """,
            t.tenant_id,
            t.project_id,
            job_id,
        )
    if not row:
        raise ApiError("NotFound", "GPU job not found", 404)
    return dict(row)


app.include_router(router)
