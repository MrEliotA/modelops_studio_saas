from __future__ import annotations

import uuid
import httpx
from fastapi import APIRouter, Request
from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")

app = create_app("feature-store-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")

def _forward_headers(request: Request) -> dict[str, str]:
    # Forward only headers that matter across internal hops.
    h: dict[str, str] = {}
    for k in ["x-tenant-id", "x-project-id", "x-user-id", "x-request-id", "idempotency-key", "traceparent"]:
        if k in request.headers:
            h[k] = request.headers[k]
    return h

async def _ensure_demo_tenants(pool):
    """Seed demo tenant routing if missing.

    NOTE: We intentionally use the app's db_pool (created by create_app) instead of
    a global DB handle. This keeps the service stateless and avoids hidden globals.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO feature_store_tenants (tenant_id, feast_base_url, feast_project)
                   VALUES ($1,$2,$3)
                   ON CONFLICT (tenant_id) DO UPDATE SET
                     feast_base_url=EXCLUDED.feast_base_url,
                     feast_project=EXCLUDED.feast_project,
                     updated_at=now()""",
            TENANT_A, "http://feast-feature-server-tenant-a.feast.svc.cluster.local:6566", "tenant_a"
        )
        await conn.execute(
            """INSERT INTO feature_store_tenants (tenant_id, feast_base_url, feast_project)
                   VALUES ($1,$2,$3)
                   ON CONFLICT (tenant_id) DO UPDATE SET
                     feast_base_url=EXCLUDED.feast_base_url,
                     feast_project=EXCLUDED.feast_project,
                     updated_at=now()""",
            TENANT_B, "http://feast-feature-server-tenant-b.feast.svc.cluster.local:6566", "tenant_b"
        )

async def _get_tenant_route(pool, tenant_id: uuid.UUID) -> tuple[str, str]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT feast_base_url, feast_project FROM feature_store_tenants WHERE tenant_id=$1",
            tenant_id,
        )
    if not row:
        raise ApiError("NotFound", "Tenant feature store route not found", 404)
    return str(row["feast_base_url"]).rstrip("/"), str(row["feast_project"])

@app.on_event("startup")
async def _startup():
    # app_factory startup runs first and creates app.state.db_pool.
    await _ensure_demo_tenants(app.state.db_pool)

@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}

@router.post("/feast/get-online-features")
async def get_online_features(request: Request, payload: dict):
    tenant_id = request.state.tenancy.tenant_id
    base_url, _project = await _get_tenant_route(request.app.state.db_pool, tenant_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{base_url}/get-online-features", json=payload, headers=_forward_headers(request))
    if r.status_code >= 400:
        raise ApiError("UpstreamError", r.text, 502)
    return r.json()

@router.post("/feast/push")
async def push(request: Request, payload: dict):
    tenant_id = request.state.tenancy.tenant_id
    base_url, _project = await _get_tenant_route(request.app.state.db_pool, tenant_id)
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{base_url}/push", json=payload, headers=_forward_headers(request))
    if r.status_code >= 400:
        raise ApiError("UpstreamError", r.text, 502)
    return r.json() if r.headers.get("content-type","").startswith("application/json") else {"ok": True}

# Optional admin API to update routing.
@router.put("/admin/tenants/{tenant_id}")
async def upsert_tenant(tenant_id: str, payload: dict):
    tid = uuid.UUID(tenant_id)
    base_url = str(payload.get("feast_base_url", "")).strip()
    project = str(payload.get("feast_project", "")).strip()
    if not base_url or not project:
        raise ApiError("ValidationError", "feast_base_url and feast_project are required", 400)
    pool = app.state.db_pool
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO feature_store_tenants (tenant_id, feast_base_url, feast_project)
                   VALUES ($1,$2,$3)
                   ON CONFLICT (tenant_id) DO UPDATE SET
                     feast_base_url=EXCLUDED.feast_base_url,
                     feast_project=EXCLUDED.feast_project,
                     updated_at=now()""",
            tid, base_url, project
        )
    return {"ok": True}

@router.get("/admin/tenants/{tenant_id}")
async def get_tenant(tenant_id: str):
    tid = uuid.UUID(tenant_id)
    base_url, project = await _get_tenant_route(app.state.db_pool, tid)
    return {"tenant_id": str(tid), "feast_base_url": base_url, "feast_project": project}

app.include_router(router)
