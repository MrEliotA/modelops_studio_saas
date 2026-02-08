from __future__ import annotations
import logging
import os
import structlog
from opentelemetry import trace
from .context import tenant_id_var, project_id_var, user_id_var, request_id_var, idempotency_key_var

def _add_trace_ids(_, __, event_dict):
    span = trace.get_current_span()
    ctx = span.get_span_context() if span is not None else None
    if ctx and ctx.is_valid:
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
    return event_dict

def configure_logging(service_name: str) -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(format="%(message)s", level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_trace_ids,
            structlog.processors.EventRenamer("event"),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service_name)

def bind_request_context():
    structlog.contextvars.bind_contextvars(
        tenant_id=str(tenant_id_var.get()) if tenant_id_var.get() else None,
        project_id=str(project_id_var.get()) if project_id_var.get() else None,
        user_id=user_id_var.get(),
        request_id=request_id_var.get(),
        idempotency_key=idempotency_key_var.get(),
    )

def clear_request_context():
    structlog.contextvars.clear_contextvars()
