from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import yaml
from sqlalchemy.orm import Session

from modelops.artifacts.s3 import ensure_bucket, s3_uri
from modelops.domain.models import (
    Deployment,
    GPUNodePool,
    Job,
    Model,
    ModelVersion,
    PipelineRun,
    PipelineTask,
    PipelineTemplate,
    Project,
)
from modelops.k8s.manager import create_job, create_serving_deployment, ensure_namespace
from modelops.services.allocator import CapacityError, acquire_allocation

log = logging.getLogger("pipeline")


def _now() -> datetime:
    return datetime.now(UTC)


def _load_template(yaml_text: str) -> dict[str, Any]:
    doc = yaml.safe_load(yaml_text)
    if not isinstance(doc, dict) or "kind" not in doc:
        raise ValueError("Invalid template format")
    return doc


def template_kind(yaml_text: str) -> str:
    return str(_load_template(yaml_text).get("kind"))


def _parse_mini_template(yaml_text: str) -> dict[str, Any]:
    doc = _load_template(yaml_text)
    if doc.get("kind") != "MiniPipelineTemplate":
        raise ValueError("Invalid template kind")
    return doc


def ensure_tasks_for_run(db: Session, run: PipelineRun) -> None:
    existing = db.query(PipelineTask).filter(PipelineTask.run_id == run.id).count()
    if existing > 0:
        return

    tpl = db.query(PipelineTemplate).filter(PipelineTemplate.id == run.template_id).one()
    doc = _load_template(tpl.template_yaml)
    if doc.get("kind") != "MiniPipelineTemplate":
        log.info("skipping task creation for non-mini template", extra={"template_id": tpl.id})
        return
    tasks = doc["spec"]["tasks"]

    for t in tasks:
        task = PipelineTask(
            run_id=run.id,
            name=t["name"],
            type=t["type"],
            depends_on=t.get("depends_on", []),
            status="PENDING",
            output={},
        )
        db.add(task)

    run.status = "RUNNING"
    db.add(run)
    db.commit()


def reconcile_pipeline_run(db: Session, run: PipelineRun) -> None:
    tpl = db.query(PipelineTemplate).filter(PipelineTemplate.id == run.template_id).one()
    doc = _load_template(tpl.template_yaml)
    if doc.get("kind") != "MiniPipelineTemplate":
        return

    ensure_tasks_for_run(db, run)

    tasks = db.query(PipelineTask).filter(PipelineTask.run_id == run.id).all()
    tasks_by_name = {t.name: t for t in tasks}

    # Find next runnable task
    runnable = None
    for t in tasks:
        if t.status in ("SUCCEEDED", "FAILED", "RUNNING"):
            continue
        deps = t.depends_on or []
        if all(tasks_by_name[d].status == "SUCCEEDED" for d in deps):
            runnable = t
            break

    if runnable is None:
        # If any failed -> run failed, else succeeded.
        if any(t.status == "FAILED" for t in tasks):
            run.status = "FAILED"
        else:
            run.status = "SUCCEEDED"
        run.finished_at = _now()
        db.add(run)
        db.commit()
        return

    # Execute runnable
    if runnable.type == "k8s_job":
        _exec_k8s_job(db, run, runnable)
        return
    if runnable.type == "register_model":
        _exec_register(db, run, runnable)
        return
    if runnable.type == "deploy_model":
        _exec_deploy(db, run, runnable)
        return

    runnable.status = "FAILED"
    runnable.output = {"error": f"Unsupported task type: {runnable.type}"}
    runnable.finished_at = _now()
    db.add(runnable)
    db.commit()


def _pool_by_name(db: Session, name: str) -> GPUNodePool:
    p = db.query(GPUNodePool).filter(GPUNodePool.name == name).first()
    if not p:
        raise ValueError(f"Unknown pool: {name}")
    return p


def _exec_k8s_job(db: Session, run: PipelineRun, task: PipelineTask) -> None:
    tpl = db.query(PipelineTemplate).filter(PipelineTemplate.id == run.template_id).one()
    doc = _parse_mini_template(tpl.template_yaml)
    tdef = next(x for x in doc["spec"]["tasks"] if x["name"] == task.name)

    project = db.query(Project).filter(Project.id == run.project_id).one()
    ensure_namespace(project.namespace)
    ensure_bucket()

    pool = _pool_by_name(db, tdef["pool"])

    # One job per task execution
    k8s_name = f"{task.name}-{run.id[:8]}"

    # Allocate pool capacity (kind demo)
    try:
        acquire_allocation(db, run.tenant_id, pool.id, "job", k8s_name, units=1)
    except CapacityError as e:
        # Keep task pending; controller will retry.
        log.info("allocation blocked", extra={"run_id": run.id, "task": task.name, "error": str(e)})
        return

    artifact_key = f"{run.tenant_id}/{run.project_id}/runs/{run.id}/model.pkl"
    metrics_key = f"{run.tenant_id}/{run.project_id}/runs/{run.id}/metrics.json"

    job = Job(
        tenant_id=run.tenant_id,
        project_id=run.project_id,
        job_type="training",
        gpu_pool_id=pool.id,
        status="SUBMITTED",
        k8s_job_name=k8s_name,
        image=tdef["image"],
        command=tdef.get("command", []),
        args=[],
        env={
            "S3_ENDPOINT": "http://minio.modelops-system.svc.cluster.local:9000",
            "S3_ACCESS_KEY": "minio",
            "S3_SECRET_KEY": "minio12345",
            "S3_BUCKET": "artifacts",
            "S3_MODEL_KEY": artifact_key,
            "S3_METRICS_KEY": metrics_key,
        },
        requested_units=1,
        requested_cpu="1",
        requested_memory="1Gi",
        artifact_uri=s3_uri(artifact_key),
        metrics_uri=s3_uri(metrics_key),
    )
    db.add(job)

    task.status = "RUNNING"
    task.started_at = _now()
    db.add(task)
    db.commit()

    create_job(
        namespace=project.namespace,
        name=k8s_name,
        image=job.image,
        command=job.command,
        args=job.args,
        env={str(k): str(v) for k, v in (job.env or {}).items()},
        cpu=job.requested_cpu,
        memory=job.requested_memory,
        node_selector=pool.node_selector,
        tolerations=pool.tolerations,
        gpu_resource_name=pool.gpu_resource_name,
        gpu_units=job.requested_units,
    )


