from __future__ import annotations

import os
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response, JSONResponse
import httpx

from mlops_common.app_factory import create_app
from .auth import get_principal, Principal
from .rbac import require
from .tenant_routing import TenantRoutingMiddleware

app = create_app("control-plane-api", enable_idempotency=True)

# TenantRoutingMiddleware runs at the edge to resolve tenant context from host/path.
# It injects X-Tenant-Id (+ optional default X-Project-Id) before the shared TenancyMiddleware.
app.add_middleware(TenantRoutingMiddleware)

# Create one shared client per process
@app.on_event("startup")
async def _startup():
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(20.0))

@app.on_event("shutdown")
async def _shutdown():
    client = getattr(app.state, "http", None)
    if client:
        await client.aclose()

router = APIRouter(prefix="/api/v1")

@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True, "service": "control-plane-api"}

def _svc_url(env: str, default: str) -> str:
    return os.getenv(env, default).rstrip("/")

SERVICE_URLS = {
    "templates": _svc_url("TEMPLATE_SERVICE_URL", "http://template-service:8000"),
    "runs": _svc_url("RUN_SERVICE_URL", "http://run-service:8000"),
    "feature_store": _svc_url("FEATURE_STORE_SERVICE_URL", "http://feature-store-service:8000"),
    "stream_ingest": _svc_url("STREAM_INGEST_SERVICE_URL", "http://stream-ingest-service:8000"),
    "training": _svc_url("TRAINING_SERVICE_URL", "http://training-service:8000"),
    "registry": _svc_url("REGISTRY_SERVICE_URL", "http://registry-service:8000"),
    "deployments": _svc_url("DEPLOYMENT_SERVICE_URL", "http://deployment-service:8000"),
    "artifacts": _svc_url("ARTIFACT_SERVICE_URL", "http://artifact-service:8000"),
    "metering": _svc_url("METERING_SERVICE_URL", "http://metering-service:8000"),
    "llm_rag": _svc_url("LLM_RAG_SERVICE_URL", "http://llm-rag-service:8000"),
    "llm_embeddings": _svc_url("LLM_EMBEDDINGS_SERVICE_URL", "http://llm-embeddings-service:8000"),
    "llm_eval": _svc_url("LLM_EVAL_SERVICE_URL", "http://llm-eval-service:8000"),
    "llm_labeling": _svc_url("LLM_LABELING_SERVICE_URL", "http://llm-labeling-service:8000"),
    "gpu_jobs": _svc_url("GPU_JOBS_SERVICE_URL", "http://gpu-jobs-service:8000"),
}

FORWARD_HEADERS = {
    "x-tenant-id",
    "x-project-id",
    "x-user-id",
    "x-request-id",
    "idempotency-key",
    "authorization",
}

def _fwd_headers(request: Request) -> dict[str, str]:
    hdrs = {}
    for k, v in request.headers.items():
        lk = k.lower()
        if lk in FORWARD_HEADERS:
            hdrs[k] = v
    return hdrs

