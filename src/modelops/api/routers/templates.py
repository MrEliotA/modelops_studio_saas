from __future__ import annotations

from fastapi import APIRouter, HTTPException

from modelops.api.deps import ActorDep, DBSession
from modelops.api.schemas import TemplateOut
from modelops.domain.models import PipelineTemplate

router = APIRouter()


@router.get("", response_model=list[TemplateOut])
def list_templates(tenant_id: str, db: DBSession, actor: ActorDep) -> list[TemplateOut]:
    if actor.tenant_id != tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    rows = db.query(PipelineTemplate).filter(PipelineTemplate.tenant_id == tenant_id).order_by(PipelineTemplate.created_at.desc()).all()
    return [TemplateOut.model_validate(r, from_attributes=True) for r in rows]
