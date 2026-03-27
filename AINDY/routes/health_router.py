import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from db.database import SessionLocal, engine, get_db
from services.auth_service import verify_api_key
from services.system_event_service import emit_system_event

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)


def _liveness_payload() -> dict:
    return {
        "status": "ok",
        "service": "aindy-api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {"api": "alive"},
    }


@router.get("/health")
def liveness() -> dict:
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


@router.get("/health/")
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


@router.get("/ready")
def readiness(db: Session = Depends(get_db)) -> dict:
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
    emit_system_event(
        db=db,
        event_type="health.readiness.completed",
        payload=payload,
        required=False,
    )
    return payload


@router.get("/health/details", dependencies=[Depends(verify_api_key)])
def health_details(db: Session = Depends(get_db)) -> dict:
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
        from services import memory_persistence

        status["components"]["memory_bridge"] = (
            "ready" if hasattr(memory_persistence, "MemoryNodeDAO") else "not_loaded"
        )
    except Exception as exc:
        status["components"]["memory_bridge"] = f"error: {exc}"
        status["status"] = "degraded"

    return status
