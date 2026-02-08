import os
import asyncio
import json
import ssl
from typing import Any, Dict, Optional, Tuple

import asyncpg
import nats
import httpx
import structlog
from nats.errors import TimeoutError
from nats.js.api import ConsumerConfig, AckPolicy, DeliverPolicy

log = structlog.get_logger("deploy-worker")

KSERVE_GROUP = "serving.kserve.io"
KSERVE_VERSION = "v1beta1"
KSERVE_PLURAL = "inferenceservices"


def _dns_name(prefix: str, endpoint_id: str) -> str:
    # Keep names deterministic and DNS-1123 safe.
    return f"{prefix}-{endpoint_id[:8]}".lower()


def _incluster_k8s_config() -> Optional[Tuple[str, str, str]]:
    host = os.getenv("KUBERNETES_SERVICE_HOST")
    port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
    if not host:
        return None

    token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
    if not os.path.exists(token_path) or not os.path.exists(ca_path):
        return None

    token = open(token_path, "r", encoding="utf-8").read().strip()
    api = f"https://{host}:{port}"
    return api, token, ca_path


def _kserve_api_base(api_server: str, namespace: str) -> str:
    return f"{api_server}/apis/{KSERVE_GROUP}/{KSERVE_VERSION}/namespaces/{namespace}/{KSERVE_PLURAL}"


async def _k8s_get_isvc(client: httpx.AsyncClient, api_base: str, name: str) -> httpx.Response:
    return await client.get(f"{api_base}/{name}")


async def _k8s_create_isvc(client: httpx.AsyncClient, api_base: str, manifest: Dict[str, Any]) -> httpx.Response:
    return await client.post(api_base, json=manifest)


async def _k8s_replace_isvc(client: httpx.AsyncClient, api_base: str, name: str, manifest: Dict[str, Any], resource_version: str) -> httpx.Response:
    manifest = dict(manifest)
    manifest.setdefault("metadata", {})["resourceVersion"] = resource_version
    return await client.put(f"{api_base}/{name}", json=manifest)


async def _k8s_delete_isvc(client: httpx.AsyncClient, api_base: str, name: str) -> httpx.Response:
    return await client.delete(f"{api_base}/{name}")


def _truthy(v: Any) -> bool:
    return str(v).lower() in {"1", "true", "yes", "y"}


def _build_isvc(endpoint: dict) -> Dict[str, Any]:
    """Build a KServe InferenceService manifest.

    Notes:
    - Canary rollouts require Knative (serverless) deployment mode. KServe docs recommend using
      `canaryTrafficPercent` under `spec.predictor`. 
    - KEDA autoscaling is typically used with Raw/Standard deployment mode.
    """
    endpoint_id = str(endpoint["id"])
    name = _dns_name(os.getenv("KSERVE_NAME_PREFIX", "isvc"), endpoint_id)
    namespace = os.getenv("KSERVE_NAMESPACE", "mlops-serving")

    traffic = endpoint.get("traffic") or {}
    autoscaling = endpoint.get("autoscaling") or {}
    runtime_config = endpoint.get("runtime_config") or {}

    # Model artifact URI for KServe storageUri.
    storage_uri = endpoint.get("artifact_uri")

    # Runtime selection.
    runtime = (endpoint.get("runtime") or "kserve").lower()
    model_format = runtime_config.get("modelFormat") or runtime_config.get("model_format")
    if not model_format:
        model_format = "triton" if "triton" in runtime else runtime_config.get("format") or "sklearn"

    # Deployment mode.
    canary_pct = traffic.get("canaryTrafficPercent")
    if canary_pct is None:
        canary_pct = traffic.get("canary_percent")

    is_canary = canary_pct is not None

    # KServe configuration keys differ across versions; keep both common spellings.
    annotations: Dict[str, str] = {}
    deployment_mode = runtime_config.get("deploymentMode") or runtime_config.get("deployment_mode")

    if is_canary:
        # Canary requires Knative/serverless.
        annotations["serving.kserve.io/deploymentMode"] = deployment_mode or "Knative"
    else:
        # Default to RawDeployment when KEDA is used.
        if _truthy(autoscaling.get("keda")) or runtime_config.get("autoscalerClass") == "keda":
            annotations["serving.kserve.io/deploymentMode"] = deployment_mode or "RawDeployment"
            annotations["serving.kserve.io/autoscalerClass"] = "keda"

    # Prometheus scraping (KServe supports enabling scraping via annotation/config).
    if _truthy(runtime_config.get("enablePrometheusScraping", True)):
        annotations["serving.kserve.io/enable-prometheus-scraping"] = "true"

    predictor: Dict[str, Any] = {}

    # Autoscaling hints (work for both serverless and raw deployment modes).
    if autoscaling.get("minReplicas") is not None:
        predictor["minReplicas"] = int(autoscaling["minReplicas"])
    if autoscaling.get("maxReplicas") is not None:
        predictor["maxReplicas"] = int(autoscaling["maxReplicas"])

    # Canary traffic split.
    if is_canary:
        predictor["canaryTrafficPercent"] = int(canary_pct)

    # Optional KServe request batching (distinct from Triton dynamic batching).
    batcher = runtime_config.get("batcher")
    if isinstance(batcher, dict):
        predictor["batcher"] = {
            "maxBatchSize": int(batcher.get("maxBatchSize", 32)),
            "maxLatency": int(batcher.get("maxLatency", 500)),
        }

    # Timeouts.
    if runtime_config.get("timeout") is not None:
        predictor["timeout"] = int(runtime_config["timeout"])

    # Model spec.
    model: Dict[str, Any] = {
        "modelFormat": {"name": str(model_format)},
    }
    if storage_uri:
        model["storageUri"] = storage_uri

    protocol_version = runtime_config.get("protocolVersion")
    if protocol_version:
        model["protocolVersion"] = str(protocol_version)

    runtime_version = runtime_config.get("runtimeVersion")
    if runtime_version:
        model["runtimeVersion"] = str(runtime_version)

    # Resources.
    resources = runtime_config.get("resources") or {}
    if not resources:
        # Conservative defaults.
        resources = {
            "requests": {"cpu": "250m", "memory": "512Mi"},
            "limits": {"cpu": "1000m", "memory": "1Gi"},
        }

    # If GPU is requested, the user can set runtime_config.gpu=true.
    if _truthy(runtime_config.get("gpu")):
        resources.setdefault("limits", {})["nvidia.com/gpu"] = 1
        resources.setdefault("requests", {})["nvidia.com/gpu"] = 1

    model["resources"] = resources

    # Storage access.
    sa_name = runtime_config.get("serviceAccountName")
    if sa_name:
        predictor["serviceAccountName"] = sa_name

    predictor["model"] = model

    manifest = {
        "apiVersion": f"{KSERVE_GROUP}/{KSERVE_VERSION}",
        "kind": "InferenceService",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {
                "mlops.tenancy/tenant_id": str(endpoint.get("tenant_id")),
                "mlops.tenancy/project_id": str(endpoint.get("project_id")),
                "mlops.platform/endpoint_id": endpoint_id,
            },
            "annotations": annotations,
        },
        "spec": {
            "predictor": predictor,
        },
    }

    return manifest


