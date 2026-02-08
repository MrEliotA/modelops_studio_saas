from __future__ import annotations
import contextvars
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

tenant_id_var: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar("tenant_id", default=None)
project_id_var: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar("project_id", default=None)
user_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("user_id", default=None)
request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
idempotency_key_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("idempotency_key", default=None)

@dataclass(frozen=True)
class Tenancy:
    tenant_id: UUID
    project_id: UUID
    user_id: str
    request_id: str
