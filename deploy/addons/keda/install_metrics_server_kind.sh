#!/usr/bin/env bash
set -euo pipefail

# metrics-server is required for CPU-based autoscaling triggers.
# This uses the upstream manifest. For kind, we also patch args to work with self-signed certs.

kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Patch metrics-server for kind (insecure TLS to kubelets).
kubectl -n kube-system patch deploy metrics-server --type='json' -p='[
  {"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"},
  {"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-preferred-address-types=InternalIP,ExternalIP,Hostname"}
]'

echo "metrics-server installed/updated."
