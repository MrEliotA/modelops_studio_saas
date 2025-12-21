from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from modelops.api.deps import db_session, require_admin
from modelops.api.schemas import (
    TenantCreate,
    TenantOut,
    GPUNodePoolCreate,
    GPUNodePoolOut,
    PlanCreate,
    PlanOut,
    TemplateCreate,
    TemplateOut,
    TenantPlanCreate,
)
from modelops.domain.models import Tenant, GPUNodePool, Plan, PipelineTemplate, TenantPlan

router = APIRouter(dependencies=[Depends(require_admin)])


@router.post("/tenants", response_model=TenantOut)
def create_tenant(payload: TenantCreate, db: Session = Depends(db_session)) -> TenantOut:
    t = Tenant(name=payload.name)
    db.add(t)
    db.commit()
    db.refresh(t)
    return TenantOut.model_validate(t, from_attributes=True)


@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(db: Session = Depends(db_session)) -> list[TenantOut]:
    rows = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return [TenantOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/gpu/pools", response_model=GPUNodePoolOut)
def create_pool(payload: GPUNodePoolCreate, db: Session = Depends(db_session)) -> GPUNodePoolOut:
    p = GPUNodePool(**payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return GPUNodePoolOut.model_validate(p, from_attributes=True)


@router.get("/gpu/pools", response_model=list[GPUNodePoolOut])
def list_pools(db: Session = Depends(db_session)) -> list[GPUNodePoolOut]:
    rows = db.query(GPUNodePool).order_by(GPUNodePool.created_at.desc()).all()
    return [GPUNodePoolOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/plans", response_model=PlanOut)
def create_plan(payload: PlanCreate, db: Session = Depends(db_session)) -> PlanOut:
    p = Plan(**payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return PlanOut.model_validate(p, from_attributes=True)


@router.get("/plans", response_model=list[PlanOut])
def list_plans(db: Session = Depends(db_session)) -> list[PlanOut]:
    rows = db.query(Plan).order_by(Plan.created_at.desc()).all()
    return [PlanOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/tenants/{tenant_id}/plans")
def assign_plan(tenant_id: str, payload: TenantPlanCreate, db: Session = Depends(db_session)) -> dict:
    tp = TenantPlan(tenant_id=tenant_id, plan_id=payload.plan_id, gpu_pool_id=payload.gpu_pool_id, quota_concurrency=payload.quota_concurrency)
    db.add(tp)
    db.commit()
    return {"status": "ok", "tenant_plan_id": tp.id}


@router.post("/templates", response_model=TemplateOut)
def create_template(payload: TemplateCreate, db: Session = Depends(db_session)) -> TemplateOut:
    t = PipelineTemplate(**payload.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return TemplateOut.model_validate(t, from_attributes=True)
