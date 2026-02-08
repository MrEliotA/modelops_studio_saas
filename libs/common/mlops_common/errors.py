from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
from fastapi import Request
from fastapi.responses import JSONResponse

@dataclass
class ApiError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: Optional[Dict[str, Any]] = None

def error_response(code: str, message: str, status_code: int = 400, details: Optional[Dict[str, Any]] = None, request_id: str | None = None):
    payload: Dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    if request_id:
        payload["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=payload)

async def api_error_handler(request: Request, exc: ApiError):
    rid = getattr(getattr(request, "state", None), "request_id", None)
    return error_response(exc.code, exc.message, exc.status_code, exc.details, rid)

async def unhandled_exception_handler(request: Request, exc: Exception):
    rid = getattr(getattr(request, "state", None), "request_id", None)
    return error_response("InternalError", "Unhandled exception", 500, {"type": type(exc).__name__}, rid)
