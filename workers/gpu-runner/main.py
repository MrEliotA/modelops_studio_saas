from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Dict, Optional

import asyncpg
import httpx
import nats
from nats.errors import TimeoutError
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy
import structlog

from mlops_common.nats_client import ensure_streams, publish

log = structlog.get_logger("gpu-dispatcher")


def _safe_name(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:63] if len(s) > 63 else s


async def _execute_http(target_url: str, request_json: dict) -> dict:
    timeout_s = float(os.getenv("HTTP_TIMEOUT_SECONDS", "300"))
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
        r = await client.post(target_url, json=request_json)
        r.raise_for_status()
        return r.json()


async def _execute_simulate(target_url: str, request_json: dict) -> dict:
    await asyncio.sleep(2)
    return {"ok": True, "target_url": target_url, "echo": request_json}


async def _direct_execute(db: asyncpg.Pool, js, job_id: str, dispatch_token: str) -> None:
    # Dev/demo mode: execute inside the dispatcher process (no K8s Job isolation).
    executor = (os.getenv("GPU_EXECUTOR") or "simulate").lower().strip()

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
        return

    try:
        if executor == "simulate":
            response = await _execute_simulate(row["target_url"], row["request_json"] or {})
        else:
            response = await _execute_http(row["target_url"], row["request_json"] or {})

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
                        "gpu_pool": row.get("gpu_pool_assigned"),
                        "gpu_class": row.get("isolation_level"),
                    }
                ),
            )

        await publish(js, "mlops.gpu.jobs.finished", {"job_id": job_id, "status": "SUCCEEDED", "elapsed_seconds": float(elapsed_s)})
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
        raise


def _k8s_incluster_session() -> httpx.AsyncClient:
    ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    token = open(token_path, "r", encoding="utf-8").read().strip()
    return httpx.AsyncClient(
        base_url="https://kubernetes.default.svc",
        verify=ca_path,
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(10.0),
    )


async def _create_job(
    client: httpx.AsyncClient,
    namespace: str,
    name: str,
    image: str,
    env: Dict[str, str],
    node_selector: Dict[str, str],
    gpu_resource_name: str,
    gpu_resource_count: str,
    ttl_seconds_after_finished: int,
) -> None:
    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": namespace, "labels": {"app": "gpu-executor"}},
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": ttl_seconds_after_finished,
            "template": {
                "metadata": {"labels": {"job-name": name, "app": "gpu-executor"}},
                "spec": {
                    "restartPolicy": "Never",
                    "nodeSelector": node_selector,
                    "containers": [
                        {
                            "name": "executor",
                            "image": image,
                            "imagePullPolicy": "IfNotPresent",
                            "workingDir": "/app/workers/gpu-runner",
                            "command": ["python", "executor.py"],
                            "env": [{"name": k, "value": v} for k, v in env.items()],
                            "resources": {
                                "requests": {gpu_resource_name: gpu_resource_count},
                                "limits": {gpu_resource_name: gpu_resource_count},
                            },
                        }
                    ],
                },
            },
        },
    }

    r = await client.post(f"/apis/batch/v1/namespaces/{namespace}/jobs", json=job)
    if r.status_code == 409:
        return
    r.raise_for_status()


