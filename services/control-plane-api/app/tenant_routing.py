from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from mlops_common.errors import ApiError


@dataclass(frozen=True)
class TenantRoute:
    tenant_id: str
    project_id: Optional[str] = None


def _header_dict(scope_headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in scope_headers:
        try:
            out[k.decode("latin-1").lower()] = v.decode("latin-1")
        except Exception:
            continue
    return out


def _strip_port(host: str) -> str:
    host = host.strip()
    if ":" in host:
        return host.split(":", 1)[0]
    return host


def _extract_tenant_from_host(host: str, base_domain: str) -> Optional[str]:
    host = _strip_port(host.lower())
    base_domain = base_domain.strip().lower().strip(".")
    if not base_domain:
        return None
    if host == base_domain:
        return None
    if not host.endswith("." + base_domain):
        return None
    prefix = host[: -(len(base_domain) + 1)]
    if not prefix:
        return None
    # Support wildcard hostnames; take the left-most label.
    return prefix.split(".")[0]


def _extract_tenant_from_path(path: str, prefix: str) -> Tuple[Optional[str], str]:
    prefix = prefix.rstrip("/")
    if not prefix:
        return None, path
    if not path.startswith(prefix + "/"):
        return None, path
    rest = path[len(prefix) + 1 :]
    parts = [p for p in rest.split("/") if p]
    if not parts:
        return None, path
    tenant = parts[0]
    new_path = "/" + "/".join(parts[1:])
    if new_path == "/":
        # Keep root if user hits /t/<tenant>
        return tenant, "/"
    return tenant, new_path


def _load_tenant_map(path: Optional[str]) -> Dict[str, TenantRoute]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)
    out: Dict[str, TenantRoute] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            if not isinstance(k, str):
                continue
            if isinstance(v, dict):
                tenant_id = str(v.get("tenant_id") or "").strip()
                project_id = str(v.get("project_id") or "").strip() or None
                if tenant_id:
                    out[k] = TenantRoute(tenant_id=tenant_id, project_id=project_id)
            elif isinstance(v, str):
                # Legacy: map slug -> tenant_id
                out[k] = TenantRoute(tenant_id=v)
    return out


_SKIP_PATHS = {
    "/healthz",
    "/api/v1/healthz",
    "/metrics",
    "/docs",
    "/openapi.json",
}


class TenantRoutingMiddleware:
    """Resolve tenant context from host/path and inject X-Tenant-Id (+ default project).

    This middleware is meant to run ONLY on the trusted edge API (control-plane-api).

    Supported routing models:
      - subdomain:  <tenant>.<TENANT_BASE_DOMAIN>
      - path:       <TENANT_PATH_PREFIX>/<tenant>/...

    When a tenant slug is resolved, this middleware injects:
      - X-Tenant-Id: <tenant UUID>
      - X-Project-Id: <default project UUID> (only if request didn't already set one)

    The slug->UUID mapping comes from TENANT_MAP_FILE (mounted ConfigMap).
    """

    def __init__(self, app):
        self.app = app
        self.mode = os.getenv("TENANT_ROUTING_MODE", "auto").lower().strip()
        raw_base = os.getenv("TENANT_BASE_DOMAIN", "").strip()
        # Allow multiple base domains (comma-separated) for environments like:
        #   mlops.local,127.0.0.1.nip.io
        self.base_domains = [b.strip() for b in raw_base.split(",") if b.strip()]
        self.path_prefix = os.getenv("TENANT_PATH_PREFIX", "/t").strip() or "/t"
        self.tenant_map_file = os.getenv("TENANT_MAP_FILE", "").strip()
        self._tenant_map = _load_tenant_map(self.tenant_map_file)

    async def __call__(self, scope: dict, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or "/"
        if path in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers") or [])
        hdrs = _header_dict(headers)

        # Always strip /t/<tenant> prefix if present, even if headers are already set.
        tenant_slug_from_path, new_path = _extract_tenant_from_path(path, self.path_prefix)
        if new_path != path:
            scope["path"] = new_path
            scope["raw_path"] = new_path.encode("utf-8")

        tenant_slug: Optional[str] = None
        if self.mode in {"auto", "path"} and tenant_slug_from_path:
            tenant_slug = tenant_slug_from_path

        if self.mode in {"auto", "subdomain"} and not tenant_slug:
            host = hdrs.get("x-forwarded-host") or hdrs.get("host") or ""
            for base in self.base_domains:
                tenant_slug = _extract_tenant_from_host(host, base)
                if tenant_slug:
                    break

        # If caller already provides tenant headers (e.g., internal calls), keep them.
        if "x-tenant-id" in hdrs:
            await self.app(scope, receive, send)
            return

        if tenant_slug:
            route = self._tenant_map.get(tenant_slug)
            if not route:
                raise ApiError("NotFound", f"Unknown tenant: {tenant_slug}", 404)

            headers.append((b"x-tenant-id", route.tenant_id.encode("latin-1")))
            if "x-project-id" not in hdrs and route.project_id:
                headers.append((b"x-project-id", route.project_id.encode("latin-1")))
            scope["headers"] = headers

        await self.app(scope, receive, send)
