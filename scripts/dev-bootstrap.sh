#!/usr/bin/env bash
set -euo pipefail

echo "==> Waiting for Postgres..."
until docker compose exec -T postgres pg_isready -U postgres -d mlops >/dev/null 2>&1; do
  sleep 1
done

echo "==> Applying migrations..."
for f in /migrations/*.sql; do
  echo "Applying $(basename "$f")"
  docker compose exec -T postgres psql -U postgres -d mlops -f "$f"
done

echo "==> Waiting for MinIO..."
until curl -fsS http://localhost:9000/minio/health/ready >/dev/null 2>&1; do
  sleep 1
done

echo "==> Creating MinIO buckets (mlflow, mlops-artifacts, rag-docs)..."
docker run --rm --network $(basename "$PWD")_default \
  -e MC_HOST_local=http://minioadmin:minioadmin@minio:9000 \
  minio/mc:latest mb --ignore-existing local/mlflow local/mlops-artifacts local/rag-docs

echo "==> Bootstrapping NATS JetStream streams..."
docker compose run --rm nats-bootstrap

echo "Done."
