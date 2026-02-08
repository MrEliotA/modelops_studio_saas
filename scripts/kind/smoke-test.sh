#!/usr/bin/env bash
set -euo pipefail

# Smoke-test for KIND demo.
#
# هدف: مطمئن شویم دمو برای CTO/CEO "بالا" است و چند flow اصلی کار می‌کند:
# - Templates CRUD
# - Runs orchestration (demo worker)
# - Training jobs (BFF route)
# - Artifacts list/create
# - Deployments create -> READY (async)
# - GPU queue (simulate) + Feature-store admin route
#
# خروجی به صورت کوتاه و demo-friendly است. برای لاگ کامل:
#   VERBOSE=1 ./scripts/kind/smoke-test.sh

NS="${NS:-mlops-system}"
BASE_URL="${BASE_URL:-http://localhost:30080}"
VERBOSE="${VERBOSE:-0}"
TENANT_SLUG="${TENANT_SLUG:-tenant-a}"
HOST_HEADER="${HOST_HEADER:-Host: ${TENANT_SLUG}.mlops.local}"
USER_ID="${USER_ID:-demo}"
ROLES="${ROLES:-admin}"

log()  { echo "[smoke] $*"; }
ok()   { echo "✅ $*"; }
fail() { echo "❌ $*" >&2; exit 1; }

resolve_tenant_ids() {
  # Resolve tenant_id/project_id from the tenant map ConfigMap (mlops-system/mlops-tenant-map).
  local slug="$1"
  local raw
  raw=$(kubectl -n "${NS}" get cm mlops-tenant-map -o jsonpath='{.data.tenant-map\.json}' 2>/dev/null || true)
  if [[ -z "$raw" ]]; then
    echo ""
    return 0
  fi
  python3 - <<'PYCODE' "$slug" <<<"$raw"
import json,sys
slug=sys.argv[1]
obj=json.loads(sys.stdin.read())
entry=obj.get(slug) or {}
print((entry.get('tenant_id') or ''))
print((entry.get('project_id') or ''))
PYCODE
}

# Resolve IDs for internal service calls (feature-store, gpu-jobs, etc.)
ids=$(resolve_tenant_ids "${TENANT_SLUG}")
TENANT_ID=$(echo "$ids" | sed -n '1p')
PROJECT_ID=$(echo "$ids" | sed -n '2p')
if [[ -z "${TENANT_ID}" || -z "${PROJECT_ID}" ]]; then
  fail "could not resolve TENANT_ID/PROJECT_ID for slug '${TENANT_SLUG}' from ConfigMap mlops-tenant-map"
fi

H_COMMON=(-H "${HOST_HEADER}" -H "X-User-Id: ${USER_ID}" -H "X-Roles: ${ROLES}")

# If you want to test explicit headers (debug), set INCLUDE_TENANT_HEADERS=1
INCLUDE_TENANT_HEADERS="${INCLUDE_TENANT_HEADERS:-0}"
if [[ "$INCLUDE_TENANT_HEADERS" == "1" ]]; then
  H_COMMON+=( -H "X-Tenant-Id: ${TENANT_ID}" -H "X-Project-Id: ${PROJECT_ID}" )
fi

json_get() {
  # Usage: echo '{...}' | json_get '.id'
  if command -v jq >/dev/null 2>&1; then
    jq -r "$1"
  else
    python3 -c "import json,sys; obj=json.load(sys.stdin); import re
expr=sys.argv[1]
# very small jq-like subset: only .key
m=re.fullmatch(r'\\.([A-Za-z0-9_]+)', expr)
if not m:
  raise SystemExit('Need jq for complex expressions: '+expr)
print(obj.get(m.group(1), ''))" "$1"
  fi
}

wait_status() {
  # Usage: wait_status <name> <url> <wanted> <field> <timeout_seconds>
  local name="$1"; local url="$2"; local wanted="$3"; local field="$4"; local timeout="$5"
  local start now st
  start=$(date +%s)
  printf "[smoke] %s: waiting for %s" "$name" "$wanted"
  while true; do
    st=$(curl -fsS "$url" 2>/dev/null | json_get ".${field}" || true)
    if [[ "$VERBOSE" == "1" ]]; then
      printf "\n[smoke]   %s=%s\n" "$field" "$st"
    fi
    if [[ "$st" == "$wanted" ]]; then
      echo " ... done"
      return 0
    fi
    now=$(date +%s)
    if (( now - start > timeout )); then
      echo ""
      fail "$name did not reach ${wanted} (last ${field}=${st})"
    fi
    printf "."
    sleep 1
  done
}

