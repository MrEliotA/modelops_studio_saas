#!/usr/bin/env bash
set -euo pipefail

# Upload the Triton model repository to MinIO (dev stack).
# This uses the same Docker-based `mc` approach as scripts/dev-bootstrap.sh.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$ROOT_DIR/model-repository"

NETWORK="$(basename "$(cd "$ROOT_DIR/../.." && pwd)")_default"

docker run --rm --network "$NETWORK" \
  -e MC_HOST_local=http://minioadmin:minioadmin@minio:9000 \
  -v "$REPO_DIR:/repo:ro" \
  minio/mc:latest \
  cp --recursive /repo/add_sub local/mlops-artifacts/triton/add_sub

# Create a "v2" copy for canary demo.
docker run --rm --network "$NETWORK" \
  -e MC_HOST_local=http://minioadmin:minioadmin@minio:9000 \
  -v "$REPO_DIR:/repo:ro" \
  minio/mc:latest \
  cp --recursive /repo/add_sub local/mlops-artifacts/triton/add_sub_v2

echo "Uploaded Triton model repos to: s3://mlops-artifacts/triton/{add_sub,add_sub_v2}"
