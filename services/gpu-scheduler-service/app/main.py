from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import structlog
from fastapi import APIRouter

from mlops_common.app_factory import create_app
from mlops_common.nats_client import connect as nats_connect, ensure_streams, publish

log = structlog.get_logger("gpu-scheduler")

LOCK_KEY = 912345678  # Stable advisory lock key
DEFAULT_POLICY = {
    "plan": "free",
    "t4_max_concurrency": 1,
    "mig_max_concurrency": 0,
    "max_queued_jobs": 50,
    "priority_boost": 0,
}


def _t4_shared_slots() -> int:
    # Total concurrent shared slots for the cluster (matches T4 time-slicing replicas).
    return int(os.getenv("T4_SHARED_SLOTS", os.getenv("T4_TOTAL_SLOTS", "8")))


def _t4_exclusive_slots() -> int:
    # Total concurrent exclusive slots for the cluster (usually 1).
    return int(os.getenv("T4_EXCLUSIVE_SLOTS", "1"))


def _mig_slots() -> int:
    # Total concurrent MIG slots (sum of available MIG partitions you allow).
    return int(os.getenv("MIG_TOTAL_SLOTS", "0"))


async def _ensure_policy(conn, tenant_id: str) -> dict:
    row = await conn.fetchrow(
        "SELECT tenant_id, plan, t4_max_concurrency, mig_max_concurrency, max_queued_jobs, priority_boost "
        "FROM tenant_gpu_policies WHERE tenant_id=$1",
        tenant_id,
    )
    if row:
        return dict(row)
    await conn.execute("INSERT INTO tenant_gpu_policies(tenant_id) VALUES ($1) ON CONFLICT DO NOTHING", tenant_id)
    return DEFAULT_POLICY.copy()


async def _try_lock(conn: asyncpg.Connection) -> bool:
    v = await conn.fetchval("SELECT pg_try_advisory_lock($1)", LOCK_KEY)
    return bool(v)


async def _unlock(conn: asyncpg.Connection) -> None:
    await conn.execute("SELECT pg_advisory_unlock($1)", LOCK_KEY)


async def _inflight_counts_per_tenant(pool: asyncpg.Pool, pool_name: str, isolation: str | None = None) -> dict[str, int]:
    # Count RUNNING + DISPATCHED as "in-flight" to avoid over-dispatch.
    async with pool.acquire() as conn:
        if isolation:
            rows = await conn.fetch(
                """
                SELECT tenant_id::text AS tenant_id, COUNT(1) AS cnt
                FROM gpu_jobs
                WHERE status IN ('RUNNING','DISPATCHED')
                  AND gpu_pool_assigned=$1
                  AND (isolation_level=$2 OR (isolation_level='isolated' AND $2='exclusive'))
                GROUP BY tenant_id
                """,
                pool_name,
                isolation,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT tenant_id::text AS tenant_id, COUNT(1) AS cnt
                FROM gpu_jobs
                WHERE status IN ('RUNNING','DISPATCHED')
                  AND gpu_pool_assigned=$1
                GROUP BY tenant_id
                """,
                pool_name,
            )
    return {r["tenant_id"]: int(r["cnt"]) for r in rows}


async def _inflight_total(pool: asyncpg.Pool, pool_name: str, isolation: str | None = None) -> int:
    async with pool.acquire() as conn:
        if isolation:
            v = await conn.fetchval(
                """
                SELECT COUNT(1) FROM gpu_jobs
                WHERE status IN ('RUNNING','DISPATCHED')
                  AND gpu_pool_assigned=$1
                  AND (isolation_level=$2 OR (isolation_level='isolated' AND $2='exclusive'))
                """,
                pool_name,
                isolation,
            )
            return int(v or 0)
        v = await conn.fetchval(
            """
            SELECT COUNT(1) FROM gpu_jobs
            WHERE status IN ('RUNNING','DISPATCHED')
              AND gpu_pool_assigned=$1
            """,
            pool_name,
        )
        return int(v or 0)


async def _pick_next_tenant(pool: asyncpg.Pool, pool_name: str, inflight_by_tenant: dict[str, int], isolation: str | None = None) -> str | None:
    async with pool.acquire() as conn:
        tenants = await conn.fetch("SELECT tenant_id::text AS tenant_id FROM tenant_gpu_policies ORDER BY tenant_id")

    for t in tenants:
        tenant_id = t["tenant_id"]
        async with pool.acquire() as conn:
            policy = await _ensure_policy(conn, tenant_id)

        max_c = int(policy.get("t4_max_concurrency", 1)) if pool_name == "t4" else int(policy.get("mig_max_concurrency", 0))
        if (inflight_by_tenant.get(tenant_id, 0) or 0) >= max_c:
            continue

        async with pool.acquire() as conn:
            if isolation:
                row = await conn.fetchrow(
                    """
                    SELECT 1 FROM gpu_jobs
                    WHERE status='QUEUED'
                      AND tenant_id=$1::uuid
                      AND (gpu_pool_requested=$2 OR gpu_pool_requested='auto')
                      AND (isolation_level=$3 OR (isolation_level='isolated' AND $3='exclusive'))
                    LIMIT 1
                    """,
                    tenant_id,
                    pool_name,
                    isolation,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT 1 FROM gpu_jobs
                    WHERE status='QUEUED'
                      AND tenant_id=$1::uuid
                      AND (gpu_pool_requested=$2 OR gpu_pool_requested='auto')
                    LIMIT 1
                    """,
                    tenant_id,
                    pool_name,
                )

        if row:
            return tenant_id

    return None


