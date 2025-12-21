from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from modelops.api.deps import db_session, actor_from_header
from modelops.api.schemas import PipelineRunCreate, PipelineRunOut
from modelops.domain.models import PipelineRun
from modelops.services.pipeline import ensure_tasks_for_run

router = APIRouter()


@router.post("/runs", response_model=PipelineRunOut)
def create_run(payload: PipelineRunCreate, db: Session = Depends(db_session), actor=Depends(actor_from_header)) -> PipelineRunOut:
    if actor.tenant_id != payload.tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    r = PipelineRun(tenant_id=payload.tenant_id, project_id=payload.project_id, template_id=payload.template_id, parameters=payload.parameters, status="PENDING")
    db.add(r)
    db.commit()
    db.refresh(r)

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
