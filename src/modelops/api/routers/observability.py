from __future__ import annotations

import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from modelops.api.deps import db_session, actor_from_header
from modelops.domain.models import DashboardAsset


router = APIRouter()


class DashboardUpsert(BaseModel):
    scope: str = Field(..., description="admin | user")
    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    dashboard_json: dict[str, Any]
    tenant_id: str | None = Field(default=None, description="null => global asset")


def _can_read(actor, asset: DashboardAsset) -> bool:
    if asset.scope == "admin":
        return actor.role == "admin"
    # user-scope: tenant-bound or global
    return asset.tenant_id is None or actor.tenant_id == asset.tenant_id or actor.role == "admin"


def _can_write(actor, asset: DashboardAsset | None, body: DashboardUpsert) -> bool:
    # Admin dashboards: admin only
    if body.scope == "admin":
        return actor.role == "admin"
    # User dashboards: tenant admin or platform admin. In this demo, role=admin is platform admin.
    if body.tenant_id is not None and actor.tenant_id != body.tenant_id and actor.role != "admin":
        return False
    return True


@router.get("/dashboards")
def list_dashboards(scope: str, tenant_id: str | None = None, db: Session = Depends(db_session), actor=Depends(actor_from_header)):
    if scope not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="scope must be admin|user")

    q = db.query(DashboardAsset).filter(DashboardAsset.scope == scope)
    if tenant_id is not None:
        q = q.filter((DashboardAsset.tenant_id == tenant_id) | (DashboardAsset.tenant_id.is_(None)))

    rows = q.order_by(DashboardAsset.updated_at.desc()).all()
    out = []
    for r in rows:
        if not _can_read(actor, r):
            continue
        out.append(
            {
                "id": r.id,
                "scope": r.scope,
                "name": r.name,
                "description": r.description,
                "tags": r.tags or [],
                "tenant_id": r.tenant_id,
                "updated_at": r.updated_at,
            }
        )
    return out


@router.get("/dashboards/{dashboard_id}")
def get_dashboard(dashboard_id: str, db: Session = Depends(db_session), actor=Depends(actor_from_header)):
    r = db.query(DashboardAsset).filter(DashboardAsset.id == dashboard_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="dashboard not found")
    if not _can_read(actor, r):
        raise HTTPException(status_code=403, detail="forbidden")
    return {
        "id": r.id,
        "scope": r.scope,
        "name": r.name,
        "description": r.description,
        "tags": r.tags or [],
        "tenant_id": r.tenant_id,
        "dashboard_json": r.dashboard_json,
        "updated_at": r.updated_at,
    }


@router.post("/dashboards")
def create_dashboard(body: DashboardUpsert, db: Session = Depends(db_session), actor=Depends(actor_from_header)):
    if body.scope not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="scope must be admin|user")
    if not _can_write(actor, None, body):
        raise HTTPException(status_code=403, detail="forbidden")

    r = DashboardAsset(
        scope=body.scope,
        name=body.name,
        description=body.description,
        tags=body.tags,
        dashboard_json=body.dashboard_json,
        tenant_id=body.tenant_id,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id}


@router.put("/dashboards/{dashboard_id}")
def update_dashboard(dashboard_id: str, body: DashboardUpsert, db: Session = Depends(db_session), actor=Depends(actor_from_header)):
    r = db.query(DashboardAsset).filter(DashboardAsset.id == dashboard_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="dashboard not found")
    if not _can_read(actor, r):
        raise HTTPException(status_code=403, detail="forbidden")
    if not _can_write(actor, r, body):
        raise HTTPException(status_code=403, detail="forbidden")

    r.scope = body.scope
    r.name = body.name
    r.description = body.description
    r.tags = body.tags
    r.dashboard_json = body.dashboard_json
    r.tenant_id = body.tenant_id
    db.commit()
    return {"status": "ok"}


@router.delete("/dashboards/{dashboard_id}")
def delete_dashboard(dashboard_id: str, db: Session = Depends(db_session), actor=Depends(actor_from_header)):
    r = db.query(DashboardAsset).filter(DashboardAsset.id == dashboard_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="dashboard not found")
    if r.scope == "admin" and actor.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    if r.tenant_id is not None and actor.tenant_id != r.tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")

    db.delete(r)
    db.commit()
    return {"status": "ok"}


@router.get("/dashboards/{dashboard_id}/export_configmap")
def export_configmap(
    dashboard_id: str,
    namespace: str = "monitoring",
    configmap_name: str | None = None,
    db: Session = Depends(db_session),
    actor=Depends(actor_from_header),
):
    r = db.query(DashboardAsset).filter(DashboardAsset.id == dashboard_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="dashboard not found")
    if not _can_read(actor, r):
        raise HTTPException(status_code=403, detail="forbidden")

    cm_name = configmap_name or f"modelops-dashboard-{r.scope}-{r.name.lower().replace(' ', '-')[:40]}"
    json_filename = f"{r.name.lower().replace(' ', '_')}.json"
    payload = json.dumps(r.dashboard_json, indent=2)
    yaml = f"""apiVersion: v1
kind: ConfigMap
metadata:
  name: {cm_name}
  namespace: {namespace}
  labels:
    grafana_dashboard: "1"
data:
  {json_filename}: |
""" + "\n".join(["    " + line for line in payload.splitlines()]) + "\n"

    return {"configmap_yaml": yaml}