async def _wait_isvc_ready(client: httpx.AsyncClient, api_base: str, name: str, timeout_s: int) -> str:
    """Wait until KServe sets status.url and Ready condition."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    last_err = None

    while asyncio.get_event_loop().time() < deadline:
        r = await _k8s_get_isvc(client, api_base, name)
        if r.status_code == 200:
            obj = r.json()
            url = (obj.get("status") or {}).get("url")
            conds = (obj.get("status") or {}).get("conditions") or []
            ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conds)
            if url and ready:
                return url
        else:
            last_err = f"isvc_get_http_{r.status_code}"

        await asyncio.sleep(3)

    raise RuntimeError(f"InferenceService not ready within timeout ({timeout_s}s). last_err={last_err}")


async def _set_endpoint_status(db: asyncpg.Pool, endpoint_id: str, status: str, url: Optional[str] = None):
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE endpoints SET status=$2, url=COALESCE($3,url), updated_at=now() WHERE id=$1::uuid",
            endpoint_id,
            status,
            url,
        )


async def _fetch_endpoint_bundle(db: asyncpg.Pool, endpoint_id: str) -> dict:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT e.*, mv.artifact_uri
               FROM endpoints e
               LEFT JOIN model_versions mv ON mv.id = e.model_version_id
               WHERE e.id=$1::uuid""",
            endpoint_id,
        )
        if not row:
            raise RuntimeError(f"endpoint_not_found: {endpoint_id}")
        return dict(row)


async def _apply_kserve(endpoint: dict) -> str:
    cfg = _incluster_k8s_config()
    if not cfg:
        raise RuntimeError("k8s_config_missing (not running in-cluster)")

    api_server, token, ca_path = cfg
    namespace = os.getenv("KSERVE_NAMESPACE", "mlops-serving")
    api_base = _kserve_api_base(api_server, namespace)

    # Trust cluster CA.
    ssl_ctx = ssl.create_default_context(cafile=ca_path)
    transport = httpx.AsyncHTTPTransport(verify=ssl_ctx)

    headers = {"Authorization": f"Bearer {token}"}

    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(headers=headers, timeout=timeout, transport=transport) as client:
        manifest = _build_isvc(endpoint)
        name = manifest["metadata"]["name"]

        get_r = await _k8s_get_isvc(client, api_base, name)
        if get_r.status_code == 404:
            create_r = await _k8s_create_isvc(client, api_base, manifest)
            if create_r.status_code not in (200, 201):
                raise RuntimeError(f"isvc_create_failed status={create_r.status_code} body={create_r.text}")
        elif get_r.status_code == 200:
            rv = str(get_r.json().get("metadata", {}).get("resourceVersion"))
            rep_r = await _k8s_replace_isvc(client, api_base, name, manifest, rv)
            if rep_r.status_code not in (200, 201):
                raise RuntimeError(f"isvc_replace_failed status={rep_r.status_code} body={rep_r.text}")
        else:
            raise RuntimeError(f"isvc_get_failed status={get_r.status_code} body={get_r.text}")

        url = await _wait_isvc_ready(client, api_base, name, int(os.getenv("DEPLOY_TIMEOUT_SECONDS", "600")))
        return url


