# Networking

This folder contains Kubernetes networking manifests that support:
- **Per-tenant isolation** via `NetworkPolicy`
- A simple **tenant onboarding generator** (YAML -> manifests)

## Tenant onboarding at scale (~1000 tenants)

Standard Kubernetes `NetworkPolicy` does **not** support selecting other namespaces directly, so a common GitOps pattern is:
1) Keep a single source-of-truth list of tenants
2) Generate per-namespace resources (Namespace + NetworkPolicy + quotas, etc.)
3) Commit the generated YAML and let ArgoCD sync it

We follow that pattern.

### Files

- Input: `deploy/tenants/tenants.yaml`
- Generator: `scripts/generate_tenant_manifests.py`
- Output: `deploy/k8s/networking/tenants/generated/tenants.generated.yaml`

### Run generator

```bash
python scripts/generate_tenant_manifests.py \
  --in deploy/tenants/tenants.yaml \
  --out deploy/k8s/networking/tenants/generated/tenants.generated.yaml
```

## CNI choice (v2): Cilium

This repo standardizes on **Cilium** as the production CNI.

Notes:
- For portability, the tenant isolation primitives in this repo are implemented using standard Kubernetes `NetworkPolicy`.
- If you later decide to use Cilium-specific policies (e.g., `CiliumClusterwideNetworkPolicy`) to reduce manifest volume, keep that as a vNext optimization.

See:
- `deploy/k8s/networking/cilium/`
