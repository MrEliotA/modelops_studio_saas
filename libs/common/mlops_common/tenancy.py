from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from starlette.requests import Request

from .context import Tenancy as TenancyCtx
from .context import project_id_var, request_id_var, tenant_id_var, user_id_var


@dataclass(frozen=True)
class Tenancy:
    tenant_id: UUID
    project_id: UUID
    user_id: str
    request_id: str


def _first_header(headers, *names: str) -> str:
    for name in names:
        v = headers.get(name)
        if v:
            return v
    return ""


def extract_tenancy(request: Request) -> Tenancy:
    headers = request.headers

    tenant_id_raw = headers.get("X-Tenant-Id")
    project_id_raw = headers.get("X-Project-Id")

    # Support both our internal header and oauth2-proxy / nginx auth_request headers.
    user_id = _first_header(
        headers,
        "X-User-Id",
        "X-Auth-Request-User",
        "X-Auth-Request-Preferred-Username",
        "X-Forwarded-User",
    )

    request_id = headers.get("X-Request-Id") or str(uuid4())

    if not tenant_id_raw or not project_id_raw or not user_id:
        raise ValueError(
            "Missing tenancy headers: X-Tenant-Id, X-Project-Id, X-User-Id (or X-Auth-Request-User)"
        )

    tenant_id = UUID(tenant_id_raw)
    project_id = UUID(project_id_raw)

    tenant_id_var.set(tenant_id)
    project_id_var.set(project_id)
    user_id_var.set(user_id)
    request_id_var.set(request_id)

    return Tenancy(tenant_id=tenant_id, project_id=project_id, user_id=user_id, request_id=request_id)
