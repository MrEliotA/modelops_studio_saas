#!/usr/bin/env bash
set -euo pipefail

TENANT="${TENANT_ID:-00000000-0000-0000-0000-000000000001}"
PROJ="${PROJECT_ID:-00000000-0000-0000-0000-000000000002}"
USER="${USER_ID:-user@example.com}"

hdrs=(
  -H "X-Tenant-Id: $TENANT"
  -H "X-Project-Id: $PROJ"
  -H "X-User-Id: $USER"
  -H "Content-Type: application/json"
)

echo "==> 1) Create a template"
TEMPLATE=$(curl -sS -X POST http://localhost:8001/api/v1/templates \
  "${hdrs[@]}" \
  -H "Idempotency-Key: 11111111-1111-1111-1111-111111111111" \
  -d '{"name":"demo-template","git_repo":"https://git.example.com/repo","git_ref":"main","entrypoint":"pipelines/demo.yaml","compiler":"kfp-yaml"}')
echo "$TEMPLATE" | jq .
TEMPLATE_ID=$(echo "$TEMPLATE" | jq -r .id)

echo "==> 2) Create a run (publishes event to JetStream)"
RUN=$(curl -sS -X POST http://localhost:8002/api/v1/runs \
  "${hdrs[@]}" \
  -H "Idempotency-Key: 22222222-2222-2222-2222-222222222222" \
  -d "$(jq -n --arg tid "$TEMPLATE_ID" '{template_id:$tid,parameters:{epochs:1},compute_profile:"t4-1x"}')")
echo "$RUN" | jq .
RUN_ID=$(echo "$RUN" | jq -r .id)

echo "==> 3) Wait for run-orchestrator to mark it SUCCEEDED..."
sleep 6
curl -sS http://localhost:8002/api/v1/runs/$RUN_ID "${hdrs[@]}" | jq .

echo "==> 4) Register a model + version"
MODEL=$(curl -sS -X POST http://localhost:8003/api/v1/models \
  "${hdrs[@]}" \
  -H "Idempotency-Key: 33333333-3333-3333-3333-333333333333" \
  -d '{"name":"demo-model","description":"sample model"}')
echo "$MODEL" | jq .
MODEL_ID=$(echo "$MODEL" | jq -r .id)

MV=$(curl -sS -X POST http://localhost:8003/api/v1/models/$MODEL_ID/versions \
  "${hdrs[@]}" \
  -H "Idempotency-Key: 44444444-4444-4444-4444-444444444444" \
  -d "$(jq -n --arg uri "s3://mlops-artifacts/models/demo-model/1/model" --arg run "$RUN_ID" '{artifact_uri:$uri,source_run_id:$run,metrics:{acc:0.9}}')")
echo "$MV" | jq .
MV_ID=$(echo "$MV" | jq -r .id)

echo "==> 5) Create an endpoint (deploy-worker will mark READY)"
EP=$(curl -sS -X POST http://localhost:8003/api/v1/endpoints \
  "${hdrs[@]}" \
  -H "Idempotency-Key: 55555555-5555-5555-5555-555555555555" \
  -d "$(jq -n --arg name "demo-endpoint" --arg mid "$MODEL_ID" --arg mvid "$MV_ID" '{name:$name,model_id:$mid,model_version_id:$mvid}')")
echo "$EP" | jq .
EP_ID=$(echo "$EP" | jq -r .id)

sleep 4
curl -sS http://localhost:8003/api/v1/endpoints/$EP_ID "${hdrs[@]}" | jq .

echo "==> 6) Ingest a metering record"
curl -sS -X POST http://localhost:8005/api/v1/usage \
  "${hdrs[@]}" \
  -H "Idempotency-Key: 66666666-6666-6666-6666-666666666666" \
  -d "$(jq -n --arg sid "$EP_ID" '{subject_type:"endpoint",subject_id:$sid,meter:"inference_requests",quantity:123,labels:{model:"demo-model"}}')" | jq .

echo "==> 7) RAG demo (create index, ingest doc, query)"
IDX=$(curl -sS -X POST http://localhost:8011/api/v1/rag/indexes \
  "${hdrs[@]}" \
  -H "Idempotency-Key: 77777777-7777-7777-7777-777777777777" \
  -d '{"name":"demo-rag","chunking":{"chunk_size":400,"overlap":80}}')
echo "$IDX" | jq .
IDX_ID=$(echo "$IDX" | jq -r .id)

curl -sS -X POST http://localhost:8011/api/v1/rag/indexes/$IDX_ID/documents \
  "${hdrs[@]}" \
  -d '{"documents":[{"external_id":"doc-1","title":"Intro","content":"MLOps SaaS runs on Kubernetes. RAG uses embeddings + vector search with pgvector."}]}' | jq .

curl -sS -X POST http://localhost:8011/api/v1/rag/indexes/$IDX_ID/query \
  "${hdrs[@]}" \
  -d '{"query":"What does RAG use?","top_k":3}' | jq .

echo "All done."
