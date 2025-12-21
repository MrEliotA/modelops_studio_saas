from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jwt

from .config import settings


@dataclass(frozen=True)
class Actor:
    tenant_id: str
    user_id: str
    role: str  # admin | member


def issue_token(actor: Actor) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + settings.jwt_ttl_seconds,
        "sub": actor.user_id,
        "tenant_id": actor.tenant_id,
        "role": actor.role,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_token(token: str) -> Actor:
    p = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    return Actor(tenant_id=str(p["tenant_id"]), user_id=str(p["sub"]), role=str(p.get("role", "member")))
