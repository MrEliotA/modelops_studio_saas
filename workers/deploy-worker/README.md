# deploy-worker

This worker turns an **endpoint intent** (stored in Postgres) into a real **KServe InferenceService**.

It consumes JetStream events:
- `mlops.serving.deploy_requested`

## Modes

### `DEPLOY_MODE=simulate` (default in Docker Compose)

- Does **not** talk to Kubernetes.
- Marks the endpoint as `READY` and sets a fake URL like:
  `http://isvc-<endpoint_id_prefix>.example.local`

This keeps local dev fast and dependency-free.

### `DEPLOY_MODE=k8s` (real KServe deploy)

- Uses **in-cluster** Kubernetes API (ServiceAccount token).
- Creates/updates a `serving.kserve.io/v1beta1` `InferenceService`.
- Waits until `status.url` is set and Ready condition becomes `True`.

Env:
- `KSERVE_NAMESPACE` (default: `mlops-serving`)
- `KSERVE_NAME_PREFIX` (default: `isvc`)
- `DEPLOY_TIMEOUT_SECONDS` (default: `600`)

## Endpoint -> KServe mapping

The worker reads these DB fields:
- `endpoints.runtime` (string)
- `endpoints.traffic` (jsonb)
- `endpoints.autoscaling` (jsonb)
- `endpoints.runtime_config` (jsonb)
- `model_versions.artifact_uri` (used as `storageUri`)

### Triton runtime (standard GPU model server)

Set endpoint `runtime` to include `triton` (e.g., `kserve-triton`) or set `runtime_config.modelFormat=triton`.

Typical `runtime_config`:
```json
{
  "modelFormat": "triton",
  "protocolVersion": "v2",
  "runtimeVersion": "24.08-py3",
  "gpu": true,
  "resources": {
    "requests": {"cpu":"500m","memory":"2Gi","nvidia.com/gpu":1},
    "limits":   {"cpu":"2","memory":"4Gi","nvidia.com/gpu":1}
  },
  "batcher": {"maxBatchSize": 32, "maxLatency": 500}
}
```

> Triton **dynamic batching** is configured inside the model repo (`config.pbtxt`). See `examples/triton/`.

### Canary (serverless / Knative)

KServe canary traffic splitting is implemented via:
- `spec.predictor.canaryTrafficPercent`

To enable canary, set `traffic.canaryTrafficPercent` on the endpoint and deploy a *new* model version.
Example patch:
```json
{
  "model_version_id": "<new_version_uuid>",
  "traffic": {"canaryTrafficPercent": 10},
  "runtime_config": {"deploymentMode": "Knative"}
}
```

Notes:
- Canary rollouts are a **Knative/serverless** feature (revision-based).
- KEDA autoscaling is typically used with **RawDeployment** mode.

## Prometheus scraping

The worker adds `serving.kserve.io/enable-prometheus-scraping: "true"` by default (configurable).

