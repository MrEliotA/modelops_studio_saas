from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

import boto3
from botocore.client import Config
import joblib
import numpy as np
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, Histogram, CONTENT_TYPE_LATEST, generate_latest


# ---------------------------
# Identity labels (injected by platform)
# ---------------------------
TENANT_ID = os.getenv("TENANT_ID", "unknown")
PROJECT_ID = os.getenv("PROJECT_ID", "unknown")
DEPLOYMENT_ID = os.getenv("DEPLOYMENT_ID", os.getenv("SERVING_NAME", "unknown"))

MAX_CONCURRENCY = int(os.getenv("SERVING_MAX_CONCURRENCY", "32"))


# ---------------------------
# Runtime telemetry (RED + saturation)
# ---------------------------
HTTP_REQUESTS_TOTAL = Counter(
    "serving_http_requests_total",
    "Total HTTP requests handled by the runtime",
    ["method", "route", "status"],
)

HTTP_LATENCY = Histogram(
    "serving_http_request_latency_seconds",
    "HTTP request latency (runtime)",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)

INFLIGHT = Gauge(
    "serving_inflight_requests",
    "Requests currently executing in runtime",
    ["tenant_id", "project_id", "deployment_id", "kind"],
)

QUEUE_DEPTH = Gauge(
    "serving_queue_depth",
    "Approximate queue depth (waiting for a worker slot)",
    ["tenant_id", "project_id", "deployment_id", "kind"],
)

QUEUE_WAIT = Histogram(
    "serving_queue_wait_seconds",
    "Time spent waiting for a worker slot",
    ["tenant_id", "project_id", "deployment_id", "kind"],
    buckets=(0.0, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

GPU_UTIL = Gauge(
    "serving_gpu_utilization_percent",
    "GPU utilization percentage (best-effort; requires NVML)",
    ["tenant_id", "project_id", "deployment_id", "gpu"],
)

GPU_MEM_USED = Gauge(
    "serving_gpu_memory_used_bytes",
    "GPU memory used bytes (best-effort; requires NVML)",
    ["tenant_id", "project_id", "deployment_id", "gpu"],
)

GPU_MEM_TOTAL = Gauge(
    "serving_gpu_memory_total_bytes",
    "GPU memory total bytes (best-effort; requires NVML)",
    ["tenant_id", "project_id", "deployment_id", "gpu"],
)


# ---------------------------
# Concurrency limiter (simple queue model)
# ---------------------------
_sem = threading.Semaphore(MAX_CONCURRENCY)
_waiting = 0
_wait_lock = threading.Lock()


class PredictRequest(BaseModel):
    instances: List[List[float]] = Field(..., description="N x D float features")


class PredictResponse(BaseModel):
    predictions: List[int]
    probabilities: List[List[float]]


class ExplainRequest(BaseModel):
    instances: List[List[float]]


class ExplainResponse(BaseModel):
    explanations: List[dict]


@dataclass
class S3Cfg:
    endpoint: str
    region: str
    access_key: str
    secret_key: str
    bucket: str
    model_key: str


def s3_client(cfg: S3Cfg):
    return boto3.client(
        "s3",
        endpoint_url=cfg.endpoint,
        region_name=cfg.region,
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
        config=Config(signature_version="s3v4"),
    )


def _start_nvml_polling() -> None:
    enabled = os.getenv("SERVING_NVML_ENABLED", "true").lower() == "true"
    if not enabled:
        return

    try:
        from pynvml import (
            nvmlInit,
            nvmlDeviceGetCount,
            nvmlDeviceGetHandleByIndex,
            nvmlDeviceGetUtilizationRates,
            nvmlDeviceGetMemoryInfo,
        )
    except Exception:
        return

    def _loop():
        try:
            nvmlInit()
            while True:
                try:
                    n = int(nvmlDeviceGetCount())
                    for i in range(n):
                        h = nvmlDeviceGetHandleByIndex(i)
                        util = nvmlDeviceGetUtilizationRates(h)
                        mem = nvmlDeviceGetMemoryInfo(h)
                        GPU_UTIL.labels(TENANT_ID, PROJECT_ID, DEPLOYMENT_ID, str(i)).set(float(util.gpu))
                        GPU_MEM_USED.labels(TENANT_ID, PROJECT_ID, DEPLOYMENT_ID, str(i)).set(float(mem.used))
                        GPU_MEM_TOTAL.labels(TENANT_ID, PROJECT_ID, DEPLOYMENT_ID, str(i)).set(float(mem.total))
                except Exception:
                    pass
                time.sleep(5.0)
        except Exception:
            return

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


app = FastAPI(title="Serving Runtime", version="1.1.0")

_model = None


@app.on_event("startup")
def _load_model() -> None:
    global _model
    cfg = S3Cfg(
        endpoint=os.environ["S3_ENDPOINT"],
        region=os.environ.get("S3_REGION", "us-east-1"),
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
        bucket=os.environ["S3_BUCKET"],
        model_key=os.environ["S3_MODEL_URI"],
    )
    s3 = s3_client(cfg)
    path = "/tmp/model.pkl"
    s3.download_file(cfg.bucket, cfg.model_key, path)
    _model = joblib.load(path)

    _start_nvml_polling()


@app.middleware("http")
async def _mw(request: Request, call_next):
    start = time.time()
    status = "500"
    try:
        resp = await call_next(request)
        status = str(resp.status_code)
        return resp
    finally:
        dur = time.time() - start
        route_obj = request.scope.get("route")
        route = getattr(route_obj, "path", request.url.path)
        HTTP_REQUESTS_TOTAL.labels(method=request.method, route=route, status=status).inc()
        HTTP_LATENCY.labels(method=request.method, route=route).observe(dur)


def _execute(kind: str, fn):
    global _waiting
    t0 = time.time()
    with _wait_lock:
        _waiting += 1
        QUEUE_DEPTH.labels(TENANT_ID, PROJECT_ID, DEPLOYMENT_ID, kind).set(_waiting)

    acquired = _sem.acquire(timeout=60.0)
    wait = time.time() - t0

    with _wait_lock:
        _waiting = max(0, _waiting - 1)
        QUEUE_DEPTH.labels(TENANT_ID, PROJECT_ID, DEPLOYMENT_ID, kind).set(_waiting)

    if not acquired:
        raise RuntimeError("worker capacity exhausted")

    try:
        QUEUE_WAIT.labels(TENANT_ID, PROJECT_ID, DEPLOYMENT_ID, kind).observe(wait)
        INFLIGHT.labels(TENANT_ID, PROJECT_ID, DEPLOYMENT_ID, kind).inc()
        return fn()
    finally:
        INFLIGHT.labels(TENANT_ID, PROJECT_ID, DEPLOYMENT_ID, kind).dec()
        _sem.release()


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    def _fn():
        X = np.array(req.instances, dtype=np.float32)
        proba = _model.predict_proba(X)
        pred = proba.argmax(axis=1).astype(int).tolist()
        return PredictResponse(predictions=pred, probabilities=proba.tolist())

    return _execute("predict", _fn)


@app.post("/explain", response_model=ExplainResponse)
def explain(req: ExplainRequest) -> ExplainResponse:
    def _fn():
        X = np.array(req.instances, dtype=np.float32)
        out = []
        for row in X:
            idx = np.argsort(np.abs(row))[::-1][:8].tolist()
            out.append({"top_indices": idx, "top_values": [float(row[i]) for i in idx]})
        return ExplainResponse(explanations=out)

    return _execute("explain", _fn)