async def _pick_job_for_tenant(pool: asyncpg.Pool, tenant_id: str, pool_name: str, isolation: str | None = None) -> str | None:
    async with pool.acquire() as conn:
        if isolation:
            row = await conn.fetchrow(
                """
                SELECT id::text AS id
                FROM gpu_jobs
                WHERE status='QUEUED'
                  AND tenant_id=$1::uuid
                  AND (gpu_pool_requested=$2 OR gpu_pool_requested='auto')
                  AND (isolation_level=$3 OR (isolation_level='isolated' AND $3='exclusive'))
                ORDER BY priority DESC, requested_at ASC
                LIMIT 1
                """,
                tenant_id,
                pool_name,
                isolation,
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT id::text AS id
                FROM gpu_jobs
                WHERE status='QUEUED'
                  AND tenant_id=$1::uuid
                  AND (gpu_pool_requested=$2 OR gpu_pool_requested='auto')
                ORDER BY priority DESC, requested_at ASC
                LIMIT 1
                """,
                tenant_id,
                pool_name,
            )
    return row["id"] if row else None


async def _dispatch_job(pool: asyncpg.Pool, js, job_id: str, pool_name: str, dispatch_subject: str) -> bool:
    token = str(uuid.uuid4())

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE gpu_jobs
            SET status='DISPATCHED',
                gpu_pool_assigned=$2,
                dispatch_token=$3::uuid,
                dispatch_attempts=dispatch_attempts+1,
                dispatched_at=now(),
                updated_at=now()
            WHERE id=$1::uuid AND status='QUEUED'
            RETURNING id::text AS id
            """,
            job_id,
            pool_name,
            token,
        )
        if not row:
            return False

    try:
        await publish(js, dispatch_subject, {"job_id": job_id, "dispatch_token": token})
        return True
    except Exception as e:
        log.warning("dispatch_publish_failed", job_id=job_id, error=str(e))
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE gpu_jobs
                SET status='QUEUED',
                    gpu_pool_assigned=NULL,
                    dispatch_token=NULL,
                    dispatched_at=NULL,
                    updated_at=now()
                WHERE id=$1::uuid AND status='DISPATCHED' AND dispatch_token=$2::uuid
                """,
                job_id,
                token,
            )
        return False


async def _requeue_stale_dispatched(pool: asyncpg.Pool):
    timeout_s = float(os.getenv("DISPATCH_TIMEOUT_SECONDS", "120"))
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE gpu_jobs
            SET status='QUEUED',
                gpu_pool_assigned=NULL,
                dispatch_token=NULL,
                dispatched_at=NULL,
                updated_at=now()
            WHERE status='DISPATCHED'
              AND dispatched_at < (now() - ($1::float * interval '1 second'))
            """,
            timeout_s,
        )


