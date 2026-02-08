# Serving (KServe + Triton + Canary)

This repo integrates **KServe** as the model serving control plane.

You can run serving in two practical modes:

## 1) Standard / Raw deployment (bare-metal friendly)

- **DeploymentMode**: RawDeployment (aka "standard" mode)
- **Autoscaling**: KEDA (optional)
- **Use-cases**: GPU inference on bare-metal clusters without Knative

Example:
- `examples/kserve/inferenceservice-triton.yaml`

## 2) Serverless / Knative (required for Canary)

- **DeploymentMode**: Knative (serverless)
- **Autoscaling**: Knative autoscaler (scale-to-zero)
- **Canary**: revision-based rollout via `spec.predictor.canaryTrafficPercent`

Example:
- `examples/kserve/inferenceservice-triton-canary.yaml`

> Canary rollouts are a serverless feature in KServe.

## Rollout workflows (Canary / A-B / Blue-Green)

This repo exposes **YAML-only** KFP pipeline templates (no user builds) that update a deployment intent
in `deployment-service`. The `deploy-worker` then reconciles the updated intent into a KServe `InferenceService`.

Templates (see `services/template-service/catalog/catalog.yaml`):

- **Canary**: `rollout-canary` (set `canary_percent` gradually: 1 → 5 → 10 → 25 → 50)
- **A/B**: `rollout-ab` (50/50 split)
- **Blue/Green**:
  - `rollout-blue-green-stage` (stage green with 0% traffic)
  - `rollout-blue-green-promote` (promote green by clearing canaryTrafficPercent)

### Policy guardrails

If `deploy/k8s/policies/kyverno/validate-kserve-rollout-tenants.yaml` is installed, tenant namespaces
get rollout guardrails:

- `canaryTrafficPercent` must be **0-100**
- canary rollouts must set `serving.kserve.io/deploymentMode=Knative`
- Triton must use `protocolVersion=v2`

## Triton runtime (standard GPU model server)

KServe can run NVIDIA Triton via the built-in Triton ServingRuntime.

This repo includes a minimal **Triton Python backend** model repository:
- `examples/triton/model-repository/add_sub`
  - `config.pbtxt` enables **dynamic batching**
  - `1/model.py` implements the model

### Upload Triton model repo to MinIO (dev)

Start the dev stack:
```bash
docker compose up -d --build
./scripts/dev-bootstrap.sh
```

Upload model repository:
```bash
./examples/triton/upload-to-minio.sh
```

Now `storageUri: s3://mlops-artifacts/triton/add_sub` is resolvable by KServe storage initializer (if configured).

## Endpoint runtime_config

Endpoints live in Postgres. The `deploy-worker` maps endpoint config to an `InferenceService`.

Example endpoint payload:
```json
{
  "name": "demo-triton",
  "model_id": "...",
  "model_version_id": "...",
  "runtime": "kserve-triton",
  "autoscaling": {"minReplicas": 1, "maxReplicas": 4, "keda": true},
  "runtime_config": {
    "modelFormat": "triton",
    "protocolVersion": "v2",
    "runtimeVersion": "24.08-py3",
    "gpu": true,
    "batcher": {"maxBatchSize": 32, "maxLatency": 500}
  }
}
```

## Installation notes (prod)

Follow the official KServe docs for the recommended installation paths:
- Serverless (Knative/Istio): install Knative Serving, networking, cert-manager, then KServe
- Raw/standard deployment: install KServe with `RawDeployment` as default mode

