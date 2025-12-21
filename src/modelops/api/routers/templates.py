from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from modelops.api.deps import db_session, actor_from_header
from modelops.api.schemas import TemplateOut
from modelops.domain.models import PipelineTemplate

router = APIRouter()


@router.get("", response_model=list[TemplateOut])
def list_templates(tenant_id: str, db: Session = Depends(db_session), actor=Depends(actor_from_header)) -> list[TemplateOut]:
    if actor.tenant_id != tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    rows = db.query(PipelineTemplate).filter(PipelineTemplate.tenant_id == tenant_id).order_by(PipelineTemplate.created_at.desc()).all()
    return [TemplateOut.model_validate(r, from_attributes=True) for r in rows]
