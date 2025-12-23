#!/usr/bin/env python3
from __future__ import annotations

import argparse
import requests


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    args = ap.parse_args()
    api = args.api.rstrip("/")

    login = requests.post(f"{api}/v1/auth/login", json={"tenant_id": "admin", "user_id": "admin", "role": "admin"})
    login.raise_for_status()
    token = login.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # GPU pools (A30 MIG, T4 time-slice)
    pools = [
        {
            "name": "gpu-pro-mig",
            "gpu_model": "A30",
            "mode": "MIG",
            "node_selector": {"atomicmail.ai/gpu-pool": "gpu-pro-mig"},
            "tolerations": [{"key": "atomicmail.ai/gpu-pro", "operator": "Equal", "value": "true", "effect": "NoSchedule"}],
            "gpu_resource_name": "nvidia.com/mig-1g.6gb",
            "capacity_shares": 2,
            "timeslice_replicas": None,
        },
        {
            "name": "gpu-econ-timeslice",
            "gpu_model": "T4",
            "mode": "TIME_SLICE",
            "node_selector": {"atomicmail.ai/gpu-pool": "gpu-econ-timeslice"},
            "tolerations": [{"key": "atomicmail.ai/gpu-econ", "operator": "Equal", "value": "true", "effect": "NoSchedule"}],
            "gpu_resource_name": "nvidia.com/gpu",
            "capacity_shares": 4,
            "timeslice_replicas": 4,
        },
    ]
    for p in pools:
        requests.post(f"{api}/v1/admin/gpu/pools", headers=h, json=p).raise_for_status()

    plans = [
        {
            "name": "Economy",
            "description": "Best-effort time-sliced pool for light workloads.",
            "sla": {"job_start_p95_minutes": 60, "availability_percent": 99.0, "support": "8x5", "max_job_minutes": 30},
            "pricing": {"gpu_share_minute": 0.01, "endpoint_request": 0.00001},
        },
        {
            "name": "Pro",
            "description": "MIG-backed pool for B2B production workloads.",
            "sla": {"job_start_p95_minutes": 10, "availability_percent": 99.5, "support": "12x5"},
            "pricing": {"gpu_slice_minute": 0.05, "endpoint_request": 0.00002},
        },
    ]
    for p in plans:
        requests.post(f"{api}/v1/admin/plans", headers=h, json=p).raise_for_status()

    # Mini pipeline template
    templates = [
        {
            "tenant_id": "admin",
            "name": "digits-train-register-deploy",
            "version": "1.0.0",
            "description": "Train a digits classifier, register, deploy serving.",
            "tags": ["demo", "digits", "train", "deploy"],
            "template_yaml": open("deploy/templates/digits_train_register_deploy.yaml", "r", encoding="utf-8").read(),
        },
        {
            "tenant_id": "admin",
            "name": "kfp-xgboost-iris",
            "version": "1.0.0",
            "description": "Kubeflow pipeline template: XGBoost Iris classifier.",
            "tags": ["kubeflow", "kfp", "xgboost", "iris"],
            "template_yaml": open("deploy/templates/kfp_xgboost_iris.yaml", "r", encoding="utf-8").read(),
        },
        {
            "tenant_id": "admin",
            "name": "kfp-pytorch-mnist",
            "version": "1.0.0",
            "description": "Kubeflow pipeline template: PyTorch MNIST training.",
            "tags": ["kubeflow", "kfp", "pytorch", "mnist"],
            "template_yaml": open("deploy/templates/kfp_pytorch_mnist.yaml", "r", encoding="utf-8").read(),
        },
        {
            "tenant_id": "admin",
            "name": "kfp-tfx-taxi",
            "version": "1.0.0",
            "description": "Kubeflow pipeline template: TFX taxi example.",
            "tags": ["kubeflow", "kfp", "tfx", "taxi"],
            "template_yaml": open("deploy/templates/kfp_tfx_taxi.yaml", "r", encoding="utf-8").read(),
        },
    ]
    for tpl in templates:
        requests.post(f"{api}/v1/admin/templates", headers=h, json=tpl).raise_for_status()


if __name__ == "__main__":
    main()