async def _proxy(request: Request, upstream: str, path: str) -> Response:
    client: httpx.AsyncClient = request.app.state.http
    url = f"{upstream}{path}"
    try:
        body = await request.body()
        resp = await client.request(
            request.method,
            url,
            params=dict(request.query_params),
            headers=_fwd_headers(request),
            content=body if body else None,
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Upstream unavailable: {e}") from e

    # Pass through JSON bodies; otherwise raw bytes.
    content_type = resp.headers.get("content-type", "")
    headers = {}
    # propagate request id even if upstream didn't
    if "x-request-id" in resp.headers:
        headers["x-request-id"] = resp.headers["x-request-id"]
    if content_type.startswith("application/json"):
        return JSONResponse(status_code=resp.status_code, content=resp.json(), headers=headers)
    return Response(status_code=resp.status_code, content=resp.content, media_type=content_type, headers=headers)

# ---- Aggregate / Proxy endpoints ----
# Templates
@router.api_route("/templates", methods=["GET","POST"])
async def templates(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="templates", method=request.method)
    return await _proxy(request, SERVICE_URLS["templates"], "/api/v1/templates")

@router.api_route("/templates/{template_id}", methods=["GET","PUT","DELETE"])
async def template_item(template_id: str, request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="templates", method=request.method)
    return await _proxy(request, SERVICE_URLS["templates"], f"/api/v1/templates/{template_id}")

# Runs
@router.api_route("/runs", methods=["GET","POST"])
async def runs(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="runs", method=request.method)
    return await _proxy(request, SERVICE_URLS["runs"], "/api/v1/runs")

@router.api_route("/runs/{run_id}", methods=["GET"])
async def run_item(run_id: str, request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="runs", method=request.method)
    return await _proxy(request, SERVICE_URLS["runs"], f"/api/v1/runs/{run_id}")

# Training jobs
@router.api_route("/training/jobs", methods=["GET","POST"])
async def training_jobs(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="training", method=request.method)
    # training-service uses /api/v1/training-jobs
    return await _proxy(request, SERVICE_URLS["training"], "/api/v1/training-jobs")

@router.api_route("/training/jobs/{job_id}", methods=["GET"])
async def training_job(job_id: str, request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="training", method=request.method)
    return await _proxy(request, SERVICE_URLS["training"], f"/api/v1/training-jobs/{job_id}")

# Backward/forward compatibility alias: allow clients to call the upstream path directly via BFF
@router.api_route("/training-jobs", methods=["GET","POST"])
async def training_jobs_v2(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="training", method=request.method)
    return await _proxy(request, SERVICE_URLS["training"], "/api/v1/training-jobs")

@router.api_route("/training-jobs/{job_id}", methods=["GET"])
async def training_job_v2(job_id: str, request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="training", method=request.method)
    return await _proxy(request, SERVICE_URLS["training"], f"/api/v1/training-jobs/{job_id}")

# Registry
@router.api_route("/models", methods=["GET","POST"])
async def models(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="registry", method=request.method)
    return await _proxy(request, SERVICE_URLS["registry"], "/api/v1/models")

@router.api_route("/models/{model_id}", methods=["GET","PUT"])
async def model_item(model_id: str, request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="registry", method=request.method)
    return await _proxy(request, SERVICE_URLS["registry"], f"/api/v1/models/{model_id}")

@router.api_route("/models/{model_id}/versions", methods=["GET","POST"])
async def model_versions(model_id: str, request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="registry", method=request.method)
    return await _proxy(request, SERVICE_URLS["registry"], f"/api/v1/models/{model_id}/versions")

# Deployments / endpoints
@router.api_route("/deployments", methods=["GET","POST"])
async def deployments(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="deployments", method=request.method)
    return await _proxy(request, SERVICE_URLS["deployments"], "/api/v1/deployments")

@router.api_route("/deployments/{deployment_id}", methods=["GET","PUT","DELETE"])
async def deployment_item(deployment_id: str, request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="deployments", method=request.method)
    return await _proxy(request, SERVICE_URLS["deployments"], f"/api/v1/deployments/{deployment_id}")

# Artifacts
@router.api_route("/artifacts", methods=["GET","POST"])
async def artifacts(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="artifacts", method=request.method)
    return await _proxy(request, SERVICE_URLS["artifacts"], "/api/v1/artifacts")

# Metering
@router.api_route("/usage", methods=["GET"])
async def usage(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="metering", method=request.method)
    return await _proxy(request, SERVICE_URLS["metering"], "/api/v1/usage")

# LLM modules
@router.api_route("/llm/rag/query", methods=["POST"])
async def llm_rag_query(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="llm", method=request.method)
    return await _proxy(request, SERVICE_URLS["llm_rag"], "/api/v1/rag/query")

@router.api_route("/llm/embeddings", methods=["POST"])
async def llm_embeddings(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="llm", method=request.method)
    return await _proxy(request, SERVICE_URLS["llm_embeddings"], "/api/v1/embeddings")

@router.api_route("/llm/eval", methods=["POST"])
async def llm_eval(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="llm", method=request.method)
    return await _proxy(request, SERVICE_URLS["llm_eval"], "/api/v1/eval")

@router.api_route("/llm/labeling", methods=["POST"])
async def llm_labeling(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="llm", method=request.method)
    return await _proxy(request, SERVICE_URLS["llm_labeling"], "/api/v1/labeling")

# A tiny aggregated endpoint as an example: checks health of core services quickly

@router.api_route("/feast/{path:path}", methods=["GET","POST","PUT","PATCH","DELETE"])
async def feast(request: Request, path: str):
    return await _proxy(request, SERVICE_URLS["feature_store"], f"/api/v1/feast/{path}")

@router.api_route("/streams/{stream_name}/events", methods=["POST"])
async def stream_events(request: Request, stream_name: str):
    return await _proxy(request, SERVICE_URLS["stream_ingest"], f"/api/v1/streams/{stream_name}/events")

@router.get("/overview")
async def overview(request: Request, principal: Principal = Depends(get_principal)):
    await require(principal, domain="overview", method="GET")
    client: httpx.AsyncClient = request.app.state.http

    async def ping(name: str, base: str):
        try:
            r = await client.get(f"{base}/api/v1/healthz", headers=_fwd_headers(request))
            return {"name": name, "ok": r.status_code == 200}
        except Exception:
            return {"name": name, "ok": False}

    # manual gather (avoid python<3.11 taskgroup assumptions)
    import asyncio
    tasks = [
        ping("template-service", SERVICE_URLS["templates"]),
        ping("run-service", SERVICE_URLS["runs"]),
        ping("training-service", SERVICE_URLS["training"]),
        ping("registry-service", SERVICE_URLS["registry"]),
        ping("deployment-service", SERVICE_URLS["deployments"]),
        ping("artifact-service", SERVICE_URLS["artifacts"]),
        ping("metering-service", SERVICE_URLS["metering"]),
    ]
    checks = await asyncio.gather(*tasks)
    return {"ok": all(c["ok"] for c in checks), "checks": checks}

app.include_router(router)


