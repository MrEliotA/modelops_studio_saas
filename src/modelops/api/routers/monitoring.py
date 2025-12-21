from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from modelops.api.deps import db_session, actor_from_header
from modelops.domain.models import InferenceLog, Deployment

router = APIRouter()


@router.get("/summary")
def summary(tenant_id: str, db: Session = Depends(db_session), actor=Depends(actor_from_header)):
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
