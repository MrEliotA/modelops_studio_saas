from __future__ import annotations
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import structlog

log = structlog.get_logger("http")

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        status_code = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            dur_ms = (time.perf_counter() - start) * 1000.0
            log.info("request_completed", method=request.method, path=request.url.path, status=status_code, duration_ms=round(dur_ms, 2))
