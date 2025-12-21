from __future__ import annotations

import logging
import time
from prometheus_client import Counter, start_http_server

from sqlalchemy.orm import Session

from modelops.core.config import settings
from modelops.core.logging import configure_logging
from modelops.core.db import SessionLocal
from modelops.domain.models import PipelineRun
from modelops.services.pipeline import reconcile_pipeline_run
from modelops.services.k8s_reconcile import reconcile_jobs

configure_logging("INFO")
log = logging.getLogger("controller")

TICKS_TOTAL = Counter("controller_ticks_total", "Controller ticks")
ERRORS_TOTAL = Counter("controller_errors_total", "Controller errors")



def tick() -> None:
    TICKS_TOTAL.inc()
    db: Session = SessionLocal()
    try:
        reconcile_jobs(db)

        runs = db.query(PipelineRun).filter(PipelineRun.status == "RUNNING").all()
        for r in runs:
            reconcile_pipeline_run(db, r)

        db.commit()
    except Exception:
        ERRORS_TOTAL.inc()
        raise
    finally:
        db.close()


def main() -> None:
    start_http_server(8000)
    log.info("controller started", extra={"tick_seconds": settings.controller_tick_seconds})
    while True:
        tick()
        time.sleep(settings.controller_tick_seconds)


if __name__ == "__main__":
    main()
