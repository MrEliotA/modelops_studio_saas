from __future__ import annotations
from fastapi import APIRouter, Request
import asyncpg
from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError
from mlops_common.nats_client import connect as nats_connect, ensure_streams, publish

app = create_app("metering-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")

@app.on_event("startup")
async def _startup_nats():
    nc = await nats_connect()
    app.state.nats = nc
    app.state.js = nc.jetstream()
    await ensure_streams(app.state.js)

@app.on_event("shutdown")
async def _shutdown_nats():
    nc = getattr(app.state, "nats", None)
    if nc:
        await nc.drain()

@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}

@router.post("/usage", status_code=201)
async def ingest_usage(request: Request, payload: dict):
    t = request.state.tenancy
    for k in ["subject_type","meter","quantity"]:
        if payload.get(k) is None:
            raise ApiError("BadRequest", f"Missing {k}", 400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO usage_ledger(tenant_id, project_id, subject_type, subject_id, meter, quantity, labels, window_start, window_end)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
               RETURNING id, subject_type, subject_id, meter, quantity, labels, window_start, window_end, created_at""",
            t.tenant_id, t.project_id, payload["subject_type"], payload.get("subject_id"),
            payload["meter"], payload["quantity"], payload.get("labels",{}),
            payload.get("window_start"), payload.get("window_end")
        )

    await publish(request.app.state.js, "mlops.metering.usage_recorded", {
        "tenant_id": str(t.tenant_id),
        "project_id": str(t.project_id),
        "usage_id": str(row["id"]),
        "meter": row["meter"],
        "quantity": float(row["quantity"]),
    })

    return dict(row)

@router.get("/usage")
async def list_usage(request: Request):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, subject_type, subject_id, meter, quantity, labels, window_start, window_end, created_at
               FROM usage_ledger WHERE tenant_id=$1 AND project_id=$2 ORDER BY created_at DESC LIMIT 200""",
            t.tenant_id, t.project_id
        )
    return {"items":[dict(r) for r in rows]}

@router.post("/invoices", status_code=201)
async def create_invoice(request: Request, payload: dict):
    t = request.state.tenancy
    period_start = payload.get("period_start")
    period_end = payload.get("period_end")
    if not period_start or not period_end:
        raise ApiError("BadRequest","Missing period_start/period_end (YYYY-MM-DD)",400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT meter, SUM(quantity) as total
               FROM usage_ledger
               WHERE tenant_id=$1 AND project_id=$2
                 AND created_at::date >= $3::date AND created_at::date <= $4::date
               GROUP BY meter""",
            t.tenant_id, t.project_id, period_start, period_end
        )
        lines = [{"meter": r["meter"], "quantity": float(r["total"]), "unit_price": 0, "amount": 0} for r in rows]
        total = 0
        inv = await conn.fetchrow(
            """INSERT INTO invoices(tenant_id, project_id, period_start, period_end, currency, total_amount, lines, status)
               VALUES ($1,$2,$3::date,$4::date,'USD',$5,$6,'DRAFT')
               RETURNING id, period_start, period_end, currency, total_amount, lines, status, created_at""",
            t.tenant_id, t.project_id, period_start, period_end, total, lines
        )
    return dict(inv)

app.include_router(router)
