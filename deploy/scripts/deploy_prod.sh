#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${1:-modelops-system}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# Production manifests (PVC-backed).
kubectl -n "${NAMESPACE}" apply -f "${ROOT_DIR}/modes/prod/k8s/postgres.yaml"
kubectl -n "${NAMESPACE}" apply -f "${ROOT_DIR}/modes/prod/k8s/minio.yaml"
kubectl -n "${NAMESPACE}" apply -f "${ROOT_DIR}/modes/prod/k8s/api.yaml"
kubectl -n "${NAMESPACE}" apply -f "${ROOT_DIR}/modes/prod/k8s/controller.yaml"
kubectl -n "${NAMESPACE}" apply -f "${ROOT_DIR}/modes/prod/k8s/agent.yaml"

echo "Deployed (prod mode) into namespace: ${NAMESPACE}"
kubectl -n "${NAMESPACE}" get pods
