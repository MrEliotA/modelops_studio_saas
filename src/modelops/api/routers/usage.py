from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_

from modelops.api.deps import db_session, actor_from_header
from modelops.domain.models import UsageLedger

router = APIRouter()


@router.get("/ledger")
def ledger(tenant_id: str, start: datetime, end: datetime, db: Session = Depends(db_session), actor=Depends(actor_from_header)):
    if actor.tenant_id != tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    rows = (
        db.query(UsageLedger)
        .filter(and_(UsageLedger.tenant_id == tenant_id, UsageLedger.created_at >= start, UsageLedger.created_at <= end))
        .order_by(UsageLedger.created_at.desc())
        .all()
    )
    return [
        {
            "resource_type": r.resource_type,
            "resource_sku": r.resource_sku,
            "minutes": r.minutes,
            "requests": r.requests,
            "created_at": r.created_at,
            "meta": r.meta,
        }
        for r in rows
    ]