async def _has_queued(pool: asyncpg.Pool, pool_name: str, isolation: str | None = None) -> bool:
    async with pool.acquire() as conn:
        if isolation:
            v = await conn.fetchval(
                """
                SELECT 1 FROM gpu_jobs
                WHERE status='QUEUED'
                  AND (gpu_pool_requested=$1 OR gpu_pool_requested='auto')
                  AND (isolation_level=$2 OR (isolation_level='isolated' AND $2='exclusive'))
                LIMIT 1
                """,
                pool_name,
                isolation,
            )
        else:
            v = await conn.fetchval(
                """
                SELECT 1 FROM gpu_jobs
                WHERE status='QUEUED'
                  AND (gpu_pool_requested=$1 OR gpu_pool_requested='auto')
                LIMIT 1
                """,
                pool_name,
            )
    return bool(v)


async def _schedule_pool_mig(pool: asyncpg.Pool, js):
    slots = _mig_slots()
    if slots <= 0:
        return

    inflight = await _inflight_total(pool, "mig")
    capacity = max(0, slots - inflight)
    if capacity <= 0:
        return

    for _ in range(min(capacity, 10)):
        inflight_by_tenant = await _inflight_counts_per_tenant(pool, "mig")
        tenant_id = await _pick_next_tenant(pool, "mig", inflight_by_tenant)
        if not tenant_id:
            return
        job_id = await _pick_job_for_tenant(pool, tenant_id, "mig")
        if not job_id:
            return
        ok = await _dispatch_job(pool, js, job_id, "mig", "mlops.gpu.jobs.dispatched.mig")
        if not ok:
            return


async def _schedule_pool_t4(pool: asyncpg.Pool, js):
    shared_slots = _t4_shared_slots()
    exclusive_slots = _t4_exclusive_slots()

    inflight_shared = await _inflight_total(pool, "t4", isolation="shared")
    inflight_excl = await _inflight_total(pool, "t4", isolation="exclusive")

    # Soft exclusivity: do not mix shared and exclusive jobs concurrently.
    if inflight_excl > 0:
        capacity = max(0, exclusive_slots - inflight_excl)
        for _ in range(min(capacity, 5)):
            inflight_by_tenant = await _inflight_counts_per_tenant(pool, "t4", isolation="exclusive")
            tenant_id = await _pick_next_tenant(pool, "t4", inflight_by_tenant, isolation="exclusive")
            if not tenant_id:
                return
            job_id = await _pick_job_for_tenant(pool, tenant_id, "t4", isolation="exclusive")
            if not job_id:
                return
            ok = await _dispatch_job(pool, js, job_id, "t4", "mlops.gpu.jobs.dispatched.t4.exclusive")
            if not ok:
                return
        return

    if inflight_shared > 0:
        capacity = max(0, shared_slots - inflight_shared)
        for _ in range(min(capacity, 10)):
            inflight_by_tenant = await _inflight_counts_per_tenant(pool, "t4", isolation="shared")
            tenant_id = await _pick_next_tenant(pool, "t4", inflight_by_tenant, isolation="shared")
            if not tenant_id:
                return
            job_id = await _pick_job_for_tenant(pool, tenant_id, "t4", isolation="shared")
            if not job_id:
                return
            ok = await _dispatch_job(pool, js, job_id, "t4", "mlops.gpu.jobs.dispatched.t4.shared")
            if not ok:
                return
        return

    # Idle: prefer exclusive if any queued; otherwise shared.
    if await _has_queued(pool, "t4", isolation="exclusive"):
        inflight_by_tenant = await _inflight_counts_per_tenant(pool, "t4", isolation="exclusive")
        tenant_id = await _pick_next_tenant(pool, "t4", inflight_by_tenant, isolation="exclusive")
        if not tenant_id:
            return
        job_id = await _pick_job_for_tenant(pool, tenant_id, "t4", isolation="exclusive")
        if not job_id:
            return
        await _dispatch_job(pool, js, job_id, "t4", "mlops.gpu.jobs.dispatched.t4.exclusive")
        return

    capacity = max(0, shared_slots - inflight_shared)
    for _ in range(min(capacity, 10)):
        inflight_by_tenant = await _inflight_counts_per_tenant(pool, "t4", isolation="shared")
        tenant_id = await _pick_next_tenant(pool, "t4", inflight_by_tenant, isolation="shared")
        if not tenant_id:
            return
        job_id = await _pick_job_for_tenant(pool, tenant_id, "t4", isolation="shared")
        if not job_id:
            return
        ok = await _dispatch_job(pool, js, job_id, "t4", "mlops.gpu.jobs.dispatched.t4.shared")
        if not ok:
            return


