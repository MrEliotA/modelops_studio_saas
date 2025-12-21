from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from modelops.core.db import SessionLocal
from modelops.core.security import verify_token, Actor


def db_session():
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
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_admin(actor: Actor = Depends(actor_from_header)) -> Actor:
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return actor
