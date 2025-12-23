from __future__ import annotations

from typing import Any

from kubernetes.client import (
    ApiException,
    CustomObjectsApi,
    V1Container,
    V1ContainerPort,
    V1Deployment,
    V1DeploymentSpec,
    V1EnvVar,
    V1Job,
    V1JobSpec,
    V1LabelSelector,
    V1Namespace,
    V1ObjectMeta,
    V1PodSpec,
    V1PodTemplateSpec,
    V1ResourceRequirements,
    V1Service,
    V1ServicePort,
    V1ServiceSpec,
    V1Toleration,
)

from modelops.core.config import settings

from .client import apps, batch, core, load


def _with_gpu(base: dict[str, str], resource_name: str | None, units: int) -> dict[str, str]:
    if not settings.enable_real_gpu_requests:
        return base
    if not resource_name or units <= 0:
        resource_name = settings.gpu_resource_fallback
    out = dict(base)
    out[str(resource_name)] = str(int(units))
    return out


def ensure_namespace(name: str) -> None:
    load()
    api = core()
    try:
        api.read_namespace(name)
        return
    except Exception:
        pass
    api.create_namespace(V1Namespace(metadata=V1ObjectMeta(name=name)))


def create_job(
    namespace: str,
    name: str,
    image: str,
    command: list[str],
    args: list[str],
    env: dict[str, str],
    cpu: str,
    memory: str,
    node_selector: dict[str, str] | None,
    tolerations: list[dict[str, Any]] | None,
    gpu_resource_name: str | None = None,
    gpu_units: int = 0,
) -> None:
    load()
    api = batch()

    container = V1Container(
        name="worker",
        image=image,
        command=command or None,
        args=args or None,
        env=[V1EnvVar(name=k, value=v) for k, v in env.items()],
        resources=V1ResourceRequirements(
            requests=_with_gpu({"cpu": cpu, "memory": memory}, gpu_resource_name, gpu_units),
            limits=_with_gpu({"cpu": cpu, "memory": memory}, gpu_resource_name, gpu_units),
        ),
    )

    tol_objs = [V1Toleration(**t) for t in (tolerations or [])] or None
    pod_spec = V1PodSpec(restart_policy="Never", containers=[container], node_selector=node_selector, tolerations=tol_objs)
    tpl = V1PodTemplateSpec(metadata=V1ObjectMeta(labels={"app": name}), spec=pod_spec)
    job = V1Job(metadata=V1ObjectMeta(name=name, namespace=namespace), spec=V1JobSpec(template=tpl, backoff_limit=0))

    api.create_namespaced_job(namespace=namespace, body=job)


def create_serving_deployment(
    namespace: str,
    name: str,
    image: str,
    env: dict[str, str],
    node_selector: dict[str, str] | None,
    tolerations: list[dict[str, Any]] | None,
    gpu_resource_name: str | None = None,
    gpu_units: int = 0,
) -> tuple[str, str]:
    load()
    apps_api = apps()
    core_api = core()

    labels = {"app": name}

    container = V1Container(
        name="serving",
        image=image,
        ports=[V1ContainerPort(container_port=8080)],
        env=[V1EnvVar(name=k, value=v) for k, v in env.items()],
        resources=V1ResourceRequirements(
            requests=_with_gpu({}, gpu_resource_name, gpu_units),
            limits=_with_gpu({}, gpu_resource_name, gpu_units),
        ),
    )

    tol_objs = [V1Toleration(**t) for t in (tolerations or [])] or None
    pod_spec = V1PodSpec(containers=[container], node_selector=node_selector, tolerations=tol_objs)
    tpl = V1PodTemplateSpec(
        metadata=V1ObjectMeta(
            labels=labels,
            annotations={"prometheus.io/scrape": "true", "prometheus.io/port": "8080", "prometheus.io/path": "/metrics"},
        ),
        spec=pod_spec,
    )

    dep = V1Deployment(
        metadata=V1ObjectMeta(name=name, namespace=namespace),
        spec=V1DeploymentSpec(replicas=1, selector=V1LabelSelector(match_labels=labels), template=tpl),
    )
    apps_api.create_namespaced_deployment(namespace=namespace, body=dep)

    svc = V1Service(
        metadata=V1ObjectMeta(name=name, namespace=namespace),
        spec=V1ServiceSpec(selector=labels, ports=[V1ServicePort(port=80, target_port=8080)]),
    )
    core_api.create_namespaced_service(namespace=namespace, body=svc)

    ensure_scaledobject_cpu(namespace=namespace, name=name, target_deployment=name)

    return name, name


def ensure_scaledobject_cpu(namespace: str, name: str, target_deployment: str) -> None:
    """Create or patch a KEDA ScaledObject for CPU utilization."""
    if not settings.keda_enabled:
        return

    load()
    co = CustomObjectsApi()
    body = {
        "apiVersion": "keda.sh/v1alpha1",
        "kind": "ScaledObject",
        "metadata": {"name": f"{name}-cpu", "namespace": namespace},
        "spec": {
            "scaleTargetRef": {"name": target_deployment},
            "minReplicaCount": int(settings.keda_min_replicas),
            "maxReplicaCount": int(settings.keda_max_replicas),
            "triggers": [
                {
                    "type": "cpu",
                    "metricType": "Utilization",
                    "metadata": {"value": str(settings.keda_cpu_utilization)},
                }
            ],
        },
    }

    try:
        co.get_namespaced_custom_object("keda.sh", "v1alpha1", namespace, "scaledobjects", body["metadata"]["name"])
        co.patch_namespaced_custom_object("keda.sh", "v1alpha1", namespace, "scaledobjects", body["metadata"]["name"], body)
    except ApiException as e:
        if e.status == 404:
            co.create_namespaced_custom_object("keda.sh", "v1alpha1", namespace, "scaledobjects", body)
        else:
            raise
