from __future__ import annotations

import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from modelops.api.deps import db_session, actor_from_header
from modelops.api.schemas import ProjectCreate, ProjectOut
from modelops.domain.models import Project, Tenant
from modelops.k8s.manager import ensure_namespace

router = APIRouter()


def _namespace(tenant_id: str, name: str) -> str:
    safe = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:20]
    return f"t-{tenant_id[:8]}-{safe}"


@router.post("", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(db_session), actor=Depends(actor_from_header)) -> ProjectOut:
    if actor.tenant_id != payload.tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    ns = _namespace(payload.tenant_id, payload.name)
    ensure_namespace(ns)

    p = Project(tenant_id=payload.tenant_id, name=payload.name, namespace=ns)
    db.add(p)
    db.commit()
    db.refresh(p)
    return ProjectOut.model_validate(p, from_attributes=True)


@router.get("", response_model=list[ProjectOut])
def list_projects(tenant_id: str, db: Session = Depends(db_session), actor=Depends(actor_from_header)) -> list[ProjectOut]:
    if actor.tenant_id != tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    rows = db.query(Project).filter(Project.tenant_id == tenant_id).order_by(Project.created_at.desc()).all()
    return [ProjectOut.model_validate(r, from_attributes=True) for r in rows]
