import logging
import uuid

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from AINDY.core.distributed_queue import QueueSaturatedError
from AINDY.core.system_event_service import emit_error_event
from AINDY.db.database import SessionLocal
from AINDY.db.mongo_setup import MongoUnavailableError
from AINDY.kernel.circuit_breaker import CircuitOpenError

logger = logging.getLogger("AINDY.main")


async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    message = detail if isinstance(detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "message": message,
            "details": detail if not isinstance(detail, str) else None,
        },
    )


async def queue_saturated_exception_handler(request: Request, exc: QueueSaturatedError):
    return JSONResponse(
        status_code=exc.status_code,
        headers={"Retry-After": str(exc.retry_after_seconds)},
        content={"error": "queue_saturated", "message": str(exc)},
    )


async def mongo_unavailable_exception_handler(
    request: Request, exc: MongoUnavailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": "mongo_unavailable",
            "message": exc.detail,
            "hint": (
                "Set MONGO_URL and ensure MongoDB is reachable, "
                "or set SKIP_MONGO_PING=true only in non-production environments."
            ),
        },
    )


async def circuit_open_exception_handler(request: Request, exc: CircuitOpenError):
    logger.warning(
        "[CircuitBreaker] open circuit rejected request path=%s error=%s",
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=503,
        content={
            "error": "ai_provider_unavailable",
            "message": "An AI provider is temporarily unavailable. Please retry in a moment.",
            "detail": str(exc),
            "retryable": True,
        },
        headers={"Retry-After": "60"},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Invalid request",
            "details": jsonable_encoder(exc.errors()),
        },
    )


def _extract_user_id_from_request(request: Request):
    request_state = getattr(request, "state", None)
    state_user_id = getattr(request_state, "user_id", None)
    if state_user_id not in (None, ""):
        try:
            from AINDY.platform_layer.user_ids import require_user_id

            return require_user_id(state_user_id)
        except Exception:
            return None

    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        from AINDY.services.auth_service import decode_access_token

        payload = decode_access_token(token)
        if not payload or "sub" not in payload:
            return None
        return uuid.UUID(str(payload["sub"]))
    except Exception:
        return None


async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error: %s", exc)
    db = None
    try:
        db = SessionLocal()
        emit_error_event(
            db=db,
            error_type="unhandled_request",
            message=str(exc),
            user_id=_extract_user_id_from_request(request),
            trace_id=getattr(getattr(request, "state", None), "trace_id", None),
            payload={"path": request.url.path, "method": request.method},
            required=True,
        )
    except Exception:
        logger.exception("Failed to emit required unhandled request error event")
    finally:
        if db is not None:
            db.close()
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Internal server error",
            "details": None,
        },
    )


def register_exception_handlers(app) -> None:
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(QueueSaturatedError, queue_saturated_exception_handler)
    app.add_exception_handler(MongoUnavailableError, mongo_unavailable_exception_handler)
    app.add_exception_handler(CircuitOpenError, circuit_open_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
