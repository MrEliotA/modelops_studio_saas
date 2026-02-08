#!/usr/bin/env python3
"""Generate per-tenant Kubernetes resources and tenant maps.

This is intentionally simple and GitOps-friendly:
- Input:  deploy/tenants/tenants.yaml
- Outputs:
    1) deploy/k8s/networking/tenants/generated/tenants.generated.yaml
       - Namespaces + NetworkPolicies for per-tenant isolation
    2) deploy/k8s/mlops-saas/base/tenant-map-configmap.generated.yaml
       - A ConfigMap consumed by control-plane-api to map tenant slug -> tenant_id (+ default project_id)

Why:
- You may have ~1000 tenants; hand-writing YAML does not scale.
- Standard Kubernetes NetworkPolicy has no namespaceSelector for cross-namespace rules,
  so we generate one NetworkPolicy set per tenant namespace.

If you run Cilium, you may later switch to Cilium cluster-wide policy resources to avoid per-tenant
manifest explosion (see deploy/k8s/networking/cilium).
"""

from __future__ import annotations

import argparse
import re
import json
import textwrap
import hashlib
import uuid
from pathlib import Path

import yaml


class _LiteralStr(str):
    """A YAML literal block string."""


def _literal_str_representer(dumper: yaml.Dumper, data: _LiteralStr):  # type: ignore
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="|")


yaml.SafeDumper.add_representer(_LiteralStr, _literal_str_representer)  # type: ignore

DEFAULT_INPUT = Path("deploy/tenants/tenants.yaml")
DEFAULT_OUTPUT = Path("deploy/k8s/networking/tenants/generated/tenants.generated.yaml")
DEFAULT_TENANT_MAP_OUTPUT = Path("deploy/k8s/mlops-saas/base/tenant-map-configmap.generated.yaml")
DEFAULT_TENANT_ROUTES_OUTPUT = Path("deploy/k8s/api-gateway/generated/tenant-httproutes.generated.yaml")

# Deterministic UUID namespaces. These keep tenant/project IDs stable across re-generation.
TENANT_UUID_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "mlops-saas/tenant")
PROJECT_UUID_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "mlops-saas/project")


DEFAULT_RESOURCE_QUOTA_HARD: dict[str, str] = {
    "pods": "20",
    "requests.cpu": "8",
    "requests.memory": "32Gi",
    "limits.cpu": "16",
    "limits.memory": "64Gi",
}

DEFAULT_LIMIT_RANGE_CONTAINER: dict = {
    "type": "Container",
    "min": {"cpu": "50m", "memory": "64Mi"},
    "max": {"cpu": "8", "memory": "32Gi"},
    "defaultRequest": {"cpu": "250m", "memory": "256Mi"},
    "default": {"cpu": "1", "memory": "1Gi"},
}

DEFAULT_NETWORK_POLICY: dict = {
    "allowIngressFromNamespaces": ["gateway-system"],
    "exposedPodLabels": {"mlops-saas.io/expose": "true"},
    "ingressPorts": None,
    "allowEgressToNamespaces": ["mlops-system"],
}


def ns_labels(tenant_id: str) -> dict[str, str]:
    return {
        "mlops-saas.io/tenant": "true",
        "mlops-saas.io/tenant-id": tenant_id,
    }


def namespace_doc(name: str, tenant_id: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": name,
            "labels": ns_labels(tenant_id),
        },
    }


def resource_quota(namespace: str, hard: dict[str, str]) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "ResourceQuota",
        "metadata": {"name": "tenant-quota", "namespace": namespace},
        "spec": {"hard": hard},
    }


def limit_range(namespace: str, limits: dict) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "LimitRange",
        "metadata": {"name": "tenant-limits", "namespace": namespace},
        "spec": {"limits": [limits]},
    }


def default_deny_ingress(namespace: str) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": "default-deny-ingress", "namespace": namespace},
        "spec": {
            "podSelector": {},
            "policyTypes": ["Ingress"],
        },
    }


def default_deny_egress(namespace: str) -> dict:
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": "default-deny-egress", "namespace": namespace},
        "spec": {
            "podSelector": {},
            "policyTypes": ["Egress"],
        },
    }


def allow_dns(namespace: str) -> dict:
    # Most clusters run CoreDNS with label k8s-app=kube-dns in kube-system.
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": "allow-dns-egress", "namespace": namespace},
        "spec": {
            "podSelector": {},
            "policyTypes": ["Egress"],
            "egress": [
                {
                    "to": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                            },
                            "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                        },
                        {
                            "namespaceSelector": {
                                "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                            },
                            "podSelector": {"matchLabels": {"k8s-app": "coredns"}},
                        },
                    ],
                    "ports": [
                        {"protocol": "UDP", "port": 53},
                        {"protocol": "TCP", "port": 53},
                    ],
                }
            ],
        },
    }


