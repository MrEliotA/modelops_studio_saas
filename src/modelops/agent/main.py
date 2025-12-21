from __future__ import annotations

import logging
import time
from prometheus_client import Counter, start_http_server
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from modelops.core.config import settings
from modelops.core.logging import configure_logging
from modelops.core.db import SessionLocal
from modelops.domain.models import Job, UsageLedger
from modelops.services.metering import record_job_usage
from modelops.services.allocator import release_allocation

configure_logging("INFO")
log = logging.getLogger("agent")

TICKS_TOTAL = Counter("agent_ticks_total", "Agent ticks")
JOBS_METERED_TOTAL = Counter("jobs_metered_total", "Jobs metered")



def _now() -> datetime:
    return datetime.now(timezone.utc)


def tick() -> None:
    TICKS_TOTAL.inc()
    db: Session = SessionLocal()
    try:
        # Jobs that finished but are not metered yet
        jobs = db.query(Job).filter(Job.finished_at.isnot(None)).all()
        for j in jobs:
            exists = db.query(UsageLedger).filter(UsageLedger.job_id == j.id).first()
            if exists:
                continue
            if not j.started_at or not j.finished_at:
                continue
            minutes = max(1, int((j.finished_at - j.started_at).total_seconds() // 60))
            record_job_usage(db, j, minutes)
            JOBS_METERED_TOTAL.inc()
            release_allocation(db, kind="job", ref_id=j.k8s_job_name or j.id)

        db.commit()
    finally:
        db.close()


def main() -> None:
    start_http_server(8000)
    log.info("agent started", extra={"tick_seconds": settings.agent_tick_seconds})
    while True:
        tick()
        time.sleep(settings.agent_tick_seconds)


if __name__ == "__main__":
    main()
