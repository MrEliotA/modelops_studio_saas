from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, HTTPException

from modelops.api.deps import ActorDep, DBSession
from modelops.core.metrics import observe_inference
from modelops.domain.models import Deployment, InferenceLog, Project
from modelops.services.metering import record_request_usage

router = APIRouter()


@router.get("")
def list_deployments(tenant_id: str, db: DBSession, actor: ActorDep):
    if actor.tenant_id != tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    rows = db.query(Deployment).filter(Deployment.tenant_id == tenant_id).order_by(Deployment.created_at.desc()).all()
    return [{"id": r.id, "name": r.name, "status": r.status, "k8s_service": r.k8s_service, "created_at": r.created_at} for r in rows]


async def _forward(db: DBSession, dep: Deployment, project: Project, path: str, payload: dict, kind: str):
    url = f"http://{dep.k8s_service}.{project.namespace}.svc.cluster.local{path}"
    start = time.time()
    status_code = 502
    status = "error"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=payload)
            status_code = r.status_code
            r.raise_for_status()
            data = r.json()
            status = "ok"
            return data
    except Exception:
        status = "error"
        raise
    finally:
        elapsed = time.time() - start
        observe_inference(
            tenant_id=dep.tenant_id,
            project_id=project.id,
            deployment_id=dep.id,
            kind=kind,
            status=status,
            status_code=status_code,
            duration_seconds=float(elapsed),
        )

        db.add(
            InferenceLog(
                tenant_id=dep.tenant_id,
                deployment_id=dep.id,
                model_version_id=dep.model_version_id,
                kind=kind,
                latency_ms=int(elapsed * 1000),
            )
        )

        record_request_usage(
            db,
            tenant_id=dep.tenant_id,
            deployment_id=dep.id,
            project_id=project.id,
            pool_name=None,
            kind=kind,
        )
        db.commit()


@router.post("/{deployment_id}/predict")
async def predict(deployment_id: str, payload: dict, db: DBSession, actor: ActorDep):
    dep = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not dep:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if actor.tenant_id != dep.tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    project = db.query(Project).filter(Project.id == dep.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return await _forward(db, dep, project, "/predict", payload, "predict")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail="Runtime error") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Runtime unavailable") from exc


@router.post("/{deployment_id}/explain")
async def explain(deployment_id: str, payload: dict, db: DBSession, actor: ActorDep):
    dep = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not dep:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if actor.tenant_id != dep.tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    project = db.query(Project).filter(Project.id == dep.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return await _forward(db, dep, project, "/explain", payload, "explain")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail="Runtime error") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Runtime unavailable") from exc
