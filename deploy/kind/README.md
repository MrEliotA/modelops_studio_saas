# kind (demo)

This environment is for **CPU-only demos** on a laptop/desktop.

v2 notes:
- `ingress-nginx` was removed.
- The repo standardizes on **Cilium** for NetworkPolicy enforcement.
- Tenant-aware routing is done via **Gateway API** (Envoy Gateway) using `*.mlops.local`.

## Requirements
- Docker
- kind
- kubectl
- helm v3

## Quickstart

```bash
./scripts/kind/up.sh
```

## Access

### Direct (NodePort)

The `control-plane-api` Service is exposed as NodePort `30080` in KIND.

```bash
curl -H "Host: tenant-a.mlops.local" http://localhost:30080/api/v1/overview
```

### Via API Gateway (Envoy Gateway)

1) In one terminal:

```bash
./scripts/kind/port-forward-gateway.sh
```

2) In another terminal:

```bash
curl -H "Host: tenant-a.mlops.local" http://localhost:30081/api/v1/overview
```

## Tenants

Tenant namespaces and isolation policies are generated from:
- `deploy/tenants/tenants.yaml`

Run:

```bash
python scripts/generate_tenant_manifests.py
```

Generated outputs:
- `deploy/k8s/networking/tenants/generated/tenants.generated.yaml`
- `deploy/k8s/api-gateway/generated/tenant-httproutes.generated.yaml`