def allow_egress_to_control_plane(namespace: str) -> dict:
    # Allow tenant workloads to call platform APIs (control-plane, registry, artifact, etc.).
    # Tighten this later per-service/port.
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": "allow-egress-to-mlops-system", "namespace": namespace},
        "spec": {
            "podSelector": {},
            "policyTypes": ["Egress"],
            "egress": [
                {
                    "to": [
                        {
                            "namespaceSelector": {
                                "matchLabels": {"kubernetes.io/metadata.name": "mlops-system"}
                            }
                        }
                    ]
                }
            ],
        },
    }


def allow_same_namespace_traffic(namespace: str) -> dict:
    # When you apply default-deny (ingress/egress), intra-namespace traffic is not implicitly allowed.
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": "allow-same-namespace", "namespace": namespace},
        "spec": {
            "podSelector": {},
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [{"from": [{"podSelector": {}}]}],
            "egress": [{"to": [{"podSelector": {}}]}],
        },
    }


def allow_egress_to_namespaces(namespace: str, allowed_namespaces: list[str]) -> dict | None:
    if not allowed_namespaces:
        return None
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": "allow-egress-to-namespaces", "namespace": namespace},
        "spec": {
            "podSelector": {},
            "policyTypes": ["Egress"],
            "egress": [
                {
                    "to": [
                        {
                            "namespaceSelector": {
                                "matchExpressions": [
                                    {
                                        "key": "kubernetes.io/metadata.name",
                                        "operator": "In",
                                        "values": allowed_namespaces,
                                    }
                                ]
                            }
                        }
                    ]
                }
            ],
        },
    }


def allow_ingress_from_namespaces(
    namespace: str,
    allowed_namespaces: list[str],
    exposed_pod_labels: dict[str, str] | None = None,
    ports: list[dict] | None = None,
) -> dict | None:
    if not allowed_namespaces:
        return None
    rule: dict = {
        "from": [
            {
                "namespaceSelector": {
                    "matchExpressions": [
                        {
                            "key": "kubernetes.io/metadata.name",
                            "operator": "In",
                            "values": allowed_namespaces,
                        }
                    ]
                }
            }
        ]
    }
    if ports:
        rule["ports"] = ports
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": "allow-ingress-from-namespaces", "namespace": namespace},
        "spec": {
            "podSelector": {"matchLabels": exposed_pod_labels} if exposed_pod_labels else {},
            "policyTypes": ["Ingress"],
            "ingress": [rule],
        },
    }


def _as_dict(obj: object, label: str) -> dict:
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise SystemExit(f"Invalid '{label}': expected mapping/dict")
    return obj


def _as_list(obj: object, label: str) -> list:
    if obj is None:
        return []
    if not isinstance(obj, list):
        raise SystemExit(f"Invalid '{label}': expected list")
    return obj


def _deterministic_tenant_id(name: str) -> str:
    return str(uuid.uuid5(TENANT_UUID_NS, name))


def _deterministic_project_id(name: str, suffix: str = "default") -> str:
    return str(uuid.uuid5(PROJECT_UUID_NS, f"{name}:{suffix}"))


def _normalize_tenant_entry(entry: dict) -> dict:
    name = str(entry.get("name") or "").strip()
    if not name:
        raise SystemExit(f"Tenant entry missing 'name': {entry}")
    tenant_id = str(entry.get("tenant_id") or "").strip() or _deterministic_tenant_id(name)
    project_id = str(entry.get("project_id") or "").strip() or _deterministic_project_id(name)
    return {"name": name, "tenant_id": tenant_id, "project_id": project_id}


def _generate_tenants(generate_cfg: dict) -> list[dict]:
    if not generate_cfg:
        return []
    count = int(generate_cfg.get("count") or 0)
    if count <= 0:
        raise SystemExit("Invalid 'generate.count': must be a positive integer")
    prefix = str(generate_cfg.get("name_prefix") or "tenant-")
    start = int(generate_cfg.get("start_index") or 1)
    width = generate_cfg.get("index_width")
    if width is None:
        width = len(str(start + count - 1))
    width = int(width)
    project_suffix = str(generate_cfg.get("project_suffix") or "default")

    tenants: list[dict] = []
    for i in range(start, start + count):
        name = f"{prefix}{i:0{width}d}"
        tenants.append(
            {
                "name": name,
                "tenant_id": _deterministic_tenant_id(name),
                "project_id": _deterministic_project_id(name, suffix=project_suffix),
            }
        )
    return tenants