# -----------------------------------------------------------------------------
# 1) K8s readiness (cheap but high signal)
log "Waiting for deployments (namespace: ${NS})"
for d in control-plane-api template-service run-service training-service deployment-service artifact-service registry-service gpu-jobs-service feature-store-service; do
  if [[ "$VERBOSE" == "1" ]]; then
    kubectl -n "$NS" rollout status "deploy/${d}" --timeout=240s
  else
    kubectl -n "$NS" rollout status "deploy/${d}" --timeout=240s >/dev/null
  fi
done
# -----------------------------------------------------------------------------
# 2) BFF health/overview (browser-friendly via tenant-router injected headers)
log "Health check"
curl -fsS "${H_COMMON[@]}" "$BASE_URL/api/v1/healthz" >/dev/null
ok "BFF healthz"

# Optional: verify the API gateway tenant-aware routing works (no explicit X-Tenant-Id/X-Project-Id).
CHECK_GATEWAY="${CHECK_GATEWAY:-1}"
if [[ "$CHECK_GATEWAY" == "1" ]]; then
  log "Gateway check (port-forward proxy service)"
  selector="gateway.envoyproxy.io/owning-gateway-name=mlops-gateway,gateway.envoyproxy.io/owning-gateway-namespace=gateway-system"
  svc="$(kubectl -n envoy-gateway-system get svc -l "$selector" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
  if [[ -n "$svc" ]]; then
    kubectl -n envoy-gateway-system port-forward "svc/$svc" 30081:80 >/tmp/pf-gw.log 2>&1 &
    PF_GW=$!
    sleep 1
    if curl -fsS -H "Host: ${TENANT_SLUG}.mlops.local" http://localhost:30081/api/v1/healthz >/dev/null; then
      ok "Gateway reachable"
    else
      log "Gateway check failed (continuing)"
    fi
    kill $PF_GW >/dev/null 2>&1 || true
  else
    log "Gateway proxy Service not found yet; skipping"
  fi
fi

log "Overview"
ovr=$(curl -fsS "${H_COMMON[@]}" "$BASE_URL/api/v1/overview")
if [[ "$(echo "$ovr" | json_get '.ok')" != "True" && "$(echo "$ovr" | json_get '.ok')" != "true" && "$(echo "$ovr" | json_get '.ok')" != "1" ]]; then
  # tolerate non-boolean encodings
  if [[ "$VERBOSE" == "1" ]]; then echo "$ovr"; fi
  fail "overview not ok"
fi
ok "Overview OK"

now_ts=$(date +%s)

# -----------------------------------------------------------------------------
# 3) Templates: create -> update -> list -> delete
log "Templates CRUD"
tmpl_payload=$(python3 - <<PY
import json, time
print(json.dumps({
  "name": f"demo-template-{int(time.time())}",
  "git_repo": "https://git.example.com/repo",
  "git_ref": "main",
  "entrypoint": "pipeline.py",
  "compiler": "kfp-v2",
  "default_parameters": {"epochs": 1}
}))
PY
)

tmpl_resp=$(curl -fsS "${H_COMMON[@]}" -X POST "$BASE_URL/api/v1/templates" -H "Content-Type: application/json" -d "$tmpl_payload")
tmpl_id=$(echo "$tmpl_resp" | json_get '.id')
[[ -n "$tmpl_id" ]] || fail "template create: missing id"

curl -fsS "${H_COMMON[@]}" -X PUT "$BASE_URL/api/v1/templates/$tmpl_id" -H "Content-Type: application/json" -d '{"description":"updated by kind smoke-test"}' >/dev/null
curl -fsS "${H_COMMON[@]}" "$BASE_URL/api/v1/templates" >/dev/null
ok "Templates CRUD (template_id=${tmpl_id})"

# -----------------------------------------------------------------------------
# 4) Runs: create -> wait SUCCEEDED (demo worker)
log "Run orchestration (demo worker)"
run_payload=$(python3 - <<PY
import json
print(json.dumps({"template_id":"$tmpl_id","parameters":{"epochs":1},"compute_profile":"t4-shared-1x"}))
PY
)
run_resp=$(curl -fsS "${H_COMMON[@]}" -X POST "$BASE_URL/api/v1/runs" -H "Content-Type: application/json" -d "$run_payload")
run_id=$(echo "$run_resp" | json_get '.id')
[[ -n "$run_id" ]] || fail "run create: missing id"
wait_status "run" "$BASE_URL/api/v1/runs/$run_id" "SUCCEEDED" "status" 45
ok "Run SUCCEEDED (run_id=${run_id})"

