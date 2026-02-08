#!/usr/bin/env bash
set -euo pipefail

# Deploy platform services to kind.
# v2: No ingress. control-plane-api is exposed via NodePort (30080) in the kind overlay.

kubectl apply -k deploy/k8s/mlops-saas/overlays/kind

echo ""
echo "Platform will be ready when pods are Running."
echo "Access (kind): http://localhost:30080"
echo "Example (tenant-aware via Host header):"
echo "  curl -H 'Host: tenant-a.mlops.local' -H 'X-User-Id: demo' -H 'X-Roles: admin' http://localhost:30080/api/v1/overview"


echo "Access via API gateway (after installing Envoy Gateway):"
echo "  ./scripts/kind/port-forward-gateway.sh"
echo "  curl -H 'Host: tenant-a.mlops.local' http://localhost:30081/api/v1/overview"