def _latest_training_job(db: Session, run: PipelineRun) -> Job | None:
    return (
        db.query(Job)
        .filter(Job.tenant_id == run.tenant_id, Job.project_id == run.project_id, Job.job_type == "training")
        .order_by(Job.created_at.desc())
        .first()
    )


def _exec_register(db: Session, run: PipelineRun, task: PipelineTask) -> None:
    tpl = db.query(PipelineTemplate).filter(PipelineTemplate.id == run.template_id).one()
    doc = _parse_mini_template(tpl.template_yaml)
    tdef = next(x for x in doc["spec"]["tasks"] if x["name"] == task.name)

    job = _latest_training_job(db, run)
    if not job or job.status != "SUCCEEDED":
        return

    model_name = tdef["model_name"]
    model = db.query(Model).filter(Model.tenant_id == run.tenant_id, Model.name == model_name).first()
    if not model:
        model = Model(tenant_id=run.tenant_id, name=model_name, description="")
        db.add(model)
        db.commit()
        db.refresh(model)

    mv = ModelVersion(
        model_id=model.id,
        version=run.id[:8],
        artifact_uri=job.artifact_uri or "",
        metrics_uri=job.metrics_uri,
        stage="STAGING",
    )
    db.add(mv)

    task.status = "SUCCEEDED"
    task.output = {"model_id": model.id, "model_version_id": mv.id}
    task.finished_at = _now()
    db.add(task)
    db.commit()


def _exec_deploy(db: Session, run: PipelineRun, task: PipelineTask) -> None:
    tpl = db.query(PipelineTemplate).filter(PipelineTemplate.id == run.template_id).one()
    doc = _parse_mini_template(tpl.template_yaml)
    tdef = next(x for x in doc["spec"]["tasks"] if x["name"] == task.name)

    project = db.query(Project).filter(Project.id == run.project_id).one()
    ensure_namespace(project.namespace)

    # Find model version from register task output
    reg_task = db.query(PipelineTask).filter(PipelineTask.run_id == run.id, PipelineTask.type == "register_model").first()
    if not reg_task or reg_task.status != "SUCCEEDED":
        return
    mv_id = reg_task.output.get("model_version_id")
    if not mv_id:
        return

    pool = _pool_by_name(db, tdef["pool"])
    name = f"deploy-{run.id[:8]}"

    # Allocate pool capacity for deployment
    try:
        acquire_allocation(db, run.tenant_id, pool.id, "deployment", name, units=1)
    except CapacityError as e:
        log.info("deployment allocation blocked", extra={"run_id": run.id, "error": str(e)})
        return

    dep_name, svc_name = create_serving_deployment(
        namespace=project.namespace,
        name=name,
        image=tdef["serving_image"],
        env={
            "S3_ENDPOINT": "http://minio.modelops-system.svc.cluster.local:9000",
            "S3_ACCESS_KEY": "minio",
            "S3_SECRET_KEY": "minio12345",
            "S3_BUCKET": "artifacts",
            "S3_MODEL_URI": _artifact_key_from_model_version(db, mv_id),
        },
        node_selector=pool.node_selector,
        tolerations=pool.tolerations,
        gpu_resource_name=pool.gpu_resource_name,
        gpu_units=1,
    )

    d = Deployment(
        tenant_id=run.tenant_id,
        project_id=run.project_id,
        model_version_id=mv_id,
        name=name,
        gpu_pool_id=pool.id,
        k8s_deployment=dep_name,
        k8s_service=svc_name,
        status="READY",
    )
    db.add(d)

    task.status = "SUCCEEDED"
    task.output = {"deployment_id": d.id, "service": svc_name}
    task.finished_at = _now()
    db.add(task)
    db.commit()


def _artifact_key_from_model_version(db: Session, model_version_id: str) -> str:
    mv = db.query(ModelVersion).filter(ModelVersion.id == model_version_id).one()
    # s3://bucket/key
    return mv.artifact_uri.split("/", 3)[-1] if mv.artifact_uri.startswith("s3://") else mv.artifact_uri
