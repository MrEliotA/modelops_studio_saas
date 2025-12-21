from __future__ import annotations

from collections import defaultdict
from sqlalchemy.orm import Session

from modelops.domain.models import Invoice, InvoiceLineItem, UsageLedger


def create_invoice(db: Session, tenant_id: str, period_start: str, period_end: str, pricebook: dict) -> Invoice:
    rows = (
        db.query(UsageLedger)
        .filter(UsageLedger.tenant_id == tenant_id)
        .all()
    )

    sku_qty = defaultdict(int)
    for r in rows:
        if r.resource_type in ("gpu_slice", "gpu_share"):
            sku_qty[r.resource_sku] += int(r.minutes) * int(r.quantity)
        elif r.resource_type == "endpoint_request":
            sku_qty["endpoint_request"] += int(r.requests)

    inv = Invoice(tenant_id=tenant_id, period_start=period_start, period_end=period_end, total_amount=0, currency="USD")
    db.add(inv)
    db.commit()
    db.refresh(inv)

    total = 0
    for sku, qty in sku_qty.items():
        unit = int(pricebook.get(sku, 0))
        amount = unit * int(qty)
        total += amount
        db.add(InvoiceLineItem(invoice_id=inv.id, sku=sku, quantity=int(qty), unit_price_cents=unit, amount_cents=amount, meta={}))

    inv.total_amount = total
    db.add(inv)
    db.commit()
    return inv
