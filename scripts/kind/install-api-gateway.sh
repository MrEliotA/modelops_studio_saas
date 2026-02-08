#!/usr/bin/env bash
set -euo pipefail

# Install Envoy Gateway (Gateway API) for KIND demos.
# Requires:
#  - helm v3
#  - kubectl

EG_VERSION="${EG_VERSION:-1.6.3}"

echo "[api-gateway] install Gateway API + Envoy Gateway CRDs (EnvoyProxy + Gateway API standard channel)"
helm upgrade --install envoy-gateway-crds \
  oci://registry-1.docker.io/envoyproxy/gateway-crds-helm \
  --version "${EG_VERSION}" \
  -n envoy-gateway-system \
  --create-namespace \
  --set crds.envoyGateway.enabled=true \
  --set crds.gatewayAPI.enabled=true \
  --set crds.gatewayAPI.channel=standard

echo "[api-gateway] install Envoy Gateway controller"
helm upgrade --install envoy-gateway \
  oci://registry-1.docker.io/envoyproxy/gateway-helm \
  --version "${EG_VERSION}" \
  -n envoy-gateway-system \
  --create-namespace

echo "[api-gateway] apply tenant-aware gateway resources"
kubectl apply -k deploy/k8s/api-gateway/overlays/kind

