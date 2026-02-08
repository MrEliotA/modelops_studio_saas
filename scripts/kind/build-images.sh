#!/usr/bin/env bash
set -euo pipefail

# Build all microservices used by the KIND overlay.
# IMPORTANT: For kind demos we default to local image names (mlops/*:dev) so `kind load` works without a registry.
services=(
  # core
  template-service run-service training-service registry-service artifact-service
  deployment-service serving-service metering-service control-plane-api

  # event/feature pipeline
  stream-ingest-service feature-store-service

  # GPU queue (CPU-only demo mode via KIND patches)
  gpu-jobs-service gpu-scheduler-service

  # LLM/RAG demos
  llm-embeddings-service llm-rag-service llm-eval-service llm-labeling-service
)
for s in "${services[@]}"; do
  echo "==> building ${s}"
  docker build -f "services/${s}/Dockerfile" -t "mlops/${s}:dev" .
done

# Build workers
workers=(
  run-orchestrator training-worker deploy-worker metering-worker
  stream-feast-writer gpu-runner
)
for w in "${workers[@]}"; do
  echo "==> building ${w}"
  docker build -f "workers/${w}/Dockerfile" -t "mlops/${w}:dev" .
done

# Build nats bootstrap job image
echo "==> building nats-bootstrap"
docker build -f "deploy/nats-bootstrap/Dockerfile" -t "mlops/nats-bootstrap:dev" .
