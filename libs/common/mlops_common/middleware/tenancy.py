from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..logging import bind_request_context, clear_request_context
from ..tenancy import extract_tenancy
from ..errors import ApiError

# By default we do NOT require tenant headers for health and metrics endpoints.
# Override via TENANCY_SKIP_PATHS (comma-separated). Supports wildcard suffix (e.g. "/internal/*").
_DEFAULT_SKIP_PATHS = (
    "/healthz",
    "/api/v1/healthz",
    "/metrics",
    "/docs",
    "/openapi.json",
)


def _parse_skip_paths(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return _DEFAULT_SKIP_PATHS
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return tuple(parts) if parts else _DEFAULT_SKIP_PATHS


_SKIP_PATHS = _parse_skip_paths(os.getenv("TENANCY_SKIP_PATHS"))


def _should_skip(path: str) -> bool:
    for rule in _SKIP_PATHS:
        if rule.endswith("*"):
            if path.startswith(rule[:-1]):
                return True
        elif path == rule:
            return True
    return False


class TenancyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _should_skip(request.url.path):
            return await call_next(request)

        try:
            tenancy = extract_tenancy(request)
        except ValueError as e:
            # Avoid leaking internal exceptions; return a clean 400 for missing tenancy.
            raise ApiError("BadRequest", str(e), 400) from e
        request.state.tenancy = tenancy
        request.state.request_id = tenancy.request_id

        bind_request_context()
        try:
            resp: Response = await call_next(request)
            resp.headers.setdefault("X-Request-Id", tenancy.request_id)
            return resp
        finally:
            clear_request_context()
