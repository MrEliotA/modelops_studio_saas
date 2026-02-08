#!/usr/bin/env bash
set -euo pipefail

# Port-forward the Envoy proxy Service created for the mlops-gateway.
# This is the easiest way to access the Gateway on kind.

LOCAL_PORT="${LOCAL_PORT:-30081}"
GW_NS="${GW_NS:-gateway-system}"
GW_NAME="${GW_NAME:-mlops-gateway}"
PROXY_NS="${PROXY_NS:-envoy-gateway-system}"
PROXY_PORT="${PROXY_PORT:-80}"

selector="gateway.envoyproxy.io/owning-gateway-name=${GW_NAME},gateway.envoyproxy.io/owning-gateway-namespace=${GW_NS}"

svc="$(kubectl -n "${PROXY_NS}" get svc -l "${selector}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "${svc}" ]]; then
  echo "[gateway] could not find proxy Service for ${GW_NS}/${GW_NAME} in namespace ${PROXY_NS}"
  kubectl -n "${PROXY_NS}" get svc -o wide
  exit 1
fi

echo "[gateway] port-forward svc/${svc} ${LOCAL_PORT}:${PROXY_PORT} (Ctrl+C to stop)"
exec kubectl -n "${PROXY_NS}" port-forward "svc/${svc}" "${LOCAL_PORT}:${PROXY_PORT}"
