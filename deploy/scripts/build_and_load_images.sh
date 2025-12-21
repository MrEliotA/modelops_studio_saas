#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${1:-modelops-pro}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "Building images..."
docker build -t modelops/api:dev -f "${ROOT_DIR}/apps/api/Dockerfile" "${ROOT_DIR}"
docker build -t modelops/controller:dev -f "${ROOT_DIR}/apps/controller/Dockerfile" "${ROOT_DIR}"
docker build -t modelops/agent:dev -f "${ROOT_DIR}/apps/agent/Dockerfile" "${ROOT_DIR}"
docker build -t modelops/trainer:dev -f "${ROOT_DIR}/apps/workloads/trainer/Dockerfile" "${ROOT_DIR}"
docker build -t modelops/serving:dev -f "${ROOT_DIR}/apps/workloads/serving/Dockerfile" "${ROOT_DIR}"

echo "Loading images into kind..."
kind load docker-image --name "${CLUSTER_NAME}" modelops/api:dev
kind load docker-image --name "${CLUSTER_NAME}" modelops/controller:dev
kind load docker-image --name "${CLUSTER_NAME}" modelops/agent:dev
kind load docker-image --name "${CLUSTER_NAME}" modelops/trainer:dev
kind load docker-image --name "${CLUSTER_NAME}" modelops/serving:dev

echo "Images loaded."
