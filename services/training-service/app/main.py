from __future__ import annotations
from fastapi import APIRouter, Request
import asyncpg
import os, yaml
from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError
from mlops_common.nats_client import connect as nats_connect, ensure_streams, publish

app = create_app("training-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")

def load_profiles(path: str) -> dict[str, dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    profs = data.get("profiles") or []
    return {p["name"]: p for p in profs if p.get("name")}

@app.on_event("startup")
async def _startup():
    # NATS
    nc = await nats_connect()
    app.state.nats = nc
    app.state.js = nc.jetstream()
    await ensure_streams(app.state.js)

    # Compute profiles
    path = os.getenv("COMPUTE_PROFILES_PATH", "/app/config/compute_profiles.yaml")
    try:
        app.state.compute_profiles = load_profiles(path)
    except Exception:
        app.state.compute_profiles = {}

@app.on_event("shutdown")
async def _shutdown():
    nc = getattr(app.state, "nats", None)
    if nc:
        await nc.drain()

@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True}

@router.get("/compute-profiles")
async def list_profiles(request: Request):
    # This simulates a ConfigMap-driven catalog
    return {"items": list(request.app.state.compute_profiles.values())}

@router.post("/training-jobs", status_code=201)
async def create_training_job(request: Request, payload: dict):
    t = request.state.tenancy
    compute_profile = payload.get("compute_profile")
    if compute_profile and compute_profile not in request.app.state.compute_profiles:
        raise ApiError("BadRequest", f"Unknown compute_profile: {compute_profile}", 400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO training_jobs(tenant_id, project_id, run_id, status, compute_profile, image, command, dataset_uri, output_uri, created_by)
               VALUES ($1,$2,$3,'QUEUED',$4,$5,$6,$7,$8,$9)
               RETURNING id, run_id, status, compute_profile, image, command, dataset_uri, output_uri, created_by, created_at, updated_at""",
            t.tenant_id, t.project_id, payload.get("run_id"), compute_profile, payload.get("image"),
            payload.get("command", []), payload.get("dataset_uri"), payload.get("output_uri"), t.user_id
        )

    job = dict(row)
    await publish(request.app.state.js, "mlops.training.requested", {
        "tenant_id": str(t.tenant_id),
        "project_id": str(t.project_id),
        "training_job_id": str(job["id"]),
        "run_id": str(job["run_id"]) if job.get("run_id") else None,
        "compute_profile": job.get("compute_profile"),
        "image": job.get("image"),
        "command": job.get("command"),
        "dataset_uri": job.get("dataset_uri"),
        "output_uri": job.get("output_uri"),
    })
    return job

@router.get("/training-jobs")
async def list_training_jobs(request: Request):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, run_id, status, compute_profile, image, command, dataset_uri, output_uri, mlflow_run_id, created_by, created_at, updated_at
               FROM training_jobs WHERE tenant_id=$1 AND project_id=$2 ORDER BY created_at DESC""",
            t.tenant_id, t.project_id
        )
    return {"items":[dict(r) for r in rows]}

@router.get("/training-jobs/{job_id}")
async def get_training_job(request: Request, job_id: str):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, run_id, status, compute_profile, image, command, dataset_uri, output_uri, mlflow_run_id, created_by, created_at, updated_at
               FROM training_jobs WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id, t.project_id, job_id
        )
    if not row:
        raise ApiError("NotFound","Training job not found",404)
    return dict(row)

app.include_router(router)
