#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${1:-monitoring}"

kubectl -n "${NAMESPACE}" apply -f deploy/addons/observability/k8s/dashboards/cm-admin-overview.yaml
kubectl -n "${NAMESPACE}" apply -f deploy/addons/observability/k8s/dashboards/cm-user-runtime.yaml
kubectl -n "${NAMESPACE}" apply -f deploy/addons/observability/k8s/dashboards/cm-admin-pools.yaml
kubectl -n "${NAMESPACE}" apply -f deploy/addons/observability/k8s/dashboards/cm-admin-gpu-node.yaml

echo "Dashboards applied into namespace=${NAMESPACE}"