def load_tenants_config(path: Path) -> tuple[list[dict], dict]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise SystemExit(f"Invalid tenants file: expected a mapping/dict in {path}")

    # Backward compatible: `tenants:`
    static_entries = _as_list(data.get("tenants"), "tenants")
    # New: `static:`
    static_entries += _as_list(data.get("static"), "static")

    generate_cfg = _as_dict(data.get("generate"), "generate")
    generated_entries = _generate_tenants(generate_cfg) if generate_cfg else []

    tenants_raw = [*static_entries, *generated_entries]
    tenants = [_normalize_tenant_entry(_as_dict(t, "tenant")) for t in tenants_raw]

    # Validate uniqueness
    names = [t["name"] for t in tenants]
    if len(names) != len(set(names)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise SystemExit(f"Duplicate tenant names: {dupes}")

    defaults = _as_dict(data.get("defaults"), "defaults")
    return tenants, defaults


def _compact_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def tenant_map_configmap(tenants: list[dict]) -> dict:
    mapping: dict[str, dict[str, str]] = {}
    for t in tenants:
        name = str(t.get("name") or "").strip()
        if not name:
            continue
        tenant_id = str(t.get("tenant_id") or "").strip()
        project_id = str(t.get("project_id") or "").strip()
        if not tenant_id:
            continue
        entry: dict[str, str] = {"tenant_id": tenant_id}
        if project_id:
            entry["project_id"] = project_id
        mapping[name] = entry

    rendered = json.dumps(mapping, indent=2, sort_keys=True)
    checksum = hashlib.sha256(_compact_json(mapping).encode("utf-8")).hexdigest()

    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "mlops-tenant-map",
            "labels": {
                "app.kubernetes.io/name": "mlops-saas",
                "app.kubernetes.io/component": "tenant-routing",
            },
            "annotations": {
                "mlops-saas.io/tenant-map-sha256": checksum,
            },
        },
        "data": {
            "tenant-map.json": _LiteralStr(textwrap.dedent(f"""\
                {rendered}
                """).strip() + "\n")
        },
    }


def _dns_safe_name(name: str) -> str:
    # K8s object names: DNS-1123 label (lowercase alnum and '-')
    safe = re.sub(r"[^a-z0-9-]", "-", name.lower())
    safe = re.sub(r"-+", "-", safe).strip('-')
    return safe or "tenant"


