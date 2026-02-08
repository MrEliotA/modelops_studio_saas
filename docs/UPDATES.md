# Future updates

This file lists optional upgrades we did not implement in the MVP to keep the platform maintainable.

## Security

- **Auth verification mode**: `AUTH_MODE=passthrough` is demo-friendly but assumes a trusted edge.
  - Planned: `AUTH_MODE=jwt` to validate tokens end-to-end.
- **Image allowlist / supply-chain enforcement**: enable admission controls to restrict image registries and privileged settings.
  - Recommended: Kyverno `restrict-image-registries` style policies.
- **Per-tenant encryption** for artifacts/feature store (KMS-managed keys).

## UX / Tenancy

- **Tenant routing via subdomain/path** is supported in `control-plane-api`.
  - subdomain: `<tenant>.<TENANT_BASE_DOMAIN>`
  - path prefix: `/t/<tenant>/...`
  The slug -> UUID map is loaded from the generated ConfigMap `mlops-tenant-map`.

## Orchestration

- ✅ **YAML-only pipeline templates**: `template-service` ships allowlisted pipeline YAML packages from `services/template-service/catalog/`.
- ✅ **No in-cluster git clone/build**: `run-orchestrator` fetches pipeline YAML from template-service and submits to KFP.
- Planned: Pipeline-level policy gates (approve before deploy, drift checks, etc.).

## Serving

- **Gateway-level traffic splitting** for raw deployment mode (if not using KServe serverless).
- **Multi-model endpoints** with Triton model repo orchestration.
- **Async inference** (request queue + callback/webhook + DLQ).

## Observability

- **Per-tenant metrics isolation** via label-based RBAC or separate Prometheus instances.
- **SLO dashboards** (p99 latency, error budgets, saturation).

## Data & ML

- **Data validation gates** integrated with Feast + pipeline templates.
- **Bias/fairness reports** in eval-service.
