#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

import requests


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    args = ap.parse_args()
    api = args.api.rstrip("/")

    admin = requests.post(f"{api}/v1/auth/login", json={"tenant_id": "admin", "user_id": "admin", "role": "admin"})
    admin.raise_for_status()
    admin_token = admin.json()["access_token"]
    ah = {"Authorization": f"Bearer {admin_token}"}

    tenant = requests.post(f"{api}/v1/admin/tenants", headers=ah, json={"name": "acme"})
    tenant.raise_for_status()
    tenant_id = tenant.json()["id"]

    tlogin = requests.post(f"{api}/v1/auth/login", json={"tenant_id": tenant_id, "user_id": "alice", "role": "admin"})
    tlogin.raise_for_status()
    token = tlogin.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    proj = requests.post(f"{api}/v1/projects", headers=h, json={"tenant_id": tenant_id, "name": "demo"})
    proj.raise_for_status()
    project_id = proj.json()["id"]

    pools = requests.get(f"{api}/v1/admin/gpu/pools", headers=ah).json()
    pro_pool = next(p for p in pools if p["name"] == "gpu-pro-mig")
    eco_pool = next(p for p in pools if p["name"] == "gpu-econ-timeslice")

    plans = requests.get(f"{api}/v1/admin/plans", headers=ah).json()
    pro_plan = next(p for p in plans if p["name"] == "Pro")
    eco_plan = next(p for p in plans if p["name"] == "Economy")

    requests.post(
        f"{api}/v1/admin/tenants/{tenant_id}/plans",
        headers=ah,
        json={"plan_id": pro_plan["id"], "gpu_pool_id": pro_pool["id"], "quota_concurrency": 1},
    ).raise_for_status()
    requests.post(
        f"{api}/v1/admin/tenants/{tenant_id}/plans",
        headers=ah,
        json={"plan_id": eco_plan["id"], "gpu_pool_id": eco_pool["id"], "quota_concurrency": 1},
    ).raise_for_status()

    templates = requests.get(f"{api}/v1/templates", headers=ah, params={"tenant_id": "admin"}).json()
    tpl = templates[0]

    run = requests.post(
        f"{api}/v1/pipelines/runs",
        headers=h,
        json={"tenant_id": tenant_id, "project_id": project_id, "template_id": tpl["id"], "parameters": {}},
    )
    run.raise_for_status()
    run_id = run.json()["id"]
    print("Run:", run_id)

    while True:
        r = requests.get(f"{api}/v1/pipelines/runs/{run_id}", headers=h)
        r.raise_for_status()
        status = r.json()["status"]
        print("Status:", status)
        if status in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(3)

    if status != "SUCCEEDED":
        raise SystemExit("Pipeline failed")

    deps = requests.get(f"{api}/v1/deployments", headers=h, params={"tenant_id": tenant_id}).json()
    dep_id = deps[0]["id"]

    x = {"instances": [[0.0] * 64]}
    pred = requests.post(f"{api}/v1/deployments/{dep_id}/predict", headers=h, json=x)
    pred.raise_for_status()
    print("Predict:", pred.json())

    exp = requests.post(f"{api}/v1/deployments/{dep_id}/explain", headers=h, json=x)
    exp.raise_for_status()
    print("Explain:", exp.json())

    # Show monitoring summary
    mon = requests.get(f"{api}/v1/monitoring/summary", headers=h, params={"tenant_id": tenant_id})
    mon.raise_for_status()
    print("Monitoring summary:", mon.json())

    # Show usage ledger
    now = int(time.time())
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3600))
    end = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 3600))
    ledger = requests.get(f"{api}/v1/usage/ledger", headers=h, params={"tenant_id": tenant_id, "start": start, "end": end})
    ledger.raise_for_status()
    print("Ledger:", ledger.json())


if __name__ == "__main__":
    main()
