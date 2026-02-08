from __future__ import annotations

from fastapi import APIRouter, Request
import os

from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError

from .providers import get_provider

app = create_app("llm-embeddings-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")

DEFAULT_DIMS = int(os.getenv("EMBEDDINGS_DIM", "1536"))
MAX_DIMS = int(os.getenv("EMBEDDINGS_MAX_DIM", "4096"))


@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True, "service": "llm-embeddings-service"}


@router.post("/embeddings")
async def embeddings(request: Request, payload: dict):
    provider = get_provider()

    model = payload.get("model") or os.getenv("EMBEDDINGS_MODEL") or "default"
    dims = int(payload.get("dims") or DEFAULT_DIMS)

    # Backward compatible keys: inputs OR texts
    inputs = payload.get("inputs")
    if inputs is None:
        inputs = payload.get("texts")

    if not isinstance(inputs, list) or not inputs:
        raise ApiError("BadRequest", "inputs must be a non-empty list", 400)
    if dims <= 0 or dims > MAX_DIMS:
        raise ApiError("BadRequest", "dims out of range", 400)

    texts = [str(x) for x in inputs]
    vectors = await provider.embed(texts, dims=dims, model=str(model))

    return {
        "provider": getattr(provider, "name", "unknown"),
        "model": model,
        "dims": dims,
        "count": len(texts),
        "embeddings": vectors,
    }


app.include_router(router)
