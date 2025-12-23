from __future__ import annotations

import os

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from modelops.api.routers import (
    admin,
    auth,
    billing,
    deployments,
    monitoring,
    observability,
    pipelines,
    projects,
    templates,
    usage,
)
from modelops.core.db import Base, SessionLocal, engine
from modelops.core.logging import configure_logging
from modelops.core.metrics import instrument_fastapi, metrics_response
from modelops.services.dashboard_seed import seed_builtin_dashboards

configure_logging("INFO")

app = FastAPI(title="ModelOps Studio", version="1.0.0")

app.middleware("http")(instrument_fastapi("api"))

@app.get("/metrics")
def metrics() -> Response:
    return metrics_response()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    # Seed built-in dashboards into DB for UI/API usage.
    db = SessionLocal()
    try:
        repo_root = os.getenv("MODELOPS_REPO_ROOT", os.getcwd())
        seed_builtin_dashboards(db, repo_root=repo_root)
    finally:
        db.close()

app.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
app.include_router(admin.router, prefix="/v1/admin", tags=["admin"])
app.include_router(projects.router, prefix="/v1/projects", tags=["projects"])
app.include_router(templates.router, prefix="/v1/templates", tags=["templates"])
app.include_router(pipelines.router, prefix="/v1/pipelines", tags=["pipelines"])
app.include_router(deployments.router, prefix="/v1/deployments", tags=["deployments"])
app.include_router(usage.router, prefix="/v1/usage", tags=["usage"])
app.include_router(monitoring.router, prefix="/v1/monitoring", tags=["monitoring"])
app.include_router(billing.router, prefix="/v1/billing", tags=["billing"])
app.include_router(observability.router, prefix="/v1/observability", tags=["observability"])
