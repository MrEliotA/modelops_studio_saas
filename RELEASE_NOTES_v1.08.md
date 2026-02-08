# Release notes — v1.08

## Serving

- **Triton runtime support** (KServe modelFormat=triton) + examples
- **KServe request batching** support (batcher field) + Triton dynamic batching example (`config.pbtxt`)
- **Real deploy-worker** (`DEPLOY_MODE=k8s`) that applies `InferenceService` and waits for readiness
- **Canary rollout support** via `spec.predictor.canaryTrafficPercent` (Knative deployment mode)
- New docs: `docs/SERVING.md`

## Platform schema

- Added `endpoints.runtime_config` (JSONB) for extensible serving options
  - Migration: `migrations/0007_endpoints_runtime_config.sql`

## API

- `PATCH /api/v1/endpoints/{endpoint_id}` to update model version / traffic / autoscaling / runtime config
- OpenAPI updated: `openapi/registry-service.openapi.yaml`

## CI

- GitHub Actions: `.github/workflows/ci.yml` (compileall + compose e2e)
- GitLab CI: `.gitlab-ci.yml` (compileall + compose e2e)

## Examples

- Triton model repo + upload script: `examples/triton/`
- KServe Triton manifests: `examples/kserve/inferenceservice-triton*.yaml`

## Deferred ideas

See `docs/UPDATES.md`.
