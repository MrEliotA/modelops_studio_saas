#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${1:-modelops-system}"

kubectl -n "${NAMESPACE}" port-forward svc/modelops-api 18000:80 >/tmp/pf-modelops-api.log 2>&1 &
PF_PID=$!
trap "kill ${PF_PID} || true" EXIT
sleep 2

python3 deploy/scripts/run_demo.py --api http://127.0.0.1:18000
echo "Demo completed."
