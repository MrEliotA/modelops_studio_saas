from __future__ import annotations

import logging
from datetime import UTC, datetime

from kubernetes.client import ApiException
from sqlalchemy.orm import Session

from modelops.domain.models import Job, Project
from modelops.k8s.client import batch, load

log = logging.getLogger("k8s-reconcile")


def _now():
    return datetime.now(UTC)


def reconcile_jobs(db: Session) -> None:
    load()
    api = batch()

    jobs = db.query(Job).filter(Job.k8s_job_name.isnot(None)).all()
    for j in jobs:
        if j.status in ("SUCCEEDED", "FAILED"):
            continue

        project = db.query(Project).filter(Project.id == j.project_id).first()
        if not project:
            continue

        try:
            k = api.read_namespaced_job(name=j.k8s_job_name, namespace=project.namespace)
        except ApiException:
            continue
        except Exception:
            continue

        active = (k.status.active or 0) > 0
        succeeded = (k.status.succeeded or 0) > 0
        failed = (k.status.failed or 0) > 0

        if active and j.status != "RUNNING":
            j.status = "RUNNING"
            j.started_at = _now()

        if succeeded:
            j.status = "SUCCEEDED"
            j.finished_at = _now()
        elif failed:
            j.status = "FAILED"
            j.finished_at = _now()

        db.add(j)
