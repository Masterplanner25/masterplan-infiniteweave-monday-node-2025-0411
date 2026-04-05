import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from core.execution_helper import execute_with_pipeline_sync
from core.system_event_service import emit_system_event
from db.database import SessionLocal, engine, get_db
from services.auth_service import verify_api_key

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)


def _execute_health(request: Request, route_name: str, handler, *, db: Session | None = None):
    metadata = {"source": "health_router"}
    if db is not None:
        metadata["db"] = db
    return execute_with_pipeline_sync(
        request=request,
        route_name=route_name,
        handler=handler,
        metadata=metadata,
    )


def _liveness_payload() -> dict:
    return {
        "status": "ok",
        "service": "aindy-api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {"api": "alive"},
    }


def _compute_liveness() -> dict:
    """
    Liveness + shallow DB check.

    Always returns HTTP 200. 'status' is 'ok' when the DB is reachable,
    'degraded' when the DB check fails or times out (2 s ceiling).
    HTTP 503 is never returned by this endpoint — a degraded service can
    still respond, which is all liveness probes require.
    """
    db_status = "error"
    _done = threading.Event()

    def _check_db() -> None:
        nonlocal db_status
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as exc:
            logger.warning("[health] DB check failed: %s", exc)
        finally:
            db.close()
            _done.set()

    t = threading.Thread(target=_check_db, daemon=True)
    t.start()
    timed_out = not _done.wait(timeout=2.0)
    if timed_out:
        logger.warning("[health] DB check did not complete within 2 s")

    overall = "ok" if db_status == "ok" else "degraded"
    return {
        "status": overall,
        "db": db_status,
        "version": settings.VERSION,
    }


def liveness() -> dict:
    payload = {"status": "ok"}
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
    return payload


@router.get(
    "/health",
    summary="Check Liveness",
    description="Performs a liveness check with a shallow database probe. Returns the current service status and database reachability.",
)
def liveness_http(request: Request) -> dict:
    payload = _compute_liveness()
    def handler(_ctx):
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
        return payload

    return _execute_health(request, "health.liveness", handler)


def liveness_legacy_alias() -> dict:
    payload = _liveness_payload()
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
    return payload


@router.get(
    "/health/",
    summary="Check Legacy Liveness",
    description="Provides the legacy slash-suffixed liveness endpoint. Returns the basic health payload used by older callers.",
)
def liveness_legacy_alias_http(request: Request) -> dict:
    payload = _liveness_payload()
    def handler(_ctx):
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
        return payload
    return _execute_health(request, "health.liveness.legacy", handler)


@router.get(
    "/ready",
    summary="Check Readiness",
    description="Runs readiness checks for required infrastructure such as the database and cache. Returns the readiness status and component results.",
)
def readiness(request: Request, db: Session = Depends(get_db)) -> dict:
    components: dict[str, str] = {}

    try:
        db.execute(text("SELECT 1"))
        components["database"] = "ready"
    except Exception as exc:
        logger.warning("Readiness database check failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "readiness_failed",
                "message": "Database not ready",
                "components": {"database": "failed"},
            },
        ) from exc

    cache_backend = settings.AINDY_CACHE_BACKEND.lower()
    if cache_backend == "redis":
        try:
            import redis

            if not settings.REDIS_URL:
                raise RuntimeError("REDIS_URL is required for redis readiness checks")
            redis.from_url(settings.REDIS_URL).ping()
            components["redis"] = "ready"
        except Exception as exc:
            logger.warning("Readiness redis check failed: %s", exc)
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "readiness_failed",
                    "message": "Redis not ready",
                    "components": {
                        "database": components["database"],
                        "redis": "failed",
                    },
                },
            ) from exc
    else:
        components["cache"] = f"{cache_backend}:not_required"

    payload = {
        "status": "ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }
    def handler(_ctx):
        emit_system_event(
            db=db,
            event_type="health.readiness.completed",
            payload=payload,
            required=False,
        )
        return payload
    return _execute_health(request, "health.readiness", handler, db=db)


@router.get(
    "/health/details",
    dependencies=[Depends(verify_api_key)],
    summary="Get Health Details",
    description="Runs detailed health diagnostics for the API, database, and supporting components. Returns a component-by-component health report.",
)
def health_details(request: Request, db: Session = Depends(get_db)) -> dict:
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "A.I.N.D.Y. v1.0.0",
        "components": {},
        "status": "healthy",
    }

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        status["components"]["database"] = "connected"
    except Exception as exc:
        status["components"]["database"] = f"error: {exc}"
        status["status"] = "degraded"

    try:
        import nltk

        nltk.data.find("tokenizers/punkt")
        nltk.data.find("tokenizers/punkt_tab")
        status["components"]["nltk"] = "available"
    except LookupError:
        status["components"]["nltk"] = "missing"
        status["status"] = "degraded"
    except Exception as exc:
        status["components"]["nltk"] = f"error: {exc}"
        status["status"] = "degraded"

    try:
        from memory import memory_persistence
        status["components"]["memory_bridge"] = (
            "ready" if hasattr(memory_persistence, "MemoryNodeDAO") else "not_loaded"
        )
    except Exception as exc:
        status["components"]["memory_bridge"] = f"error: {exc}"
        status["status"] = "degraded"

    def handler(_ctx):
        return status
    return _execute_health(request, "health.details", handler, db=db)
