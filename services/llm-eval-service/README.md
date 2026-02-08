# llm-eval-service

A minimal, production-friendly **evaluation microservice** for model/LLM outputs.

It computes common metrics and stores evaluation runs in Postgres for later inspection.

## API

### Create an evaluation run

`POST /api/v1/eval`

Request:
- `task`: `classification | regression | exact_match | retrieval`
- `predictions`: list
- `labels`: list (same length as predictions)
- optional `options`: object (e.g., `{ "k": 10 }` for retrieval)
- optional `model_version_id`: uuid (to link results to the model registry)

Response:
- `id`, `task`, `metrics`, `details`, `created_at`, ...

### List runs

- `GET /api/v1/eval/runs?limit=50`
- `GET /api/v1/eval/runs/{run_id}`

## Notes

- This service is designed to be called from pipelines (post-training) and from online monitoring (sampling).
- For more “SageMaker-like” dashboards, you can push the stored metrics into Prometheus/Grafana or a BI store.
