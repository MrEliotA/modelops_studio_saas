# registry-service

Owns:
- `models` and `model_versions` (internal façade)
- `endpoints` (deployment intents)

In production you may split:
- registry-service (MLflow registry façade)
- deployment-service / serving-service (KServe intents)

This runnable dev version includes all 3 for a working happy-path.

## MLflow integration (optional)
If `MLFLOW_TRACKING_URI` is provided, the service will:
- create a registered model (name scoped by tenant/project)
- register model versions

If not, it still stores everything in Postgres.

## Events
- When an endpoint is created, publish `mlops.serving.deploy_requested` so `deploy-worker` can simulate readiness.

## Env
- `DATABASE_URL` (required)
- `NATS_URL` (required)
- `MLFLOW_TRACKING_URI` (optional)

