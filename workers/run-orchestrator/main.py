from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Optional

import asyncpg
import httpx
import nats
import structlog
from nats.errors import TimeoutError
from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

log = structlog.get_logger("run-orchestrator")

PIPELINE_BACKEND = os.getenv("PIPELINE_BACKEND", "local").lower()

# Kubeflow Pipelines (KFP)
KFP_HOST = os.getenv("KFP_HOST", "").strip()
KFP_NAMESPACE = os.getenv("KFP_NAMESPACE", "kubeflow").strip()
KFP_POLL_INTERVAL_SECONDS = float(os.getenv("KFP_POLL_INTERVAL_SECONDS", "10"))

# Template Service (YAML-only pipeline packages)
TEMPLATE_SERVICE_BASE_URL = os.getenv("TEMPLATE_SERVICE_BASE_URL", "http://template-service:8000").rstrip("/")
TEMPLATE_SERVICE_TIMEOUT_SECONDS = float(os.getenv("TEMPLATE_SERVICE_TIMEOUT_SECONDS", "10"))
SYSTEM_USER_ID = os.getenv("SYSTEM_USER_ID", "system:run-orchestrator")
SYSTEM_ROLES = os.getenv("SYSTEM_ROLES", "system")

try:
    import kfp  # type: ignore
except Exception:  # pragma: no cover
    kfp = None


@dataclass(frozen=True)
class TemplateMeta:
    id: str
    tenant_id: str
    project_id: str
    compiler: str
    default_parameters: dict[str, Any]


def _kfp_enabled() -> bool:
    return PIPELINE_BACKEND == "kfp"


def _require_kfp() -> None:
    if kfp is None:
        raise RuntimeError(
            "KFP backend selected but kfp is not installed. "
            "Add 'kfp' to workers/run-orchestrator/requirements.txt."
        )
    if not KFP_HOST:
        raise RuntimeError("KFP backend selected but KFP_HOST is empty")


def _get_run_state(run_obj: Any) -> str:
    """Best-effort extraction of a run state across KFP client versions."""
    for attr in ("state", "status", "run_status"):
        v = getattr(run_obj, attr, None)
        if v:
            return str(v)

    inner = getattr(run_obj, "run", None)
    if inner is not None:
        for attr in ("state", "status", "run_status"):
            v = getattr(inner, attr, None)
            if v:
                return str(v)

    if isinstance(run_obj, dict):
        for key in ("state", "status", "run_status"):
            v = run_obj.get(key)
            if v:
                return str(v)
        inner = run_obj.get("run")
        if isinstance(inner, dict):
            for key in ("state", "status", "run_status"):
                v = inner.get(key)
                if v:
                    return str(v)

    return "UNKNOWN"


def _map_kfp_state_to_platform_status(state: str) -> Optional[str]:
    s = state.strip().lower()
    if s in {"succeeded", "success", "completed"}:
        return "SUCCEEDED"
    if s in {"failed", "error"}:
        return "FAILED"
    if s in {"running", "in_progress", "pending"}:
        return "RUNNING"
    if s in {"cancelled", "canceled", "skipped"}:
        return "CANCELLED"
    return None


