from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import and_

from modelops.domain.models import (
    GPUNodePool,
    Plan,
    TenantPlan,
    UsageLedger,
    Invoice,
    InvoiceLineItem,
)


def _to_cents(value) -> int:
    # Accept int (already cents) or float/str (dollars).
    if isinstance(value, int):
        return value
    d = Decimal(str(value))
    return int((d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _unit_price_cents_for(db: Session, tenant_id: str, pool_id: str | None, resource_type: str) -> int:
    plan = None
    if pool_id:
        tp = (
            db.query(TenantPlan)
            .filter(TenantPlan.tenant_id == tenant_id, TenantPlan.gpu_pool_id == pool_id, TenantPlan.enabled.is_(True))
            .first()
        )
        if tp:
            plan = db.query(Plan).filter(Plan.id == tp.plan_id).first()

    pricing = (plan.pricing if plan else {}) or {}
    if resource_type == "gpu_slice":
        return _to_cents(pricing.get("gpu_slice_minute", pricing.get("gpu_slice_minute_cents", 0)))
    if resource_type == "gpu_share":
        return _to_cents(pricing.get("gpu_share_minute", pricing.get("gpu_share_minute_cents", 0)))
    if resource_type == "endpoint_request":
        return _to_cents(pricing.get("endpoint_request", pricing.get("endpoint_request_cents", 0)))
    return 0


def create_invoice_for_period(db: Session, tenant_id: str, start: datetime, end: datetime) -> Invoice:
    rows = (
        db.query(UsageLedger)
        .filter(and_(UsageLedger.tenant_id == tenant_id, UsageLedger.created_at >= start, UsageLedger.created_at <= end))
        .order_by(UsageLedger.created_at.asc())
        .all()
    )

    # Key: (resource_type, pool_id, sku)
    agg = defaultdict(int)

    for r in rows:
        pool_name = (r.meta or {}).get("pool")
        pool_id = None
        if pool_name:
            pool = db.query(GPUNodePool).filter(GPUNodePool.name == pool_name).first()
            pool_id = pool.id if pool else None

        if r.resource_type in ("gpu_slice", "gpu_share"):
            minutes = int(r.minutes) * max(1, int(r.quantity))
            sku = r.resource_sku or r.resource_type
            agg[(r.resource_type, pool_id, sku)] += minutes
        elif r.resource_type == "endpoint_request":
            sku = "endpoint_request"
            agg[(r.resource_type, pool_id, sku)] += int(r.requests) or 1

    inv = Invoice(
        tenant_id=tenant_id,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        total_amount=0,
        currency="USD",
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)

    total = 0
    for (rtype, pool_id, sku), qty in agg.items():
        unit = _unit_price_cents_for(db, tenant_id, pool_id, rtype)
        amount = unit * int(qty)
        total += amount
        db.add(
            InvoiceLineItem(
                invoice_id=inv.id,
                sku=sku,
                quantity=int(qty),
                unit_price_cents=int(unit),
                amount_cents=int(amount),
                meta={"resource_type": rtype, "pool_id": pool_id},
            )
        )

    inv.total_amount = total
    db.add(inv)
    db.commit()
    return inv
