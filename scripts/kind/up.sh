#!/usr/bin/env bash
set -euo pipefail

# One-command KIND demo setup.
#
# Creates a kind cluster, installs tenant namespaces/policies (no ingress), builds/loads images,
# deploys the platform (KIND overlay), runs DB migrations, and executes a smoke test.
#
# Tunables:
#   CLUSTER_NAME=mlops
#   
#   SKIP_BUILD=1      (skip docker build)
#   SKIP_LOAD=1       (skip kind load)
#   SKIP_SMOKE=1      (skip smoke test)

SKIP_BUILD="${SKIP_BUILD:-0}"
SKIP_LOAD="${SKIP_LOAD:-0}"
SKIP_SMOKE="${SKIP_SMOKE:-0}"

echo "[up] create cluster"
./scripts/kind/create-cluster.sh

echo "[up] install tenant isolation policies (NetworkPolicy)"
./scripts/kind/install-networking.sh

if [[ "$SKIP_BUILD" != "1" ]]; then
  echo "[up] build images"
  ./scripts/kind/build-images.sh
else
  echo "[up] SKIP_BUILD=1"
fi

if [[ "$SKIP_LOAD" != "1" ]]; then
  echo "[up] load images"
  ./scripts/kind/load-images.sh
else
  echo "[up] SKIP_LOAD=1"
fi

echo "[up] deploy platform"
./scripts/kind/deploy.sh

echo "[up] bootstrap DB (migrations)"
./scripts/kind/bootstrap-db.sh

echo "[up] install API gateway (Envoy Gateway)"
./scripts/kind/install-api-gateway.sh

if [[ "$SKIP_SMOKE" != "1" ]]; then
  echo "[up] run smoke test"
  ./scripts/kind/smoke-test.sh
else
  echo "[up] SKIP_SMOKE=1"
fi

echo ""

cat <<"EOF"

Demo usage (direct NodePort, no gateway):
  tenant-a: curl -H "Host: tenant-a.mlops.local" http://localhost:30080/api/v1/overview

Demo usage (via API gateway):
  1) In one terminal:
       ./scripts/kind/port-forward-gateway.sh
  2) In another terminal:
       curl -H "Host: tenant-a.mlops.local" http://localhost:30081/api/v1/overview
EOF
