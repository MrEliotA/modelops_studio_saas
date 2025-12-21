from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from modelops.domain.models import GPUNodePool, PoolAllocation, TenantPlan


class CapacityError(Exception):
    pass


def acquire_allocation(
    db: Session,
    tenant_id: str,
    pool_id: str,
    kind: str,
    ref_id: str,
    units: int,
) -> PoolAllocation:
    pool = db.query(GPUNodePool).filter(GPUNodePool.id == pool_id).one()

    # Pool capacity enforcement
    active_units = (
        db.query(func.coalesce(func.sum(PoolAllocation.units), 0))
        .filter(PoolAllocation.pool_id == pool_id, PoolAllocation.active.is_(True))
        .scalar()
    )
    if int(active_units) + units > int(pool.capacity_shares):
        raise CapacityError("Pool capacity exceeded")

    # Tenant quota enforcement (per pool)
    tp = (
        db.query(TenantPlan)
        .filter(
            TenantPlan.tenant_id == tenant_id,
            TenantPlan.gpu_pool_id == pool_id,
            TenantPlan.enabled.is_(True),
        )
        .first()
    )
    if tp:
        tenant_active = (
            db.query(func.coalesce(func.sum(PoolAllocation.units), 0))
            .filter(
                PoolAllocation.pool_id == pool_id,
                PoolAllocation.tenant_id == tenant_id,
                PoolAllocation.active.is_(True),
            )
            .scalar()
        )
        if int(tenant_active) + units > int(tp.quota_concurrency):
            raise CapacityError("Tenant quota exceeded")

    alloc = PoolAllocation(pool_id=pool_id, tenant_id=tenant_id, kind=kind, ref_id=ref_id, units=units, active=True)
    db.add(alloc)
    db.commit()
    db.refresh(alloc)
    return alloc


def release_allocation(db: Session, kind: str, ref_id: str) -> None:
    rows = db.query(PoolAllocation).filter(PoolAllocation.kind == kind, PoolAllocation.ref_id == ref_id, PoolAllocation.active.is_(True)).all()
    for r in rows:
        r.active = False
        db.add(r)
    db.commit()
