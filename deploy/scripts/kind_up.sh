#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${1:-modelops-pro}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

kind create cluster --name "${CLUSTER_NAME}" --config "${ROOT_DIR}/kind/kind-config.yaml"

# Emulate GPU pools via labels/taints for a deterministic demo.
WORKERS=($(kubectl get nodes -o name | grep worker | sort))
PRO_NODE="${WORKERS[0]}"
ECO_NODE="${WORKERS[1]}"

kubectl label "${PRO_NODE}" atomicmail.ai/gpu-pool=gpu-pro-mig --overwrite
kubectl taint "${PRO_NODE}" atomicmail.ai/gpu-pro=true:NoSchedule --overwrite

kubectl label "${ECO_NODE}" atomicmail.ai/gpu-pool=gpu-econ-timeslice --overwrite
kubectl taint "${ECO_NODE}" atomicmail.ai/gpu-econ=true:NoSchedule --overwrite

echo "kind cluster ready: ${CLUSTER_NAME}"
echo "pro node: ${PRO_NODE}"
echo "econ node: ${ECO_NODE}"
