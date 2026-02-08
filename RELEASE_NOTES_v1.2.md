# Release Notes — v1.2

## Fixed ("خرابی‌های قطعی")

### Control-plane BFF
- **Training route mismatch:** BFF now proxies training endpoints to the correct upstream path (`/api/v1/training-jobs`). A compatibility alias is also available at `/training-jobs`.

### Template Service
- **Completed CRUD:** Implemented `PUT /api/v1/templates/{template_id}` and `DELETE /api/v1/templates/{template_id}` to match what the BFF exposes.

### Artifact Service
- **Artifacts GET:** Implemented `GET /api/v1/artifacts` (list) — BFF already exposed `GET /artifacts`.

### Deployment Service
- **No longer empty:** Implemented `POST/GET/PUT/DELETE /api/v1/deployments` backed by the `endpoints` table.
- Publishes `mlops.serving.deploy_requested` on create/update of serving-relevant fields.
- Publishes `mlops.serving.delete_requested` on delete and soft-deletes by renaming to free unique name constraints.

### GPU Jobs
- **SQL placeholder bug:** Fixed INSERT placeholder count mismatch in gpu-jobs-service.

### Feature Store
- **Missing function bug:** feature-store-service no longer imports/uses a non-existent `get_db()`; it uses `app.state.db_pool` provided by the shared app factory.

## Ops / Deployment hardening

### Kustomize secrets safety
- Removed in-repo secrets from the base deployments.
- Added `*.example.yaml` secret manifests (not referenced by default) for guidance.

### Feast secrets
- Feast kustomization no longer applies secrets by default. Use your secret manager or apply `deploy/k8s/feast/secrets.example.yaml` for local demos.

### Docker Compose
- `stream-ingest-service` now depends on Postgres (in addition to NATS).

### NATS bootstrap
- `scripts/bootstrap_nats.py` now reuses the shared `DEFAULT_STREAMS` via `mlops_common.nats_client.ensure_streams`.
