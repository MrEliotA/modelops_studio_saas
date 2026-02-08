#!/usr/bin/env bash
set -euo pipefail

# v2: ingress-based tenant routers are removed.
# For kind demos:
#   - Direct NodePort: control-plane-api is exposed via NodePort (30080) and you can set Host header.
#   - Via API gateway: port-forward the Envoy proxy Service and set Host header.

cat <<"EOF"
No Ingress resources to apply.

Direct (NodePort):
  curl -H "Host: tenant-a.mlops.local" http://localhost:30080/api/v1/overview

Via API gateway:
  # terminal 1
  ./scripts/kind/port-forward-gateway.sh

  # terminal 2
  curl -H "Host: tenant-a.mlops.local" http://localhost:30081/api/v1/overview
EOF
