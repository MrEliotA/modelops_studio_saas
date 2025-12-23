from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

from modelops.core.db import SessionLocal
from modelops.domain.models import (
    GPUNodePool,
    Job,
    PoolAllocation,
    UsageLedger,
)

# ---------------------------
# HTTP (generic) metrics
# ---------------------------
REQUESTS_TOTAL = Counter(
    "modelops_http_requests_total",
    "Total HTTP requests",
    ["component", "method", "route", "status"],
)

REQUEST_LATENCY = Histogram(
    "modelops_http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["component", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)


# ---------------------------
# Inference (tenant-aware) metrics
# ---------------------------
INFERENCE_REQUESTS_TOTAL = Counter(
    "modelops_inference_requests_total",
    "Total inference requests via gateway",
    ["tenant_id", "project_id", "deployment_id", "kind", "status", "code_class"],
)

INFERENCE_LATENCY = Histogram(
    "modelops_inference_request_duration_seconds",
    "Inference request duration in seconds (gateway to runtime)",
    ["tenant_id", "project_id", "deployment_id", "kind"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)


# ---------------------------
# Cost (FinOps) metrics (ledger-derived)
# ---------------------------
COST_30D_CENTS = Gauge(
    "modelops_cost_30d_cents",
    "Rolling 30-day cost in cents (derived from usage ledger)",
    ["tenant_id", "project_id"],
)


# ---------------------------
# GPU pool capacity metrics (allocator view)
# ---------------------------
POOL_CAPACITY_SHARES = Gauge(
    "modelops_pool_capacity_shares",
    "Logical capacity shares for a GPU pool",
    ["pool", "gpu_model", "mode"],
)
POOL_ALLOC_ACTIVE_UNITS = Gauge(
    "modelops_pool_allocations_active_units",
    "Active allocated units in a GPU pool",
    ["pool"],
)
POOL_ALLOC_AVAILABLE_UNITS = Gauge(
    "modelops_pool_allocations_available_units",
    "Available units in a GPU pool",
    ["pool"],
)
POOL_UTILIZATION_RATIO = Gauge(
    "modelops_pool_utilization_ratio",
    "Active/Capacity utilization ratio for a GPU pool",
    ["pool"],
)
POOL_JOBS_PENDING = Gauge(
    "modelops_pool_jobs_pending",
    "Jobs pending (not started) for a GPU pool",
    ["pool"],
)
POOL_JOBS_RUNNING = Gauge(
    "modelops_pool_jobs_running",
    "Jobs running for a GPU pool",
    ["pool"],
)


def _code_class(status_code: int) -> str:
    return f"{int(status_code) // 100}xx"


def observe_inference(
    tenant_id: str,
    project_id: str,
    deployment_id: str,
    kind: str,
    status: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    INFERENCE_REQUESTS_TOTAL.labels(
        tenant_id=tenant_id,
        project_id=project_id,
        deployment_id=deployment_id,
        kind=kind,
        status=status,
        code_class=_code_class(status_code),
    ).inc()

    INFERENCE_LATENCY.labels(
        tenant_id=tenant_id,
        project_id=project_id,
        deployment_id=deployment_id,
        kind=kind,
    ).observe(duration_seconds)


def instrument_fastapi(component: str) -> Callable:
    async def middleware(request: Request, call_next) -> Response:
        start = time.time()
        status = "500"
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            elapsed = time.time() - start
            # IMPORTANT: route template keeps label cardinality bounded.
            route_obj = request.scope.get("route")
            route = getattr(route_obj, "path", request.url.path)
            REQUESTS_TOTAL.labels(component=component, method=request.method, route=route, status=status).inc()
            REQUEST_LATENCY.labels(component=component, method=request.method, route=route).observe(elapsed)

    return middleware


def _unit_price_cents_for(pool: GPUNodePool | None, resource_type: str) -> int:
    # Minimal demo pricing table; in a real system, drive this from plan pricing.
    if resource_type == "endpoint_request":
        return 1  # $0.01 per request if you interpret 100 cents per dollar later
    if not pool:
        return 0
    if pool.mode == "MIG":
        return 25  # $0.25 per gpu-slice-minute (demo)
    return 5  # $0.05 per gpu-share-minute (demo)


def _refresh_cost_metrics(db) -> None:
    now = datetime.now(UTC)
    start = now - timedelta(days=30)
    rows = db.query(UsageLedger).filter(UsageLedger.created_at >= start).all()

    totals: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        meta = (r.meta or {})
        project_id = str(meta.get("project_id", "unknown"))

        pool = None
        pool_name = meta.get("pool")
        if pool_name:
            pool = db.query(GPUNodePool).filter(GPUNodePool.name == str(pool_name)).first()

        unit = _unit_price_cents_for(pool, r.resource_type)
        if r.resource_type in ("gpu_slice", "gpu_share"):
            qty = int(r.minutes) * max(1, int(r.quantity))
        elif r.resource_type == "endpoint_request":
            qty = int(r.requests) or 1
        else:
            qty = 0
        totals[(r.tenant_id, project_id)] += int(unit) * int(qty)

    for (tenant_id, project_id), cents in totals.items():
        COST_30D_CENTS.labels(tenant_id=tenant_id, project_id=project_id).set(cents)


def _refresh_pool_capacity_metrics(db) -> None:
    pools = db.query(GPUNodePool).all()
    for p in pools:
        POOL_CAPACITY_SHARES.labels(pool=p.name, gpu_model=p.gpu_model, mode=p.mode).set(int(p.capacity_shares))

        active_units = (
            db.query(PoolAllocation)
            .filter(PoolAllocation.pool_id == p.id)
            .filter(PoolAllocation.released_at.is_(None))
            .with_entities(PoolAllocation.units)
            .all()
        )
        active = sum(int(u[0]) for u in active_units) if active_units else 0
        available = max(0, int(p.capacity_shares) - active)

        POOL_ALLOC_ACTIVE_UNITS.labels(pool=p.name).set(active)
        POOL_ALLOC_AVAILABLE_UNITS.labels(pool=p.name).set(available)
        POOL_UTILIZATION_RATIO.labels(pool=p.name).set(active / max(1, int(p.capacity_shares)))

        pending = db.query(Job).filter(Job.gpu_pool_id == p.id).filter(Job.status.in_(["PENDING", "CREATED"])).count()
        running = db.query(Job).filter(Job.gpu_pool_id == p.id).filter(Job.status.in_(["RUNNING"])).count()
        POOL_JOBS_PENDING.labels(pool=p.name).set(pending)
        POOL_JOBS_RUNNING.labels(pool=p.name).set(running)


def metrics_response() -> Response:
    db = SessionLocal()
    try:
        _refresh_cost_metrics(db)
        _refresh_pool_capacity_metrics(db)
    finally:
        db.close()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
