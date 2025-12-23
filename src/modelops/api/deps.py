from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from modelops.core.db import SessionLocal
from modelops.core.security import Actor, verify_token


def db_session() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def actor_from_header(authorization: str = Header(default="")) -> Actor:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        return verify_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


ActorDep = Annotated[Actor, Depends(actor_from_header)]


def require_admin(actor: ActorDep) -> Actor:
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return actor


DBSession = Annotated[Session, Depends(db_session)]
AdminActorDep = Annotated[Actor, Depends(require_admin)]
