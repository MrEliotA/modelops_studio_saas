from __future__ import annotations

from fastapi import HTTPException
from .auth import Principal

# RBAC uses (domain:action) where action is read|write|use.
ROLE_PERMS = {
    "admin": {"*:*"},
    "editor": {
        "templates:write",
        "runs:write",
        "training:write",
        "registry:write",
        "deployments:write",
        "endpoints:write",
        "artifacts:write",
        "gpu-jobs:write",
        "metering:read",
        "llm:use",
        "overview:read",
    },
    "viewer": {
        "templates:read",
        "runs:read",
        "training:read",
        "registry:read",
        "deployments:read",
        "endpoints:read",
        "artifacts:read",
        "gpu-jobs:read",
        "metering:read",
        "overview:read",
    },
    "llm-user": {"llm:use", "overview:read"},
}

def _method_to_action(method: str) -> str:
    m = method.upper()
    if m in ("GET", "HEAD", "OPTIONS"):
        return "read"
    return "write"

def _allowed(principal: Principal, perm: str) -> bool:
    # perm is like "templates:read"
    domain = perm.split(":", 1)[0]
    for role in principal.roles:
        perms = ROLE_PERMS.get(role, set())
        if "*:*" in perms:
            return True
        if perm in perms:
            return True
        if f"{domain}:write" in perms and perm.endswith(":read"):
            return True
    return False

async def require(principal: Principal, domain: str, method: str) -> None:
    # Special case for LLM calls.
    if domain == "llm":
        perm = "llm:use"
    else:
        perm = f"{domain}:{_method_to_action(method)}"
    if _allowed(principal, perm):
        return
    raise HTTPException(status_code=403, detail=f"Forbidden: missing permission {perm}")
