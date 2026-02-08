#!/usr/bin/env bash
set -euo pipefail

# Creates a kind cluster for demos.
#
# This project standardizes on **Cilium** for NetworkPolicy enforcement.
# The kind cluster is created with `disableDefaultCNI: true` (see deploy/kind/kind-config.yaml)
# and Cilium is installed immediately after.

CLUSTER_NAME=${CLUSTER_NAME:-mlops}
CILIUM_CHART_VERSION=${CILIUM_CHART_VERSION:-1.19.0}

kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
kind create cluster --name "${CLUSTER_NAME}" --config deploy/kind/kind-config.yaml

echo "[kind] Cluster '${CLUSTER_NAME}' created."

echo "[kind] Installing Cilium ${CILIUM_CHART_VERSION} (NetworkPolicy enforcement)..."
# Requires: helm v3
helm upgrade --install cilium \
  oci://quay.io/cilium/charts/cilium \
  --version "${CILIUM_CHART_VERSION}" \
  --namespace kube-system \
  --set ipam.mode=kubernetes \
  --set hubble.enabled=false \
  --set operator.replicas=1

kubectl rollout status -n kube-system ds/cilium --timeout=300s
kubectl rollout status -n kube-system deploy/cilium-operator --timeout=300s

echo "[kind] Cilium is ready."
