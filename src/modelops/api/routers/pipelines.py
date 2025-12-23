from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from modelops.api.deps import db_session, actor_from_header
from modelops.api.schemas import PipelineRunCreate, PipelineRunOut
from modelops.core.config import settings
from modelops.domain.models import PipelineRun, PipelineTemplate
from modelops.services.kfp import submit_kfp_run
from modelops.services.pipeline import ensure_tasks_for_run, template_kind

router = APIRouter()


@router.post("/runs", response_model=PipelineRunOut)
def create_run(payload: PipelineRunCreate, db: Session = Depends(db_session), actor=Depends(actor_from_header)) -> PipelineRunOut:
    if actor.tenant_id != payload.tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    r = PipelineRun(tenant_id=payload.tenant_id, project_id=payload.project_id, template_id=payload.template_id, parameters=payload.parameters, status="PENDING")
    db.add(r)
    db.commit()
    db.refresh(r)

    tpl = db.query(PipelineTemplate).filter(PipelineTemplate.id == payload.template_id).one()
    kind = template_kind(tpl.template_yaml)
    if settings.pipeline_backend == "mini" and kind != "MiniPipelineTemplate":
        raise HTTPException(status_code=400, detail="Template kind incompatible with mini pipeline backend")
    if settings.pipeline_backend == "kfp" and kind != "KfpPipelineTemplate":
        raise HTTPException(status_code=400, detail="Template kind incompatible with kfp pipeline backend")

    if settings.pipeline_backend == "kfp":
        submit_kfp_run(db, r)
    else:
        ensure_tasks_for_run(db, r)
    return PipelineRunOut.model_validate(r, from_attributes=True)


@router.get("/runs/{run_id}", response_model=PipelineRunOut)
def get_run(run_id: str, db: Session = Depends(db_session), actor=Depends(actor_from_header)) -> PipelineRunOut:
    r = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")
    if actor.tenant_id != r.tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    return PipelineRunOut.model_validate(r, from_attributes=True)
