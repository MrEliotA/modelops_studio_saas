from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from modelops.api.deps import ActorDep, DBSession
from modelops.domain.models import Invoice, InvoiceLineItem
from modelops.services.invoicing import create_invoice_for_period

router = APIRouter()


@router.post("/invoices")
def create_invoice(tenant_id: str, start: datetime, end: datetime, db: DBSession, actor: ActorDep):
    if actor.tenant_id != tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    inv = create_invoice_for_period(db, tenant_id=tenant_id, start=start, end=end)
    return {"invoice_id": inv.id, "total_amount_cents": inv.total_amount, "currency": inv.currency}


@router.get("/invoices")
def list_invoices(tenant_id: str, db: DBSession, actor: ActorDep):
    if actor.tenant_id != tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    rows = db.query(Invoice).filter(Invoice.tenant_id == tenant_id).order_by(Invoice.created_at.desc()).all()
    return [{"id": r.id, "period_start": r.period_start, "period_end": r.period_end, "total_amount_cents": r.total_amount, "currency": r.currency} for r in rows]


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: str, db: DBSession, actor: ActorDep):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if actor.tenant_id != inv.tenant_id and actor.role != "admin":
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    lines = db.query(InvoiceLineItem).filter(InvoiceLineItem.invoice_id == inv.id).all()
    return {
        "id": inv.id,
        "tenant_id": inv.tenant_id,
        "period_start": inv.period_start,
        "period_end": inv.period_end,
        "total_amount_cents": inv.total_amount,
        "currency": inv.currency,
        "line_items": [
            {"sku": line.sku, "quantity": line.quantity, "unit_price_cents": line.unit_price_cents, "amount_cents": line.amount_cents, "meta": line.meta}
            for line in lines
        ],
    }
