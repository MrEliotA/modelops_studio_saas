from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List

from fastapi import HTTPException, Request

try:
    import jwt  # PyJWT
except Exception:  # pragma: no cover
    jwt = None


@dataclass
class Principal:
    user_id: str
    roles: List[str]


def _first_header(request: Request, *names: str) -> str:
    for name in names:
        v = request.headers.get(name)
        if v:
            return v
    return ""


def _parse_roles(raw: str | None) -> List[str]:
    if not raw:
        return []
    parts = re.split(r"[,\s]+", raw.strip())
    return [p for p in (r.strip() for r in parts) if p]


async def get_principal(request: Request) -> Principal:
    """Auth is intentionally lightweight because SSO/Gateway is out-of-scope.

    Modes:
      - AUTH_MODE=passthrough (default):
          Trust identity headers set by a trusted edge (demo: tenant-router, prod: gateway/edge auth).
      - AUTH_MODE=dev-jwt:
          Validate a HS256 JWT (for local/kind demos) and read roles from a claim.
    """
    mode = os.getenv("AUTH_MODE", "passthrough").lower()

    # Support both the platform headers and oauth2-proxy's standard auth_request headers.
    user_id = _first_header(
        request,
        "X-User-Id",
        "X-Auth-Request-User",
        "X-Auth-Request-Preferred-Username",
        "X-Forwarded-User",
    )

    roles_raw = _first_header(
        request,
        "X-Roles",
        "X-User-Roles",
        "X-Auth-Request-Groups",
        "X-Forwarded-Groups",
    )
    roles = _parse_roles(roles_raw)

    if mode == "dev-jwt":
        if jwt is None:
            raise HTTPException(
                status_code=500,
                detail="PyJWT not installed (pip install -r services/control-plane-api/requirements.txt)",
            )
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = auth.split(" ", 1)[1].strip()
        secret = os.getenv("JWT_SECRET", "dev-secret")
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

        user_id = user_id or str(payload.get("sub") or payload.get("user_id") or "")
        roles = roles or list(payload.get("roles") or [])
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing 'sub'")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Missing identity header (X-User-Id / X-Auth-Request-User)",
        )

    return Principal(user_id=user_id, roles=roles)
