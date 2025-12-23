from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from modelops.domain.models import DashboardAsset


def seed_builtin_dashboards(db: Session, repo_root: str) -> None:
    dashboards = [
        ("admin", "Platform Overview", "Cross-tenant golden signals + top tenants by cost", "modelops_admin_platform_overview.json"),
        ("admin", "GPU Pool Capacity", "Allocator view of pool capacity/utilization/jobs", "modelops_admin_gpu_pool_capacity.json"),
        ("user", "Runtime Resources", "Deployment runtime saturation + CPU/mem views", "modelops_user_runtime_resources.json"),
    ]

    base = Path(repo_root) / "deploy" / "addons" / "observability" / "grafana" / "dashboards"

    for scope, name, desc, fn in dashboards:
        p = base / fn
        if not p.exists():
            continue
        payload = json.loads(p.read_text(encoding="utf-8"))
        exists = (
            db.query(DashboardAsset)
            .filter(DashboardAsset.scope == scope)
            .filter(DashboardAsset.name == name)
            .filter(DashboardAsset.tenant_id.is_(None))
            .first()
        )
        if exists:
            continue

        db.add(
            DashboardAsset(
                scope=scope,
                name=name,
                description=desc,
                tags=["modelops", scope],
                dashboard_json=payload,
                tenant_id=None,
            )
        )
    db.commit()
