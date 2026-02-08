# training-service

Owns **Training Jobs** (GPU pool selection + job submission).

This runnable dev version:
- stores training job intents in Postgres (`training_jobs`)
- validates `compute_profile` against a YAML catalog (simulates ConfigMap-based selection)
- publishes `mlops.training.requested` to NATS JetStream

Endpoints:
- `GET /api/v1/compute-profiles`
- `POST /api/v1/training-jobs`
- `GET /api/v1/training-jobs`
- `GET /api/v1/training-jobs/{id}`

## Env
- `DATABASE_URL` (required)
- `NATS_URL` (required)
- `COMPUTE_PROFILES_PATH` (default: `/app/config/compute_profiles.yaml` in container)

## Worker
`training-worker` consumes `mlops.training.requested` and simulates:
`QUEUED → RUNNING → SUCCEEDED`

