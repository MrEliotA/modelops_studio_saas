from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    tenant_id: str
    user_id: str
    role: str = "admin"


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)


class TenantOut(BaseModel):
    id: str
    name: str
    created_at: datetime


class ProjectCreate(BaseModel):
    tenant_id: str
    name: str = Field(min_length=2, max_length=64)


class ProjectOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    namespace: str
    created_at: datetime


class GPUNodePoolCreate(BaseModel):
    name: str
    gpu_model: str
    mode: str
    node_selector: dict
    tolerations: list
    gpu_resource_name: str | None = None
    capacity_shares: int
    timeslice_replicas: int | None = None


class GPUNodePoolOut(GPUNodePoolCreate):
    id: str
    created_at: datetime


class PlanCreate(BaseModel):
    name: str
    description: str = ""
    sla: dict
    pricing: dict


class PlanOut(BaseModel):
    id: str
    name: str
    description: str
    sla: dict
    pricing: dict
    created_at: datetime


class TenantPlanCreate(BaseModel):
    plan_id: str
    gpu_pool_id: str
    quota_concurrency: int = 1


class TemplateCreate(BaseModel):
    tenant_id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    tags: list[str] = []
    template_yaml: str


class TemplateOut(BaseModel):
    id: str
    tenant_id: str
    name: str
    version: str
    description: str
    tags: list[str]
    created_at: datetime


class PipelineRunCreate(BaseModel):
    tenant_id: str
    project_id: str
    template_id: str
    parameters: dict = {}


class PipelineRunOut(BaseModel):
    id: str
    tenant_id: str
    project_id: str
    template_id: str
    status: str
    created_at: datetime
    finished_at: datetime | None


class UsageOut(BaseModel):
    resource_type: str
    resource_sku: str
    minutes: int
    requests: int
    created_at: datetime
    meta: dict
