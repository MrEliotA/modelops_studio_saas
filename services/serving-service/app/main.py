from __future__ import annotations
from fastapi import APIRouter
from mlops_common.app_factory import create_app

app = create_app("serving-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")

@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True, "service": "serving-service"}

app.include_router(router)
