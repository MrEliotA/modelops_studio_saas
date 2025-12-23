from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
import yaml
from sqlalchemy.orm import Session

from modelops.core.config import settings
from modelops.domain.models import PipelineRun, PipelineTemplate

log = logging.getLogger("kfp")

KFP_STATUS_MAP = {
    "SUCCEEDED": "SUCCEEDED",
    "FAILED": "FAILED",
    "CANCELLED": "FAILED",
    "SKIPPED": "FAILED",
}


def submit_kfp_run(db: Session, run: PipelineRun) -> None:
    tpl = db.query(PipelineTemplate).filter(PipelineTemplate.id == run.template_id).one()
    doc = _load_template(tpl.template_yaml)
    if doc.get("kind") != "KfpPipelineTemplate":
        raise ValueError("Template kind must be KfpPipelineTemplate when pipeline_backend=kfp")

    spec = doc.get("spec", {})
    kfp_spec = spec.get("kfp", {})
    pipeline_id = kfp_spec.get("pipeline_id")
    if not pipeline_id:
        raise ValueError("kfp.pipeline_id is required")

    payload: dict[str, Any] = {
        "display_name": f"{tpl.name}-{run.id[:8]}",
        "pipeline_version_reference": {
            "pipeline_id": pipeline_id,
        },
    }

    pipeline_version_id = kfp_spec.get("pipeline_version_id")
    if pipeline_version_id:
        payload["pipeline_version_reference"]["pipeline_version_id"] = pipeline_version_id

    experiment_id = kfp_spec.get("experiment_id") or settings.kfp_default_experiment_id
    if experiment_id:
        payload["experiment_id"] = experiment_id

    if run.parameters:
        payload["runtime_config"] = {"parameters": run.parameters}

    base_url = settings.kfp_api_endpoint.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if settings.kfp_api_token:
        headers["Authorization"] = f"Bearer {settings.kfp_api_token}"

    try:
        with httpx.Client(
            base_url=base_url,
            timeout=settings.kfp_timeout_seconds,
            verify=settings.kfp_verify_ssl,
        ) as client:
            response = client.post("/apis/v2beta1/runs", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
    except Exception as exc:
        log.exception("kfp submit failed", extra={"run_id": run.id})
        run.status = "FAILED"
        run.finished_at = datetime.now(UTC)
        run.parameters = {**(run.parameters or {}), "kfp_error": str(exc)}
        db.add(run)
        db.commit()
        return

    run_id = body.get("run_id") or body.get("id")
    run.status = "RUNNING"
    run.parameters = {**(run.parameters or {}), "kfp_run_id": run_id}
    db.add(run)
    db.commit()


def refresh_kfp_run_status(db: Session, run: PipelineRun) -> None:
    kfp_run_id = (run.parameters or {}).get("kfp_run_id")
    if not kfp_run_id:
        return

    base_url = settings.kfp_api_endpoint.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if settings.kfp_api_token:
        headers["Authorization"] = f"Bearer {settings.kfp_api_token}"

    try:
        with httpx.Client(
            base_url=base_url,
            timeout=settings.kfp_timeout_seconds,
            verify=settings.kfp_verify_ssl,
        ) as client:
            response = client.get(f"/apis/v2beta1/runs/{kfp_run_id}", headers=headers)
            response.raise_for_status()
            body = response.json()
    except Exception:
        log.exception("kfp status refresh failed", extra={"run_id": run.id})
        return

    state = body.get("state") or body.get("status")
    if not state:
        return
    mapped = KFP_STATUS_MAP.get(state.upper())
    if not mapped:
        return

    run.status = mapped
    run.finished_at = datetime.now(UTC)
    db.add(run)
    db.commit()


def _load_template(yaml_text: str) -> dict[str, Any]:
    doc = yaml.safe_load(yaml_text)
    if not isinstance(doc, dict) or "kind" not in doc:
        raise ValueError("Invalid template format")
    return doc
