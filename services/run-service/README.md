# run-service

Owns **Runs** (template-driven pipeline runs).

- `POST /api/v1/runs` creates a run and publishes an event to NATS JetStream:
  - subject: `mlops.runs.requested`
- `GET /api/v1/runs` list runs
- `GET /api/v1/runs/{id}` run status

## Event flow (dev)
`run-orchestrator` worker consumes `mlops.runs.requested` and simulates a KFP run by moving run status:
`QUEUED → RUNNING → SUCCEEDED`

## Env
- `DATABASE_URL` (required)
- `NATS_URL` (required)

