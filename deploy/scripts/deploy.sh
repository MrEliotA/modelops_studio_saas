#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${1:-modelops-system}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "${NAMESPACE}" apply -f "${ROOT_DIR}/k8s/postgres.yaml"
kubectl -n "${NAMESPACE}" apply -f "${ROOT_DIR}/k8s/minio.yaml"
kubectl -n "${NAMESPACE}" apply -f "${ROOT_DIR}/k8s/api.yaml"
kubectl -n "${NAMESPACE}" apply -f "${ROOT_DIR}/k8s/controller.yaml"
kubectl -n "${NAMESPACE}" apply -f "${ROOT_DIR}/k8s/agent.yaml"

echo "Deployed into namespace: ${NAMESPACE}"
kubectl -n "${NAMESPACE}" get pods
