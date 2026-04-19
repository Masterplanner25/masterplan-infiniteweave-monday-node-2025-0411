from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.responses import Response

from AINDY.config import settings

logger = logging.getLogger(__name__)

_EXEMPT_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/ready",
)


def is_execution_exempt_path(path: str) -> bool:
    normalized = path or "/"
    return normalized == "/" or normalized.startswith(_EXEMPT_PREFIXES)


def require_execution_context(request: Request) -> None:
    if is_execution_exempt_path(request.url.path):
        return
    request.state.execution_contract_required = True
    if hasattr(request.state, "execution_context"):
        return


def validate_execution_contract(request: Request, response: Response | None = None) -> None:
    if is_execution_exempt_path(request.url.path):
        return
    if not getattr(request.state, "execution_contract_required", False):
        return
    if hasattr(request.state, "execution_context"):
        return
    if response is not None and int(getattr(response, "status_code", 200)) >= 400:
        return
    message = "ExecutionContract violation: route bypassed execution pipeline"
    if settings.ENFORCE_EXECUTION_CONTRACT:
        raise RuntimeError(message)
    logger.warning(message, extra={"path": request.url.path})