def _build_kfp_client() -> "kfp.Client":  # type: ignore
    _require_kfp()
    return kfp.Client(host=KFP_HOST, namespace=KFP_NAMESPACE)


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Merge b into a (deep), returning a new dict."""
    out: dict[str, Any] = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)  # type: ignore
        else:
            out[k] = v
    return out


def _template_headers(tenant_id: str, project_id: str) -> dict[str, str]:
    # Auth is passthrough in MVP; we propagate tenancy and use a system identity.
    return {
        "X-Tenant-Id": tenant_id,
        "X-Project-Id": project_id,
        "X-User-Id": SYSTEM_USER_ID,
        "X-Roles": SYSTEM_ROLES,
    }


async def _fetch_template_meta(
    http: httpx.AsyncClient,
    tenant_id: str,
    project_id: str,
    template_id: str,
) -> TemplateMeta:
    url = f"{TEMPLATE_SERVICE_BASE_URL}/api/v1/templates/{template_id}"
    r = await http.get(url, headers=_template_headers(tenant_id, project_id))
    if r.status_code == 404:
        raise RuntimeError(f"Template not found: {template_id}")
    if r.status_code >= 400:
        raise RuntimeError(f"Template-service error {r.status_code}: {r.text}")
    data = r.json()
    return TemplateMeta(
        id=str(data["id"]),
        tenant_id=tenant_id,
        project_id=project_id,
        compiler=str(data.get("compiler") or ""),
        default_parameters=dict(data.get("default_parameters") or {}),
    )


async def _fetch_pipeline_package_yaml(
    http: httpx.AsyncClient,
    tenant_id: str,
    project_id: str,
    template_id: str,
) -> str:
    url = f"{TEMPLATE_SERVICE_BASE_URL}/api/v1/templates/{template_id}/package"
    r = await http.get(url, headers=_template_headers(tenant_id, project_id))
    if r.status_code == 404:
        raise RuntimeError(f"Template package not found: {template_id}")
    if r.status_code >= 400:
        raise RuntimeError(f"Template-service error {r.status_code}: {r.text}")
    return r.text


def _is_kfp_yaml_compiler(compiler: str) -> bool:
    c = compiler.strip().lower()
    # Accept legacy values as long as they start with kfp.
    return c.startswith("kfp")


def _experiment_name(tenant_id: str, project_id: str) -> str:
    # KFP experiment names are human-readable; keep stable and short.
    short = hashlib.sha256(f"{tenant_id}:{project_id}".encode("utf-8")).hexdigest()[:12]
    return f"mlops-{short}"


async def _submit_kfp_run(
    client: "kfp.Client",  # type: ignore
    http: httpx.AsyncClient,
    run_id: str,
    template: TemplateMeta,
    run_parameters: dict[str, Any],
) -> str:
    if not _is_kfp_yaml_compiler(template.compiler):
        raise RuntimeError(f"Unsupported template compiler for KFP backend: {template.compiler}")

    pipeline_yaml = await _fetch_pipeline_package_yaml(http, template.tenant_id, template.project_id, template.id)

    params = _deep_merge(template.default_parameters, run_parameters)

    exp_name = _experiment_name(template.tenant_id, template.project_id)
    try:
        if hasattr(client, "create_experiment"):
            client.create_experiment(name=exp_name)
    except Exception:
        pass

    # KFP expects a local file path.
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(pipeline_yaml)
            tmp_path = f.name

        kwargs: dict[str, Any] = {
            "package_path": tmp_path,
            "arguments": params,
            "run_name": f"mlops-saas-{run_id}",
        }

        sig = inspect.signature(client.create_run_from_pipeline_package)
        if "experiment_name" in sig.parameters:
            kwargs["experiment_name"] = exp_name
        if "namespace" in sig.parameters:
            kwargs["namespace"] = KFP_NAMESPACE

        run = client.create_run_from_pipeline_package(**kwargs)

        for attr in ("run_id", "id"):
            v = getattr(run, attr, None)
            if v:
                return str(v)

        if isinstance(run, dict):
            for key in ("run_id", "id"):
                v = run.get(key)
                if v:
                    return str(v)

        return str(run)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


async def _consume_events(db: asyncpg.Pool, js) -> None:
    stream = "MLOPS_RUNS"
    subject = "mlops.runs.requested"
    durable = "run-orchestrator"

    # Create durable consumer (idempotent)
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
    log.info(
        "worker_started",
        stream=stream,
        subject=subject,
        backend=PIPELINE_BACKEND,
        template_service=TEMPLATE_SERVICE_BASE_URL,
    )

    kfp_client = _build_kfp_client() if _kfp_enabled() else None

    timeout = httpx.Timeout(TEMPLATE_SERVICE_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout) as http:
        while True:
            try:
                msgs = await sub.fetch(10, timeout=1)
            except TimeoutError:
                msgs = []

            for msg in msgs:
                try:
                    evt = json.loads(msg.data.decode("utf-8"))
                    run_id = str(evt["run_id"])

                    if _kfp_enabled():
                        assert kfp_client is not None
                        tenant_id = str(evt.get("tenant_id") or "")
                        project_id = str(evt.get("project_id") or "")
                        template_id = str(evt.get("template_id") or "")
                        parameters = dict(evt.get("parameters") or {})

                        template = await _fetch_template_meta(http, tenant_id, project_id, template_id)
                        kfp_run_id = await _submit_kfp_run(kfp_client, http, run_id, template, parameters)

                        async with db.acquire() as conn:
                            await conn.execute(
                                "UPDATE runs SET status='RUNNING', kfp_run_id=$2, updated_at=now() WHERE id=$1",
                                run_id,
                                kfp_run_id,
                            )
                        log.info(
                            "run_submitted_to_kfp",
                            run_id=run_id,
                            kfp_run_id=kfp_run_id,
                            template_id=template_id,
                        )
                    else:
                        async with db.acquire() as conn:
                            await conn.execute(
                                "UPDATE runs SET status='RUNNING', updated_at=now() WHERE id=$1",
                                run_id,
                            )

                        # Simulate pipeline execution
                        await asyncio.sleep(2)

                        async with db.acquire() as conn:
                            await conn.execute(
                                "UPDATE runs SET status='SUCCEEDED', updated_at=now() WHERE id=$1",
                                run_id,
                            )
                        log.info("run_completed", run_id=run_id, status="SUCCEEDED")

                    await msg.ack()
                except Exception as e:
                    log.exception("failed_processing", error=str(e))
                    # Mark as failed if possible.
                    try:
                        evt = json.loads(msg.data.decode("utf-8"))
                        run_id = str(evt.get("run_id") or "")
                        if run_id:
                            async with db.acquire() as conn:
                                await conn.execute(
                                    "UPDATE runs SET status='FAILED', updated_at=now() WHERE id=$1",
                                    run_id,
                                )
                    except Exception:
                        pass
                    # No ack -> will be redelivered.

            await asyncio.sleep(0.2)


async def _reconcile_kfp_runs(db: asyncpg.Pool) -> None:
    if not _kfp_enabled():
        return

    client = _build_kfp_client()

    while True:
        try:
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT id, kfp_run_id FROM runs WHERE status='RUNNING' AND kfp_run_id IS NOT NULL"
                )

            for row in rows:
                run_id = str(row["id"])
                kfp_run_id = str(row["kfp_run_id"])

                try:
                    run = client.get_run(run_id=kfp_run_id)
                    state = _get_run_state(run)
                    mapped = _map_kfp_state_to_platform_status(state)

                    if mapped and mapped != "RUNNING":
                        async with db.acquire() as conn:
                            await conn.execute(
                                "UPDATE runs SET status=$2, updated_at=now() WHERE id=$1",
                                run_id,
                                mapped,
                            )
                        log.info(
                            "run_reconciled",
                            run_id=run_id,
                            kfp_run_id=kfp_run_id,
                            kfp_state=state,
                            status=mapped,
                        )
                except Exception as e:
                    log.exception("kfp_reconcile_error", run_id=run_id, kfp_run_id=kfp_run_id, error=str(e))

        except Exception as e:
            log.exception("reconciler_loop_error", error=str(e))

        await asyncio.sleep(KFP_POLL_INTERVAL_SECONDS)


async def main() -> None:
    db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    nc = await nats.connect(os.getenv("NATS_URL", "nats://nats:4222"))
    js = nc.jetstream()

    tasks = [asyncio.create_task(_consume_events(db, js))]

    if _kfp_enabled():
        tasks.append(asyncio.create_task(_reconcile_kfp_runs(db)))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
