from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import func

from modelops.api.deps import ActorDep, DBSession
from modelops.domain.models import Deployment, InferenceLog

router = APIRouter()


@router.get("/summary")
def summary(tenant_id: str, db: DBSession, actor: ActorDep):
    if actor.tenant_id != tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    rows = (
        db.query(InferenceLog.deployment_id, InferenceLog.kind, func.count(InferenceLog.id), func.avg(InferenceLog.latency_ms))
        .filter(InferenceLog.tenant_id == tenant_id)
        .group_by(InferenceLog.deployment_id, InferenceLog.kind)
        .all()
    )

    out = []
    for dep_id, kind, cnt, avg_lat in rows:
        dep = db.query(Deployment).filter(Deployment.id == dep_id).first()
        out.append(
            {
                "deployment_id": dep_id,
                "deployment_name": dep.name if dep else "unknown",
                "kind": kind,
                "count": int(cnt),
                "avg_latency_ms": float(avg_lat or 0.0),
            }
        )
    return out