def tenant_routes_manifest(
    tenants: list[dict],
    base_domain: str = "mlops.local",
    gateway_name: str = "mlops-gateway",
    gateway_namespace: str = "gateway-system",
    backend_service: str = "control-plane-api",
    backend_namespace: str = "mlops-system",
    backend_port: int = 8000,
) -> dict:
    items: list[dict] = []
    for t in tenants:
        slug = str(t.get("name") or "").strip()
        if not slug:
            continue
        tenant_id = str(t.get("tenant_id") or "").strip()
        project_id = str(t.get("project_id") or "").strip()

        route_name_base = f"tenant-{_dns_safe_name(slug)}"
        if len(route_name_base) > 63:
            # keep deterministic shortening
            h = hashlib.sha256(route_name_base.encode('utf-8')).hexdigest()[:10]
            route_name_base = (route_name_base[:52] + '-' + h)[:63]

        host = f"{slug}.{base_domain}"

        header_set = []
        if tenant_id:
            header_set.append({"name": "X-Tenant-Id", "value": tenant_id})
        if project_id:
            header_set.append({"name": "X-Project-Id", "value": project_id})

        route = {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "HTTPRoute",
            "metadata": {
                "name": route_name_base,
                "namespace": gateway_namespace,
                "labels": {
                    "app.kubernetes.io/name": "mlops-gateway",
                    "mlops-saas.io/tenant": "true",
                    "mlops-saas.io/tenant-slug": slug,
                },
            },
            "spec": {
                "parentRefs": [{"name": gateway_name}],
                "hostnames": [host],
                "rules": [
                    {
                        "matches": [{"path": {"type": "PathPrefix", "value": "/"}}],
                        "filters": (
                            [
                                {
                                    "type": "RequestHeaderModifier",
                                    "requestHeaderModifier": {"set": header_set},
                                }
                            ]
                            if header_set
                            else []
                        ),
                        "backendRefs": [
                            {
                                "name": backend_service,
                                "namespace": backend_namespace,
                                "port": backend_port,
                            }
                        ],
                    }
                ],
            },
        }

        items.append(route)

    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": items,
    }


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge two dicts.

    Nested dict values are merged recursively; all other override values replace base.
    """
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _normalize_ports(obj: object) -> list[dict] | None:
    """Normalize ingress ports config.

    Accepts:
      - None
      - list[int]  -> TCP ports
      - list[dict] -> [{"protocol":"TCP","port":8000}]
    """
    if obj is None:
        return None
    ports = _as_list(obj, "ingressPorts")
    normalized: list[dict] = []
    for p in ports:
        if isinstance(p, int):
            normalized.append({"protocol": "TCP", "port": p})
        elif isinstance(p, dict):
            if "port" not in p:
                raise SystemExit(f"Invalid ingress port entry (missing 'port'): {p}")
            normalized.append({
                "protocol": str(p.get("protocol") or "TCP").upper(),
                "port": p["port"],
            })
        else:
            raise SystemExit(f"Invalid ingress port entry: {p} (expected int or dict)")
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tenant-map-output", type=Path, default=DEFAULT_TENANT_MAP_OUTPUT)
    parser.add_argument("--tenant-routes-output", type=Path, default=DEFAULT_TENANT_ROUTES_OUTPUT)
    parser.add_argument("--tenant-domain", type=str, default="mlops.local")
    args = parser.parse_args()

    tenants, defaults = load_tenants_config(args.input)

    # Defaults
    quota_cfg = _as_dict(defaults.get("quota"), "defaults.quota")
    quota_override = _as_dict(quota_cfg.get("hard"), "defaults.quota.hard") if "hard" in quota_cfg else quota_cfg
    quota_hard = _deep_merge(DEFAULT_RESOURCE_QUOTA_HARD, quota_override)

    limit_cfg = defaults.get("limitRange") or defaults.get("limit_range") or defaults.get("limits")
    limit_cfg = _as_dict(limit_cfg, "defaults.limitRange")
    container_override = _as_dict(limit_cfg.get("container"), "defaults.limitRange.container") if "container" in limit_cfg else limit_cfg
    limit_container = _deep_merge(DEFAULT_LIMIT_RANGE_CONTAINER, container_override)
    if "type" not in limit_container:
        limit_container["type"] = "Container"

    network_cfg = _as_dict(defaults.get("network"), "defaults.network")
    network = _deep_merge(DEFAULT_NETWORK_POLICY, network_cfg)
    allowed_ingress_ns = _as_list(network.get("allowIngressFromNamespaces"), "allowIngressFromNamespaces")
    allowed_egress_ns = _as_list(network.get("allowEgressToNamespaces"), "allowEgressToNamespaces")
    exposed_labels = _as_dict(network.get("exposedPodLabels"), "exposedPodLabels")
    ingress_ports = _normalize_ports(network.get("ingressPorts"))

    # Ensure platform namespace access is always allowed (tenant workloads call platform APIs).
    if "mlops-system" not in allowed_egress_ns:
        allowed_egress_ns.append("mlops-system")

    docs: list[dict] = []

    for t in tenants:
        name = str(t["name"])
        tenant_id = str(t.get("tenant_id") or name)
        docs.append(namespace_doc(name, tenant_id))
        docs.append(resource_quota(name, quota_hard))
        docs.append(limit_range(name, limit_container))
        docs.append(default_deny_ingress(name))
        docs.append(default_deny_egress(name))
        docs.append(allow_same_namespace_traffic(name))
        docs.append(allow_dns(name))

        maybe_egress = allow_egress_to_namespaces(name, allowed_egress_ns)
        if maybe_egress:
            docs.append(maybe_egress)

        maybe_ingress = allow_ingress_from_namespaces(
            name,
            allowed_ingress_ns,
            exposed_pod_labels=exposed_labels or None,
            ports=ingress_ports,
        )
        if maybe_ingress:
            docs.append(maybe_ingress)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump_all(
            docs,
            sort_keys=False,
            explicit_start=True,
        )
    )

    tenant_map = tenant_map_configmap(tenants)
    args.tenant_map_output.parent.mkdir(parents=True, exist_ok=True)
    args.tenant_map_output.write_text(
        yaml.safe_dump(
            tenant_map,
            sort_keys=False,
        )
    )

    print(f"Wrote {len(docs)} resources to {args.output}")
    print(f"Wrote tenant map ConfigMap to {args.tenant_map_output}")

    tenant_routes = tenant_routes_manifest(tenants, base_domain=args.tenant_domain)
    args.tenant_routes_output.parent.mkdir(parents=True, exist_ok=True)
    args.tenant_routes_output.write_text(
        yaml.safe_dump(tenant_routes, sort_keys=False)
    )
    print(f"Wrote tenant HTTPRoutes to {args.tenant_routes_output}")


if __name__ == "__main__":
    main()