# -----------------------------------------------------------------------------
# 5) Training: create -> list (BFF route)
log "Training jobs"
tr_resp=$(curl -fsS "${H_COMMON[@]}" -X POST "$BASE_URL/api/v1/training/jobs" -H "Content-Type: application/json" -d '{}')
tr_id=$(echo "$tr_resp" | json_get '.id')
[[ -n "$tr_id" ]] || fail "training create: missing id"
curl -fsS "${H_COMMON[@]}" "$BASE_URL/api/v1/training/jobs" >/dev/null
ok "Training jobs OK (job_id=${tr_id})"

# -----------------------------------------------------------------------------
# 6) Artifacts: create -> list
log "Artifacts"
art_payload=$(python3 - <<PY
import json
print(json.dumps({"kind":"model","uri":"s3://mlops-artifacts/demo/model.bin","metadata":{"ts":$now_ts}}))
PY
)
curl -fsS "${H_COMMON[@]}" -X POST "$BASE_URL/api/v1/artifacts" -H "Content-Type: application/json" -d "$art_payload" >/dev/null
curl -fsS "${H_COMMON[@]}" "$BASE_URL/api/v1/artifacts" >/dev/null
ok "Artifacts OK"

# -----------------------------------------------------------------------------
# 7) Deployments: create -> wait READY
log "Deployments"
dep_payload=$(python3 - <<PY
import json
print(json.dumps({"name":"demo-dep-$now_ts"}))
PY
)
dep_resp=$(curl -fsS "${H_COMMON[@]}" -X POST "$BASE_URL/api/v1/deployments" -H "Content-Type: application/json" -d "$dep_payload")
dep_id=$(echo "$dep_resp" | json_get '.id')
[[ -n "$dep_id" ]] || fail "deployment create: missing id"
wait_status "deployment" "$BASE_URL/api/v1/deployments/$dep_id" "READY" "status" 75
ok "Deployment READY (deployment_id=${dep_id})"

# -----------------------------------------------------------------------------
# 8) GPU queue + feature-store (direct svc port-forward)
log "GPU queue + Feature-store (port-forward)"
TENANT="${TENANT_ID}"
PROJ="${PROJECT_ID}"
USER="${USER_ID}"
H_TEN=(-H "X-Tenant-Id: $TENANT" -H "X-Project-Id: $PROJ" -H "X-User-Id: $USER" -H "X-Roles: admin" -H "Content-Type: application/json")

PF1_LOG=$(mktemp)
PF2_LOG=$(mktemp)
kubectl -n "$NS" port-forward svc/feature-store-service 18009:8000 >"$PF1_LOG" 2>&1 &
PF1=$!
kubectl -n "$NS" port-forward svc/gpu-jobs-service 18010:8000 >"$PF2_LOG" 2>&1 &
PF2=$!
cleanup() { kill $PF1 $PF2 >/dev/null 2>&1 || true; }
trap cleanup EXIT
sleep 1

fs_ok=$(curl -fsS "http://localhost:18009/api/v1/admin/tenants/$TENANT" "${H_TEN[@]}" | python3 -c "import json,sys; d=json.load(sys.stdin); print('feast_base_url' in d)")
[[ "$fs_ok" == "True" || "$fs_ok" == "true" ]] || fail "feature-store admin route failed"

job_payload='{"gpu_pool_requested":"t4","isolation_level":"shared","priority":0,"target_url":"http://example.invalid","request_json":{"ping":true}}'
job_resp=$(curl -fsS -X POST "http://localhost:18010/api/v1/gpu-jobs" "${H_TEN[@]}" -d "$job_payload")
job_id=$(echo "$job_resp" | json_get '.id')
[[ -n "$job_id" ]] || fail "gpu job create: missing id"
wait_status "gpu-job" "http://localhost:18010/api/v1/gpu-jobs/$job_id" "SUCCEEDED" "status" 60
ok "GPU job SUCCEEDED (gpu_job_id=${job_id})"

# -----------------------------------------------------------------------------
# 9) Cleanup (template)
log "Cleanup"
curl -fsS "${H_COMMON[@]}" -X DELETE "$BASE_URL/api/v1/templates/$tmpl_id" >/dev/null
ok "Cleanup complete"

echo ""
echo "================= DEMO LINKS ================="
echo "Tenant A (no custom headers):"
echo "  - Overview:        ${BASE_URL}/api/v1/overview"
echo "  - API Docs:        ${BASE_URL}/docs"
echo "  - Templates:       ${BASE_URL}/api/v1/templates"
echo "  - Run detail:      ${BASE_URL}/api/v1/runs/${run_id}"
echo "  - Training jobs:   ${BASE_URL}/api/v1/training/jobs"
echo "  - Deployments:     ${BASE_URL}/api/v1/deployments"
echo "  - Deployment:      ${BASE_URL}/api/v1/deployments/${dep_id}"
echo ""
echo "============================================="

echo ""
echo "SMOKE TEST PASSED ✅"
