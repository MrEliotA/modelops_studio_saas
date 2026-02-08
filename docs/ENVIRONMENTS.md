# Environments

This repo supports three execution modes:

- **docker-compose** (local dev): fast iteration, no Kubernetes, no GPU integration.
- **kind** (demo): runs on a local Kubernetes-in-Docker cluster, no GPU integration.
- **production** (bare-metal Kubernetes + ArgoCD): full platform, including GPU Operator for GPU node pools.

## GPU support

GPU integration is **production-first** in this repo.
See `docs/GPU.md`, `docs/GPU_QUEUE.md`, and `docs/GPU_SCHEDULER.md`.

## Serving (KServe)

- Docker Compose: `deployment-worker` runs with `DEPLOY_MODE=simulate`.
- Kubernetes production: set `DEPLOY_MODE=k8s` and install KServe.

See: `docs/SERVING.md`.

## kind demo

For CTO/CEO demos we keep the kind stack minimal (no MetalLB). The helper script:

```bash
./scripts/kind/up.sh
```

performs:
- creates a kind cluster
- installs **Cilium** (NetworkPolicy enforcement)
- applies tenant namespaces / quotas / NetworkPolicies
- builds and loads images
- deploys the KIND overlay
- runs DB migrations
- installs the API Gateway (Envoy Gateway)
- runs a smoke test

At the end, it prints demo hints like:

- Direct NodePort: `curl -H "Host: tenant-a.mlops.local" http://localhost:30080/api/v1/overview`
- Via API Gateway: `curl -H "Host: tenant-a.mlops.local" http://localhost:30081/api/v1/overview` (after `./scripts/kind/port-forward-gateway.sh`)

### NetworkPolicy enforcement in kind

KIND is created with `disableDefaultCNI: true` and **Cilium** is installed automatically, so standard Kubernetes `NetworkPolicy` is enforced in the demo cluster.

## Tenant manifests generation

Tenant namespaces and policies are generated from a declarative file.

- input: `deploy/tenants/tenants.yaml`
- example for 1000 tenants: `deploy/tenants/tenants.example-1000.yaml`
- generator: `scripts/generate_tenant_manifests.py`

Generated outputs (tracked for GitOps):
- `deploy/k8s/networking/tenants/generated/tenants.generated.yaml`
- `deploy/k8s/mlops-saas/base/tenant-map-configmap.generated.yaml`

NOTE: Ingress has been removed in v2. Gateway API + API Gateway is used instead.
