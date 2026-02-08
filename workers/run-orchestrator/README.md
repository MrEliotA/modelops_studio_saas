# run-orchestrator worker

Consumes:
- `mlops.runs.requested` (JetStream)

## Backends

This worker supports two orchestration backends:

1) **local** (default, MVP)
- Simulates a pipeline run by sleeping and then setting `runs.status=SUCCEEDED`.

2) **kfp** (Kubeflow Pipelines)
- Fetches a **YAML-only pipeline package** from template-service:
  - `GET /api/v1/templates/{template_id}/package`
- Submits it to KFP via `create_run_from_pipeline_package`.
- Stores `runs.kfp_run_id` and reconciles run state.

### Security note (v2 goal)

This worker **does not**:
- git clone user repos
- run a compiler

Only pre-approved YAML-only templates can be executed.

## Configuration

Environment variables:

- `PIPELINE_BACKEND`: `local | kfp`
- `KFP_HOST`: e.g. `http://ml-pipeline.kubeflow:8888`
- `KFP_NAMESPACE`: defaults to `kubeflow`
- `KFP_POLL_INTERVAL_SECONDS`: defaults to `10`

Template-service:

- `TEMPLATE_SERVICE_BASE_URL`: defaults to `http://template-service:8000`
- `TEMPLATE_SERVICE_TIMEOUT_SECONDS`: defaults to `10`

Service identity (passthrough MVP):
- `SYSTEM_USER_ID`: defaults to `system:run-orchestrator`
- `SYSTEM_ROLES`: defaults to `system`

## State transitions

- `QUEUED` → `RUNNING` (on event consumption)
- `RUNNING` → `SUCCEEDED | FAILED | CANCELLED` (via KFP reconciler)