async def main() -> None:
    nats_url = os.getenv("NATS_URL", "nats://nats:4222")
    database_url = os.getenv("DATABASE_URL", "")

    stream = os.getenv("GPU_STREAM", "MLOPS_GPU")
    gpu_pool = (os.getenv("GPU_POOL") or "t4").lower().strip()
    gpu_class = (os.getenv("GPU_CLASS") or "").lower().strip()

    mode = (os.getenv("GPU_EXECUTION_MODE") or "direct").lower().strip()  # direct|k8s_job

    if gpu_pool == "t4" and gpu_class in ("shared", "exclusive"):
        subject = f"mlops.gpu.jobs.dispatched.t4.{gpu_class}"
        durable = os.getenv("NATS_DURABLE", f"gpu-dispatcher-t4-{gpu_class}")
    else:
        subject = f"mlops.gpu.jobs.dispatched.{gpu_pool}"
        durable = os.getenv("NATS_DURABLE", f"gpu-dispatcher-{gpu_pool}")

    db: Optional[asyncpg.Pool] = None
    if database_url:
        db = await asyncpg.create_pool(database_url)

    nc = await nats.connect(nats_url)
    js = nc.jetstream()
    await ensure_streams(js)

    try:
        await js.add_consumer(
            stream,
            ConsumerConfig(
                durable_name=durable,
                ack_policy=AckPolicy.EXPLICIT,
                deliver_policy=DeliverPolicy.ALL,
                filter_subject=subject,
            ),
        )
    except Exception:
        pass

    sub = await js.pull_subscribe(subject, durable=durable, stream=stream)
    log.info("dispatcher_started", subject=subject, durable=durable, mode=mode, gpu_pool=gpu_pool, gpu_class=gpu_class or None)

    k8s_ns = os.getenv("GPU_JOB_NAMESPACE", "mlops-system")
    executor_image = os.getenv("GPU_EXECUTOR_IMAGE", "")
    ttl = int(os.getenv("GPU_JOB_TTL_SECONDS", "120"))

    node_selector_key = os.getenv("GPU_NODE_SELECTOR_KEY", "nvidia.com/device-plugin.config")
    node_selector_val = os.getenv("GPU_NODE_SELECTOR_VALUE", "tesla-t4")
    gpu_resource_name = os.getenv("GPU_RESOURCE_NAME", "nvidia.com/gpu")
    gpu_resource_count = os.getenv("GPU_RESOURCE_COUNT", "1")

    http_timeout = os.getenv("HTTP_TIMEOUT_SECONDS", "300")
    gpu_executor = os.getenv("GPU_EXECUTOR", "http")

    client: Optional[httpx.AsyncClient] = None
    if mode == "k8s_job":
        if not executor_image:
            raise RuntimeError("GPU_EXECUTOR_IMAGE is required for GPU_EXECUTION_MODE=k8s_job")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required for GPU_EXECUTION_MODE=k8s_job")
        client = _k8s_incluster_session()

    while True:
        try:
            msgs = await sub.fetch(10, timeout=1)
        except TimeoutError:
            msgs = []

        for msg in msgs:
            try:
                evt = json.loads(msg.data.decode("utf-8"))
                job_id = evt.get("job_id")
                dispatch_token = evt.get("dispatch_token")
                if not job_id or not dispatch_token:
                    await msg.ack()
                    continue

                if mode == "direct":
                    if not db:
                        raise RuntimeError("DATABASE_URL is required for direct execution")
                    await _direct_execute(db, js, job_id, dispatch_token)
                    await msg.ack()
                    continue

                job_name = _safe_name(f"gpu-exec-{job_id[:8]}-{dispatch_token[:8]}")
                env = {
                    "DATABASE_URL": database_url,
                    "NATS_URL": nats_url,
                    "HTTP_TIMEOUT_SECONDS": http_timeout,
                    "GPU_EXECUTOR": gpu_executor,
                    "GPU_POOL": gpu_pool,
                    "GPU_CLASS": gpu_class,
                    "JOB_ID": job_id,
                    "DISPATCH_TOKEN": dispatch_token,
                }

                await _create_job(
                    client=client,  # type: ignore[arg-type]
                    namespace=k8s_ns,
                    name=job_name,
                    image=executor_image,
                    env=env,
                    node_selector={node_selector_key: node_selector_val},
                    gpu_resource_name=gpu_resource_name,
                    gpu_resource_count=gpu_resource_count,
                    ttl_seconds_after_finished=ttl,
                )

                await msg.ack()
            except Exception as e:
                log.exception("dispatch_failed", error=str(e))
                continue

        await asyncio.sleep(0.2)


if __name__ == "__main__":
    asyncio.run(main())
