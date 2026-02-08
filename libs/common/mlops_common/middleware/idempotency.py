from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timedelta, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi.responses import JSONResponse
import asyncpg
import structlog

log = structlog.get_logger(__name__)
IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH"}

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _now() -> datetime:
    return datetime.now(timezone.utc)

async def _fetch_existing(conn, tenant_id, project_id, idem_key, method, path):
    return await conn.fetchrow(
        """SELECT request_hash, status_code, response_headers, response_body
            FROM idempotency_keys
            WHERE tenant_id=$1 AND project_id=$2 AND idem_key=$3 AND method=$4 AND path=$5
              AND expires_at > now()""",
        tenant_id, project_id, idem_key, method, path
    )

async def _insert_placeholder(conn, tenant_id, project_id, idem_key, method, path, request_hash, ttl_seconds: int):
    expires_at = _now() + timedelta(seconds=ttl_seconds)
    await conn.execute(
        """INSERT INTO idempotency_keys(tenant_id, project_id, idem_key, method, path, request_hash, expires_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7)""",
        tenant_id, project_id, idem_key, method, path, request_hash, expires_at
    )

async def _finalize(conn, tenant_id, project_id, idem_key, method, path, status_code: int, headers: dict, body: bytes | None):
    await conn.execute(
        """UPDATE idempotency_keys
            SET status_code=$1, response_headers=$2, response_body=$3
            WHERE tenant_id=$4 AND project_id=$5 AND idem_key=$6 AND method=$7 AND path=$8""",
        status_code, json.dumps(headers), body, tenant_id, project_id, idem_key, method, path
    )

class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, pool_getter=lambda req: req.app.state.db_pool):
        super().__init__(app)
        self.pool_getter = pool_getter
        self.ttl_seconds = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "86400"))
        self.max_store_bytes = int(os.getenv("IDEMPOTENCY_MAX_BODY_BYTES", "1048576"))

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        if method not in IDEMPOTENT_METHODS:
            return await call_next(request)

        idem_key = request.headers.get("Idempotency-Key")
        if not idem_key:
            return await call_next(request)

        tenancy = getattr(request.state, "tenancy", None)
        if tenancy is None:
            return await call_next(request)

        req_body = await request.body()
        request_hash = _sha256(req_body + f"|{method}|{request.url.path}".encode())

        pool = self.pool_getter(request)
        async with pool.acquire() as conn:
            existing = await _fetch_existing(conn, tenancy.tenant_id, tenancy.project_id, idem_key, method, request.url.path)
            if existing:
                if existing["request_hash"] != request_hash:
                    return JSONResponse(status_code=409, content={"code":"IdempotencyConflict","message":"Idempotency-Key already used with a different request payload.","request_id": tenancy.request_id})
                if existing["status_code"] is None:
                    return JSONResponse(status_code=409, content={"code":"IdempotencyInProgress","message":"A request with this Idempotency-Key is still in progress.","request_id": tenancy.request_id})

                headers = existing["response_headers"] or {}
                body = bytes(existing["response_body"] or b"")
                status_code = int(existing["status_code"])
                resp = Response(content=body, status_code=status_code, media_type=headers.get("content-type","application/json"))
                for k, v in (headers or {}).items():
                    if k.lower() not in ("content-length","transfer-encoding","connection"):
                        resp.headers[k] = str(v)
                resp.headers.setdefault("X-Idempotent-Replayed","true")
                return resp

            try:
                await _insert_placeholder(conn, tenancy.tenant_id, tenancy.project_id, idem_key, method, request.url.path, request_hash, self.ttl_seconds)
            except asyncpg.UniqueViolationError:
                return JSONResponse(status_code=409, content={"code":"IdempotencyInProgress","message":"A request with this Idempotency-Key is already being processed.","request_id": tenancy.request_id})

        try:
            response = await call_next(request)
        except Exception as e:
            log.exception("unhandled_exception_in_idempotent_request", error=str(e))
            response = JSONResponse(status_code=500, content={"code":"InternalError","message":"Unhandled exception","request_id": tenancy.request_id})

        # Capture full response to return; store only up to max_store_bytes
        full_body = b""
        stored_body = b""
        store_enabled = True
        async for chunk in response.body_iterator:
            full_body += chunk
            if store_enabled and (len(stored_body) + len(chunk) <= self.max_store_bytes):
                stored_body += chunk
            else:
                store_enabled = False

        new_resp = Response(
            content=full_body,
            status_code=response.status_code,
            media_type=response.media_type,
            headers=dict(response.headers),
        )
        new_resp.headers.setdefault("X-Request-Id", tenancy.request_id)

        async with pool.acquire() as conn:
            headers = dict(new_resp.headers)
            body_to_store = stored_body if store_enabled else None
            await _finalize(conn, tenancy.tenant_id, tenancy.project_id, idem_key, method, request.url.path, new_resp.status_code, headers, body_to_store)

        return new_resp
