#!/usr/bin/env bash
set -euo pipefail

# Recommended install method: Helm.
# Docs: https://keda.sh/docs/latest/deploy/

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required to install KEDA via this script."
  echo "Install helm, or install KEDA manually using the official docs."
  exit 1
fi

kubectl create namespace keda --dry-run=client -o yaml | kubectl apply -f -

helm repo add kedacore https://kedacore.github.io/charts
helm repo update

# Pin a version for reproducibility. You can upgrade later.
helm upgrade --install keda kedacore/keda --namespace keda --version 2.18.2

echo "KEDA installed in namespace 'keda'."
