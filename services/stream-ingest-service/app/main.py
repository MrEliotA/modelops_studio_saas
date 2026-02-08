from __future__ import annotations

from fastapi import APIRouter, Request
from mlops_common.app_factory import create_app
from mlops_common.nats_client import connect as nats_connect, ensure_streams, publish

app = create_app("stream-ingest-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")

@app.on_event("startup")
async def _startup():
    nc = await nats_connect()
    app.state.nats = nc
    app.state.js = nc.jetstream()
    await ensure_streams(app.state.js)

@app.on_event("shutdown")
async def _shutdown():
    nc = getattr(app.state, "nats", None)
    if nc:
        await nc.drain()

@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}

@router.post("/streams/{stream_name}/events", status_code=202)
async def ingest_event(request: Request, stream_name: str, payload: dict):
    t = request.state.tenancy
    subject = f"mlops.stream.{stream_name}"
    await publish(request.app.state.js, subject, {
        "tenant_id": str(t.tenant_id),
        "project_id": str(t.project_id),
        "user_id": t.user_id,
        "payload": payload,
    })
    return {"accepted": True, "subject": subject}

app.include_router(router)
