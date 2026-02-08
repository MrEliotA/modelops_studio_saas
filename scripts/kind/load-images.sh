#!/usr/bin/env bash
set -euo pipefail
CLUSTER_NAME="${KIND_CLUSTER_NAME:-mlops}"

images=(
  mlops/template-service:dev mlops/run-service:dev mlops/training-service:dev mlops/registry-service:dev
  mlops/artifact-service:dev mlops/deployment-service:dev mlops/serving-service:dev mlops/metering-service:dev
  mlops/control-plane-api:dev mlops/llm-embeddings-service:dev mlops/llm-rag-service:dev mlops/llm-eval-service:dev
  mlops/llm-labeling-service:dev
  mlops/run-orchestrator:dev mlops/training-worker:dev mlops/deploy-worker:dev mlops/metering-worker:dev
  mlops/stream-ingest-service:dev mlops/stream-feast-writer:dev mlops/feature-store-service:dev
  mlops/gpu-jobs-service:dev mlops/gpu-scheduler-service:dev mlops/gpu-runner:dev
  mlops/nats-bootstrap:dev
)

for img in "${images[@]}"; do
  echo "==> loading ${img}"
  kind load docker-image --name "${CLUSTER_NAME}" "${img}"
done