app = create_app("gpu-scheduler-service", enable_idempotency=False)
router = APIRouter(prefix="/api/v1")


@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True, "service": "gpu-scheduler-service"}


@router.get("/tenant-gpu-policies")
async def list_policies():
    pool = app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tenant_id::text AS tenant_id, plan, t4_max_concurrency, mig_max_concurrency,
                   max_queued_jobs, priority_boost, updated_at
            FROM tenant_gpu_policies
            ORDER BY tenant_id
            """
        )
    return {"items": [dict(r) for r in rows]}


@router.put("/tenant-gpu-policies/{tenant_id}")
async def upsert_policy(tenant_id: str, payload: dict):
    pool = app.state.db_pool
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tenant_gpu_policies(tenant_id, plan, t4_max_concurrency, mig_max_concurrency, max_queued_jobs, priority_boost)
            VALUES ($1::uuid,$2,$3,$4,$5,$6)
            ON CONFLICT (tenant_id) DO UPDATE SET
              plan=EXCLUDED.plan,
              t4_max_concurrency=EXCLUDED.t4_max_concurrency,
              mig_max_concurrency=EXCLUDED.mig_max_concurrency,
              max_queued_jobs=EXCLUDED.max_queued_jobs,
              priority_boost=EXCLUDED.priority_boost,
              updated_at=now()
            """,
            tenant_id,
            payload.get("plan", "free"),
            int(payload.get("t4_max_concurrency", 1)),
            int(payload.get("mig_max_concurrency", 0)),
            int(payload.get("max_queued_jobs", 50)),
            int(payload.get("priority_boost", 0)),
        )
    return {"ok": True}


app.include_router(router)


@app.on_event("startup")
async def _startup():
    nc = await nats_connect()
    app.state.nats = nc
    app.state.js = nc.jetstream()
    await ensure_streams(app.state.js)

    async def _loop():
        tick = float(os.getenv("SCHEDULER_TICK_SECONDS", "0.5"))
        while True:
            try:
                async with app.state.db_pool.acquire() as conn:
                    locked = await _try_lock(conn)
                    if not locked:
                        await asyncio.sleep(tick)
                        continue
                    try:
                        await _requeue_stale_dispatched(app.state.db_pool)
                        await _schedule_pool_t4(app.state.db_pool, app.state.js)
                        await _schedule_pool_mig(app.state.db_pool, app.state.js)
                    finally:
                        await _unlock(conn)
            except Exception as e:
                log.exception("scheduler_loop_error", error=str(e))
            await asyncio.sleep(tick)

    app.state._scheduler_task = asyncio.create_task(_loop())


@app.on_event("shutdown")
async def _shutdown():
    task = getattr(app.state, "_scheduler_task", None)
    if task:
        task.cancel()
    nc = getattr(app.state, "nats", None)
    if nc:
        await nc.drain()
