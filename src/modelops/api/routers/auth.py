from __future__ import annotations

from fastapi import APIRouter
from modelops.core.security import Actor, issue_token
from modelops.api.schemas import LoginRequest, LoginResponse

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    # MVP-only authentication; swap to OIDC for production.
    token = issue_token(Actor(tenant_id=payload.tenant_id, user_id=payload.user_id, role=payload.role))
    return LoginResponse(access_token=token)