async def _delete_kserve(endpoint_id: str) -> None:
    cfg = _incluster_k8s_config()
    if not cfg:
        raise RuntimeError("k8s_config_missing (not running in-cluster)")

    api_server, token, ca_path = cfg
    namespace = os.getenv("KSERVE_NAMESPACE", "mlops-serving")
    api_base = _kserve_api_base(api_server, namespace)

    ssl_ctx = ssl.create_default_context(cafile=ca_path)
    transport = httpx.AsyncHTTPTransport(verify=ssl_ctx)
    headers = {"Authorization": f"Bearer {token}"}
    timeout = httpx.Timeout(30.0, connect=10.0)

    name = _dns_name(os.getenv("KSERVE_NAME_PREFIX", "isvc"), endpoint_id)

    async with httpx.AsyncClient(headers=headers, timeout=timeout, transport=transport) as client:
        r = await _k8s_delete_isvc(client, api_base, name)
        if r.status_code not in (200, 202, 204, 404):
            raise RuntimeError(f"isvc_delete_failed status={r.status_code} body={r.text}")


async def main():
    deploy_mode = os.getenv("DEPLOY_MODE", "simulate").lower()

    db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    nc = await nats.connect(os.getenv("NATS_URL", "nats://nats:4222"))
    js = nc.jetstream()

    stream = "MLOPS_SERVING"

    # Two independent consumers: deploy + delete
    deploy_subject = "mlops.serving.deploy_requested"
    deploy_durable = "deploy-worker"

    delete_subject = "mlops.serving.delete_requested"
    delete_durable = "deploy-worker-delete"

    try:
        await js.add_consumer(
            stream,
            ConsumerConfig(
                durable_name=deploy_durable,
                ack_policy=AckPolicy.EXPLICIT,
                deliver_policy=DeliverPolicy.ALL,
                filter_subject=deploy_subject,
            ),
        )
    except Exception:
        pass

    try:
        await js.add_consumer(
            stream,
            ConsumerConfig(
                durable_name=delete_durable,
                ack_policy=AckPolicy.EXPLICIT,
                deliver_policy=DeliverPolicy.ALL,
                filter_subject=delete_subject,
            ),
        )
    except Exception:
        pass

    deploy_sub = await js.pull_subscribe(deploy_subject, durable=deploy_durable, stream=stream)
    delete_sub = await js.pull_subscribe(delete_subject, durable=delete_durable, stream=stream)
    log.info(
        "worker_started",
        stream=stream,
        deploy_subject=deploy_subject,
        delete_subject=delete_subject,
        deploy_mode=deploy_mode,
    )

    while True:
        # Fetch a small batch from both subscriptions.
        try:
            deploy_msgs = await deploy_sub.fetch(10, timeout=1)
        except TimeoutError:
            deploy_msgs = []

        try:
            delete_msgs = await delete_sub.fetch(10, timeout=1)
        except TimeoutError:
            delete_msgs = []

        for msg in deploy_msgs:
            try:
                evt = json.loads(msg.data.decode("utf-8"))
                endpoint_id = evt["endpoint_id"]

                await _set_endpoint_status(db, endpoint_id, "DEPLOYING")
                endpoint = await _fetch_endpoint_bundle(db, endpoint_id)

                if deploy_mode == "simulate":
                    # Simulate a URL similar to Knative/KServe.
                    await asyncio.sleep(2)
                    url = f"http://{_dns_name('isvc', endpoint_id)}.example.local"
                elif deploy_mode == "k8s":
                    url = await _apply_kserve(endpoint)
                else:
                    raise RuntimeError(f"unknown_deploy_mode: {deploy_mode}")

                await _set_endpoint_status(db, endpoint_id, "READY", url=url)
                log.info("endpoint_ready", endpoint_id=endpoint_id, url=url)
                await msg.ack()

            except Exception as e:
                log.exception("failed_processing_deploy", error=str(e))
                try:
                    evt = json.loads(msg.data.decode("utf-8"))
                    await _set_endpoint_status(db, evt.get("endpoint_id"), "ERROR")
                except Exception:
                    pass

        for msg in delete_msgs:
            try:
                evt = json.loads(msg.data.decode("utf-8"))
                endpoint_id = evt["endpoint_id"]

                if deploy_mode == "k8s":
                    await _delete_kserve(endpoint_id)

                # Mark deleted (idempotent - deployment-service also does this)
                await _set_endpoint_status(db, endpoint_id, "DELETED", url=None)
                log.info("endpoint_deleted", endpoint_id=endpoint_id)
                await msg.ack()

            except Exception as e:
                log.exception("failed_processing_delete", error=str(e))
                try:
                    evt = json.loads(msg.data.decode("utf-8"))
                    await _set_endpoint_status(db, evt.get("endpoint_id"), "ERROR")
                except Exception:
                    pass

        await asyncio.sleep(0.2)


if __name__ == "__main__":
    asyncio.run(main())
