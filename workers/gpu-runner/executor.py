from __future__ import annotations

import asyncio
import json
import os
import time

import asyncpg
import httpx
import nats
import structlog

from mlops_common.nats_client import ensure_streams, publish

log = structlog.get_logger("gpu-executor")


async def _execute_http(target_url: str, request_json: dict) -> dict:
    timeout_s = float(os.getenv("HTTP_TIMEOUT_SECONDS", "300"))
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
        r = await client.post(target_url, json=request_json)
        r.raise_for_status()
        return r.json()


async def _execute_simulate(target_url: str, request_json: dict) -> dict:
    await asyncio.sleep(2)
    return {"ok": True, "target_url": target_url, "echo": request_json}


async def _maybe_publish(event_subject: str, payload: dict) -> None:
    nats_url = os.getenv("NATS_URL")
    if not nats_url:
        return
    nc = await nats.connect(nats_url)
    try:
        js = nc.jetstream()
        await ensure_streams(js)
        await publish(js, event_subject, payload)
    finally:
        await nc.drain()


async def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    job_id = os.getenv("JOB_ID")
    dispatch_token = os.getenv("DISPATCH_TOKEN")
    gpu_pool = (os.getenv("GPU_POOL") or "t4").lower().strip()
    gpu_class = (os.getenv("GPU_CLASS") or "").lower().strip()

    if not database_url or not job_id or not dispatch_token:
        raise RuntimeError("DATABASE_URL, JOB_ID, DISPATCH_TOKEN are required")

    executor = (os.getenv("GPU_EXECUTOR") or "http").lower().strip()

    db = await asyncpg.create_pool(database_url)

    t0 = time.monotonic()

    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE gpu_jobs
            SET status='RUNNING', started_at=now(), updated_at=now()
            WHERE id=$1::uuid AND status='DISPATCHED' AND dispatch_token=$2::uuid
            RETURNING id::text AS id,
                      tenant_id::text AS tenant_id,
                      project_id::text AS project_id,
                      gpu_pool_assigned,
                      isolation_level,
                      target_url,
                      request_json
            """,
            job_id,
            dispatch_token,
        )

    if not row:
        log.info("stale_or_already_processed", job_id=job_id)
        await db.close()
        return

    target_url = row["target_url"]
    request_json = row["request_json"] or {}

    try:
        if executor == "simulate":
            response = await _execute_simulate(target_url, request_json)
        else:
            response = await _execute_http(target_url, request_json)

        elapsed_s = max(0.0, time.monotonic() - t0)

        async with db.acquire() as conn:
            await conn.execute(
                """
                UPDATE gpu_jobs
                SET status='SUCCEEDED',
                    response_json=$2,
                    finished_at=now(),
                    updated_at=now()
                WHERE id=$1::uuid
                """,
                job_id,
                json.dumps(response),
            )
            await conn.execute(
                """
                INSERT INTO usage_ledger(
                  tenant_id, project_id, subject_type, subject_id, meter, quantity, labels
                )
                VALUES ($1::uuid,$2::uuid,'gpu_job',$3::uuid,'gpu_seconds',$4,$5)
                """,
                row["tenant_id"],
                row["project_id"],
                job_id,
                float(elapsed_s),
                json.dumps(
                    {
                        "gpu_pool": row.get("gpu_pool_assigned") or gpu_pool,
                        "gpu_class": gpu_class or row.get("isolation_level") or None,
                    }
                ),
            )

        await _maybe_publish(
            "mlops.gpu.jobs.finished",
            {"job_id": job_id, "status": "SUCCEEDED", "elapsed_seconds": float(elapsed_s)},
        )
        log.info("job_succeeded", job_id=job_id, elapsed_seconds=elapsed_s)
    except Exception as e:
        async with db.acquire() as conn:
            await conn.execute(
                """
                UPDATE gpu_jobs
                SET status='FAILED', error=$2, finished_at=now(), updated_at=now()
                WHERE id=$1::uuid
                """,
                job_id,
                str(e),
            )
        await _maybe_publish("mlops.gpu.jobs.finished", {"job_id": job_id, "status": "FAILED", "error": str(e)})
        log.exception("job_failed", job_id=job_id, error=str(e))
        await db.close()
        raise

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
