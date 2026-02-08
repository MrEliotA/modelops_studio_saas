from __future__ import annotations
from fastapi import APIRouter, Request
import asyncpg
import os
import boto3
from botocore.client import Config
from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError

app = create_app("artifact-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")

def _s3():
    endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("S3_REGION","us-east-1"),
        config=Config(signature_version="s3v4"),
    )

@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}

@router.post("/artifacts", status_code=201)
async def create_artifact(request: Request, payload: dict):
    t = request.state.tenancy
    if not payload.get("kind") or not payload.get("uri"):
        raise ApiError("BadRequest","Missing kind or uri",400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO artifacts(tenant_id, project_id, kind, uri, content_type, size_bytes, checksum, metadata, created_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
               RETURNING id, kind, uri, content_type, size_bytes, checksum, metadata, created_by, created_at, updated_at""",
            t.tenant_id, t.project_id, payload["kind"], payload["uri"], payload.get("content_type"),
            payload.get("size_bytes"), payload.get("checksum"), payload.get("metadata",{}), t.user_id
        )
    return dict(row)


@router.get("/artifacts")
async def list_artifacts(request: Request, limit: int = 50, kind: str | None = None):
    """List artifact metadata records for the current tenant/project."""
    t = request.state.tenancy
    limit = max(1, min(200, int(limit)))

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        if kind:
            rows = await conn.fetch(
                """SELECT id, kind, uri, content_type, size_bytes, checksum, metadata, created_by, created_at, updated_at
                   FROM artifacts
                   WHERE tenant_id=$1 AND project_id=$2 AND kind=$3
                   ORDER BY created_at DESC
                   LIMIT $4""",
                t.tenant_id,
                t.project_id,
                kind,
                limit,
            )
        else:
            rows = await conn.fetch(
                """SELECT id, kind, uri, content_type, size_bytes, checksum, metadata, created_by, created_at, updated_at
                   FROM artifacts
                   WHERE tenant_id=$1 AND project_id=$2
                   ORDER BY created_at DESC
                   LIMIT $3""",
                t.tenant_id,
                t.project_id,
                limit,
            )
    return {"items": [dict(r) for r in rows]}

@router.post("/artifacts/presign")
async def presign(request: Request, payload: dict):
    # payload: {bucket,key,method,expires_in}
    bucket = payload.get("bucket")
    key = payload.get("key")
    method = (payload.get("method") or "get").lower()
    if not bucket or not key:
        raise ApiError("BadRequest","Missing bucket or key",400)

    s3 = _s3()
    expires = int(payload.get("expires_in", 3600))
    if method == "put":
        url = s3.generate_presigned_url("put_object", Params={"Bucket":bucket,"Key":key}, ExpiresIn=expires)
    else:
        url = s3.generate_presigned_url("get_object", Params={"Bucket":bucket,"Key":key}, ExpiresIn=expires)

    return {"url": url, "method": method, "expires_in": expires}

app.include_router(router)
