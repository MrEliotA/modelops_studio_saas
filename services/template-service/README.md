# template-service

Owns **Templates** (pipeline/training templates). In production, this would manage:
- template catalog
- versioning (git SHA)
- compilation (KFP/MLflow projects templates)

This runnable dev version implements:
- `POST /api/v1/templates`
- `GET /api/v1/templates`
- `GET /api/v1/templates/{id}`

## Shared concerns
This service uses the shared library `mlops-common`:
- Tenancy headers (required)
- Idempotency (optional header `Idempotency-Key`)
- Structured logging and OTel tracing

## Environment
- `DATABASE_URL` (required)
- `NATS_URL` (optional; used for emitting template events in future)

## Example
### KFP pipeline template (recommended)
When `PIPELINE_BACKEND=kfp`, the run-orchestrator expects templates to point to a **compiled KFP pipeline package** (YAML).

Recommended fields:
- `git_repo`: Git URL (HTTPS recommended)
- `git_ref`: git commit SHA / tag / branch
- `entrypoint`: path to the compiled pipeline YAML within the repo
- `compiler`: any value that starts with `kfp` (e.g. `kfp-yaml`, `kfp-v2`)

```bash
curl -X POST http://localhost:8001/api/v1/templates \
  -H "X-Tenant-Id: 00000000-0000-0000-0000-000000000001" \
  -H "X-Project-Id: 00000000-0000-0000-0000-000000000002" \
  -H "X-User-Id: user@example.com" \
  -H "Idempotency-Key: 11111111-1111-1111-1111-111111111111" \
  -H "Content-Type: application/json" \
  -d '{"name":"demo","git_repo":"https://git/repo","git_ref":"main","entrypoint":"pipelines/my_pipeline.yaml","compiler":"kfp-yaml","default_parameters":{"epochs":1}}'
```

## YAML-only template catalog (v2)

This service supports a built-in, YAML-only template catalog for supply-chain safety.

- Catalog index: `services/template-service/catalog/catalog.yaml`
- Pipeline packages: `services/template-service/catalog/pipelines/*.yaml`

When `TEMPLATE_MODE=catalog`, mutating endpoints (`POST/PUT/DELETE /templates`) are disabled and templates are seeded per tenant/project from the catalog.

### Included serving templates

- `kserve-deploy-triton` - create a KServe Triton deployment intent
- `rollout-canary` - set canary percent (0-100)
- `rollout-ab` - 50/50 traffic split
- `rollout-blue-green-stage` - stage new revision with 0% traffic
- `rollout-blue-green-promote` - promote staged revision by clearing canary percent
