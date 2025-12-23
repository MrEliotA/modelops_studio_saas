from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from modelops.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    namespace: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_project_tenant_name"),)


class GPUNodePool(Base):
    __tablename__ = "gpu_node_pools"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)
    gpu_model: Mapped[str] = mapped_column(String)
    mode: Mapped[str] = mapped_column(String)  # MIG | TIME_SLICE
    node_selector: Mapped[dict] = mapped_column(JSON)
    tolerations: Mapped[list] = mapped_column(JSON)
    gpu_resource_name: Mapped[str | None] = mapped_column(String, nullable=True)
    capacity_shares: Mapped[int] = mapped_column(Integer)
    timeslice_replicas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str] = mapped_column(String, default="")
    sla: Mapped[dict] = mapped_column(JSON)
    pricing: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TenantPlan(Base):
    __tablename__ = "tenant_plans"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), index=True)
    plan_id: Mapped[str] = mapped_column(String, ForeignKey("plans.id"), index=True)
    gpu_pool_id: Mapped[str] = mapped_column(String, ForeignKey("gpu_node_pools.id"), index=True)
    quota_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PoolAllocation(Base):
    __tablename__ = "pool_allocations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    pool_id: Mapped[str] = mapped_column(String, ForeignKey("gpu_node_pools.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)  # job | deployment
    ref_id: Mapped[str] = mapped_column(String, index=True)
    units: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), index=True)
    job_type: Mapped[str] = mapped_column(String)  # processing | training | drift
    gpu_pool_id: Mapped[str] = mapped_column(String, ForeignKey("gpu_node_pools.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="PENDING")  # PENDING/SUBMITTED/RUNNING/SUCCEEDED/FAILED
    k8s_job_name: Mapped[str | None] = mapped_column(String, nullable=True)
    image: Mapped[str] = mapped_column(String)
    command: Mapped[list] = mapped_column(JSON, default=list)
    args: Mapped[list] = mapped_column(JSON, default=list)
    env: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_units: Mapped[int] = mapped_column(Integer, default=1)
    requested_cpu: Mapped[str] = mapped_column(String, default="1")
    requested_memory: Mapped[str] = mapped_column(String, default="1Gi")
    artifact_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    metrics_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PipelineTemplate(Base):
    __tablename__ = "pipeline_templates"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, index=True)  # owner (admin for shared)
    name: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[str] = mapped_column(String, default="1.0.0")
    description: Mapped[str] = mapped_column(String, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    template_yaml: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "name", "version", name="uq_tpl_owner_name_ver"),)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    template_id: Mapped[str] = mapped_column(String, index=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PipelineTask(Base):
    __tablename__ = "pipeline_tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    type: Mapped[str] = mapped_column(String)  # k8s_job | register_model | deploy_model
    depends_on: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Model(Base):
    __tablename__ = "models"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_model_tenant_name"),)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    model_id: Mapped[str] = mapped_column(String, ForeignKey("models.id"), index=True)
    version: Mapped[str] = mapped_column(String)
    artifact_uri: Mapped[str] = mapped_column(String)
    metrics_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    stage: Mapped[str] = mapped_column(String, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_model_version"),)


class Deployment(Base):
    __tablename__ = "deployments"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    model_version_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    gpu_pool_id: Mapped[str] = mapped_column(String, index=True)
    k8s_deployment: Mapped[str] = mapped_column(String)
    k8s_service: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="CREATING")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InferenceLog(Base):
    __tablename__ = "inference_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    deployment_id: Mapped[str] = mapped_column(String, index=True)
    model_version_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)  # predict | explain
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UsageLedger(Base):
    __tablename__ = "usage_ledger"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    job_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    resource_type: Mapped[str] = mapped_column(String)  # gpu_slice | gpu_share | endpoint_request
    resource_sku: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    requests: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    period_start: Mapped[str] = mapped_column(String)
    period_end: Mapped[str] = mapped_column(String)
    total_amount: Mapped[int] = mapped_column(Integer, default=0)  # cents
    currency: Mapped[str] = mapped_column(String, default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    invoice_id: Mapped[str] = mapped_column(String, ForeignKey("invoices.id"), index=True)
    sku: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    unit_price_cents: Mapped[int] = mapped_column(Integer, default=0)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class DashboardAsset(Base):
    __tablename__ = "dashboard_assets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    scope: Mapped[str] = mapped_column(String)  # admin | user
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    dashboard_json: Mapped[dict] = mapped_column(JSON)
    tenant_id: Mapped[str | None] = mapped_column(String, nullable=True)  # null => global asset
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("scope", "name", "tenant_id", name="uq_dashboard_scope_name_tenant"),
    )
