from __future__ import annotations

from fastapi import APIRouter, Request
import asyncpg

from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError

from .metrics import (
    classification_accuracy,
    classification_macro_f1,
    regression_mae,
    regression_mse,
    exact_match_rate,
    retrieval_recall_at_k,
    retrieval_mrr_at_k,
)

app = create_app("llm-eval-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")


@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True, "service": "llm-eval-service"}


@router.post("/eval", status_code=201)
async def eval_run(request: Request, payload: dict):
    t = request.state.tenancy

    task = str(payload.get("task") or "").strip().lower()
    if not task:
        raise ApiError("BadRequest", "Missing task", 400)

    predictions = payload.get("predictions")
    labels = payload.get("labels")
    if not isinstance(predictions, list) or not isinstance(labels, list) or len(predictions) != len(labels):
        raise ApiError("BadRequest", "predictions and labels must be lists of equal length", 400)

    options = payload.get("options") or {}
    if not isinstance(options, dict):
        raise ApiError("BadRequest", "options must be an object", 400)

    metrics: dict = {}
    details: dict = {"task": task, "options": options}

    if task == "classification":
        metrics["accuracy"] = classification_accuracy(predictions, labels)
        metrics["macro_f1"] = classification_macro_f1(predictions, labels)
    elif task == "regression":
        try:
            y_pred = [float(x) for x in predictions]
            y_true = [float(x) for x in labels]
        except Exception as e:
            raise ApiError("BadRequest", f"regression expects numeric predictions/labels: {e}", 400)
        metrics["mae"] = regression_mae(y_pred, y_true)
        metrics["mse"] = regression_mse(y_pred, y_true)
    elif task == "exact_match":
        metrics["exact_match_rate"] = exact_match_rate([str(x) for x in predictions], [str(x) for x in labels])
    elif task == "retrieval":
        k = int(options.get("k", 10))
        ranked_lists = predictions
        relevant_lists = labels
        if not all(isinstance(x, list) for x in ranked_lists) or not all(isinstance(x, list) for x in relevant_lists):
            raise ApiError("BadRequest", "retrieval expects predictions/labels as list[list[Any]]", 400)
        metrics["recall_at_k"] = retrieval_recall_at_k(ranked_lists, relevant_lists, k)
        metrics["mrr_at_k"] = retrieval_mrr_at_k(ranked_lists, relevant_lists, k)
        details["k"] = k
    else:
        raise ApiError("BadRequest", f"Unsupported task: {task}", 400)

    model_version_id = payload.get("model_version_id")

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO llm_eval_runs(tenant_id, project_id, task, model_version_id, input_count, metrics, details, created_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               RETURNING id, task, model_version_id, input_count, metrics, details, created_by, created_at""",
            t.tenant_id, t.project_id, task, model_version_id, len(predictions), metrics, details, t.user_id
        )

    return dict(row)


@router.get("/eval/runs")
async def list_eval_runs(request: Request, limit: int = 50):
    t = request.state.tenancy
    limit = max(1, min(int(limit), 200))
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, task, model_version_id, input_count, metrics, created_by, created_at
               FROM llm_eval_runs
               WHERE tenant_id=$1 AND project_id=$2
               ORDER BY created_at DESC
               LIMIT $3""",
            t.tenant_id, t.project_id, limit
        )
    return {"items": [dict(r) for r in rows]}


@router.get("/eval/runs/{run_id}")
async def get_eval_run(request: Request, run_id: str):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, task, model_version_id, input_count, metrics, details, created_by, created_at
               FROM llm_eval_runs
               WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id, t.project_id, run_id
        )
    if not row:
        raise ApiError("NotFound", "Eval run not found", 404)
    return dict(row)


app.include_router(router)
