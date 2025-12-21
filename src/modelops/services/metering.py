from __future__ import annotations

from sqlalchemy.orm import Session

from modelops.domain.models import GPUNodePool, Job, UsageLedger


def record_job_usage(db: Session, job: Job, minutes: int) -> None:
    pool = db.query(GPUNodePool).filter(GPUNodePool.id == job.gpu_pool_id).first()
    if not pool:
        return

    if pool.mode == "MIG":
        rtype = "gpu_slice"
        sku = f"{pool.gpu_model}-slice"
    else:
        rtype = "gpu_share"
        r = pool.timeslice_replicas or 4
        sku = f"{pool.gpu_model}-share-r{r}"

    db.add(
        UsageLedger(
            tenant_id=job.tenant_id,
            job_id=job.id,
            resource_type=rtype,
            resource_sku=sku,
            quantity=max(1, job.requested_units),
            minutes=minutes,
            requests=0,
            meta={"pool": pool.name, "mode": pool.mode, "project_id": job.project_id},
        )
    )


def record_request_usage(db: Session, tenant_id: str, deployment_id: str, project_id: str, pool_name: str | None, kind: str) -> None:
    db.add(
        UsageLedger(
            tenant_id=tenant_id,
            job_id=None,
            resource_type="endpoint_request",
            resource_sku=f"{kind}",
            quantity=1,
            minutes=0,
            requests=1,
            meta={"deployment_id": deployment_id, "project_id": project_id, "pool": pool_name},
        )
    )
