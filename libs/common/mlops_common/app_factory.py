from __future__ import annotations
from fastapi import FastAPI
from .logging import configure_logging
from .otel import setup_tracing
from .db import create_pool
from .errors import ApiError, api_error_handler, unhandled_exception_handler
from .middleware.tenancy import TenancyMiddleware
from .middleware.idempotency import IdempotencyMiddleware
from .middleware.request_logging import RequestLoggingMiddleware

async def _startup(app: FastAPI):
    app.state.db_pool = await create_pool()

async def _shutdown(app: FastAPI):
    pool = getattr(app.state, "db_pool", None)
    if pool:
        await pool.close()

def create_app(service_name: str, enable_idempotency: bool = True) -> FastAPI:
    """Create a FastAPI app wired with shared concerns.
    Middleware order:
      outermost (runs first) -> RequestLogging
      then -> Tenancy
      then -> Idempotency
    We add in reverse order (inner to outer).
    """
    configure_logging(service_name)
    app = FastAPI(title=service_name)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    if enable_idempotency:
        app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(TenancyMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    @app.on_event("startup")
    async def _on_startup():
        await _startup(app)
        setup_tracing(app, service_name)

    @app.on_event("shutdown")
    async def _on_shutdown():
        await _shutdown(app)

    return app
