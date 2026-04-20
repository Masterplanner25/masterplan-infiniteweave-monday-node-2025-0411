import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from AINDY.config import settings
from AINDY.core.system_event_service import emit_system_event
from AINDY.db.database import SessionLocal
from AINDY.platform_layer.rate_limiter import limiter

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)


def _testing_health_payload() -> dict:
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.VERSION,
        "dependencies": {},
    }


def _emit_health_event(payload: dict) -> None:
    event_db = SessionLocal()
    try:
        emit_system_event(
            db=event_db,
            event_type="health.liveness.completed",
            payload=payload,
            required=False,
        )
    finally:
        event_db.close()


def liveness() -> dict:
    payload = _testing_health_payload()
    _emit_health_event(payload)
    return payload


def liveness_legacy_alias() -> dict:
    payload = _testing_health_payload()
    _emit_health_event(payload)
    return payload


def _build_health_response(*, force: bool) -> JSONResponse:
    if settings.is_testing:
        payload = _testing_health_payload()
        _emit_health_event(payload)
        return JSONResponse(status_code=200, content=payload)

    from AINDY.platform_layer.health_service import get_system_health

    health = get_system_health(force=force)
    payload = health.to_dict()
    _emit_health_event(payload)
    return JSONResponse(status_code=health.http_status, content=payload)


@router.get("/health", summary="Check Health")
@limiter.limit("120/minute")
async def health_check(request: Request):
    return _build_health_response(force=False)


@router.get("/health/", summary="Check Health (Legacy Alias)")
@limiter.limit("120/minute")
async def health_check_legacy(request: Request):
    return _build_health_response(force=False)


@router.get("/health/detail", summary="Check Detailed Health")
@limiter.limit("60/minute")
async def health_check_detail(request: Request):
    return _build_health_response(force=True)


@router.get("/health/details", summary="Check Detailed Health (Legacy Alias)")
@limiter.limit("60/minute")
async def health_check_details_legacy(request: Request):
    return _build_health_response(force=True)


@router.get("/ready", summary="Check Readiness")
@limiter.limit("120/minute")
def readiness(request: Request) -> dict:
    return {
        "status": "ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
