import logging
import os
import uuid as _uuid
from asyncio import TimeoutError as AsyncTimeoutError
from asyncio import gather, to_thread, wait_for
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from AINDY.config import settings
from AINDY.core.execution_signal_helper import queue_system_event
from AINDY.core.system_event_service import emit_system_event
from AINDY.db.database import SessionLocal, get_pool_status
from AINDY.platform_layer.registry import get_degraded_domains
from AINDY.platform_layer.rate_limiter import limiter

router = APIRouter(tags=["Health"])
logger = logging.getLogger(__name__)
_INSTANCE_ID = str(_uuid.uuid4())


def _get_degraded_domains() -> list[str]:
    return get_degraded_domains()


def _testing_health_payload() -> dict:
    db_pool = get_pool_status()
    payload = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.VERSION,
        "degraded_domains": _get_degraded_domains(),
        "dependencies": {},
        "db_pool": db_pool,
    }
    warnings: list[str] = []
    if db_pool.get("checkedout", 0) > (db_pool.get("pool_size", 0) + (settings.DB_MAX_OVERFLOW * 0.8)):
        warnings.append("db_pool_near_exhaustion")
    if warnings:
        payload["warnings"] = warnings
    return payload


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
    db_pool = get_pool_status()
    payload["db_pool"] = db_pool
    if db_pool.get("checkedout", 0) > (db_pool.get("pool_size", 0) + (settings.DB_MAX_OVERFLOW * 0.8)):
        warnings = list(payload.get("warnings") or [])
        warnings.append("db_pool_near_exhaustion")
        payload["warnings"] = warnings
    _emit_health_event(payload)
    return JSONResponse(status_code=health.http_status, content=payload)


async def _run_deep_check(check_fn, *, timeout: float):
    try:
        return await wait_for(to_thread(check_fn), timeout=timeout)
    except AsyncTimeoutError:
        return {"status": "error", "detail": f"Timed out after {timeout:.1f}s"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _check_database_status() -> dict:
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
    finally:
        db.close()


def _check_redis_status() -> dict:
    if not settings.REDIS_URL:
        return {"status": "not_configured"}

    from AINDY.platform_layer.health_service import check_redis_available

    try:
        return {"status": "ok" if check_redis_available(use_cache=False) else "unavailable"}
    except Exception as exc:
        return {"status": "unavailable", "detail": str(exc)}


def _check_mongo_status() -> dict:
    if not settings.MONGO_URL:
        return {"status": "not_configured"}

    from AINDY.db.mongo_setup import ensure_mongo_ready

    try:
        ensure_mongo_ready()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "unavailable", "detail": str(exc)}


def _check_scheduler_status() -> dict:
    background_enabled = os.getenv("AINDY_ENABLE_BACKGROUND_TASKS", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    if not background_enabled:
        return {"status": "disabled"}

    from AINDY.platform_layer import scheduler_service

    try:
        scheduler = scheduler_service.get_scheduler()
    except Exception as exc:
        return {"status": "not_running", "detail": str(exc)}

    if getattr(scheduler, "running", False):
        return {"status": "ok"}
    return {"status": "not_running", "detail": "Scheduler is initialized but not running"}


def _check_flow_registry_status() -> dict:
    from AINDY.runtime.flow_engine import FLOW_REGISTRY, NODE_REGISTRY

    node_count = len(NODE_REGISTRY)
    flow_count = len(FLOW_REGISTRY)
    return {
        "status": "ok" if node_count > 0 and flow_count > 0 else "empty",
        "node_count": node_count,
        "flow_count": flow_count,
    }


def _check_worker_health() -> dict:
    if settings.EXECUTION_MODE != "distributed":
        return {"status": "not_applicable", "detail": "EXECUTION_MODE=thread"}
    if not settings.REDIS_URL:
        return {"status": "error", "detail": "EXECUTION_MODE=distributed but REDIS_URL not set"}
    try:
        import redis as _redis

        client = _redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        val = client.get("aindy:worker:heartbeat")
        if val is None:
            return {
                "status": "no_heartbeat",
                "detail": "No worker heartbeat in Redis — worker may not be running",
            }
        return {"status": "ok", "detail": f"last_beat={val.decode()}"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _check_nodus_status() -> dict:
    nodus_path = os.environ.get("NODUS_SOURCE_PATH")
    if not nodus_path:
        return {"status": "not_configured", "detail": "NODUS_SOURCE_PATH not set"}

    import sys as _sys

    if nodus_path not in _sys.path:
        _sys.path.insert(0, nodus_path)
    try:
        import importlib

        importlib.import_module("nodus.runtime.embedding")
        return {"status": "ok", "path": nodus_path}
    except ImportError as exc:
        return {"status": "unavailable", "detail": str(exc), "path": nodus_path}


def _check_ai_providers_status() -> dict:
    from AINDY.kernel.circuit_breaker import (
        CircuitState,
        get_deepseek_circuit_breaker,
        get_openai_circuit_breaker,
    )

    def _summarize(cb) -> dict:
        state = cb.state
        result = {
            "circuit": state.value,
            "failure_count": cb.failure_count,
        }
        if state != CircuitState.CLOSED:
            opened = cb.opened_at
            result["opened_at"] = opened.isoformat() if opened else None
        return result

    openai_status = _summarize(get_openai_circuit_breaker())
    deepseek_status = _summarize(get_deepseek_circuit_breaker())
    any_open = any(
        status["circuit"] == "open"
        for status in (openai_status, deepseek_status)
    )
    aggregate = "degraded" if any_open else "ok"
    return {
        "status": aggregate,
        "openai": openai_status,
        "deepseek": deepseek_status,
    }


@router.post("/client/error", status_code=204)
@limiter.limit("30/minute")
async def report_client_error(
    request: Request,
    payload: dict = Body(default={}),
):
    """
    Receive a frontend error report and write it as a SystemEvent.
    Returns 204 (no content) - the client does not need a response body.
    Authentication is optional: unauthenticated reports are accepted so
    errors during login/boot can be captured.
    """
    db = SessionLocal()
    try:
        queue_system_event(
            db=db,
            event_type="client.error.reported",
            user_id=payload.get("user_id"),
            trace_id=payload.get("trace_id") or str(_uuid.uuid4()),
            source="frontend",
            payload={
                "error_message": str(payload.get("error_message") or "")[:1000],
                "component_stack": str(payload.get("component_stack") or "")[:3000],
                "route": str(payload.get("route") or "")[:200],
                "user_agent": str(payload.get("user_agent") or "")[:300],
                "error_type": str(payload.get("error_type") or "boundary"),
            },
            required=False,
        )
    except Exception:
        pass
    finally:
        db.close()


@router.post("/client/vitals", status_code=204)
@limiter.limit("30/minute")
async def report_client_vitals(
    request: Request,
    payload: dict = Body(default={}),
):
    """
    Receive Web Vitals measurements from the frontend.
    Returns 204 - no response body needed.
    """
    db = SessionLocal()
    try:
        queue_system_event(
            db=db,
            event_type="client.vitals.reported",
            user_id=payload.get("user_id"),
            trace_id=payload.get("session_id") or str(_uuid.uuid4()),
            source="frontend",
            payload={
                "lcp_ms": payload.get("lcp_ms"),
                "cls_score": payload.get("cls_score"),
                "inp_ms": payload.get("inp_ms"),
                "route": str(payload.get("route") or "")[:200],
            },
            required=False,
        )
    except Exception:
        pass
    finally:
        db.close()


async def _build_deep_health_payload() -> dict:
    database, redis, mongo, scheduler, flow_registry, worker, nodus, ai_providers = await gather(
        _run_deep_check(_check_database_status, timeout=0.5),
        _run_deep_check(_check_redis_status, timeout=1.0),
        _run_deep_check(_check_mongo_status, timeout=1.0),
        _run_deep_check(_check_scheduler_status, timeout=0.5),
        _run_deep_check(_check_flow_registry_status, timeout=0.5),
        _run_deep_check(_check_worker_health, timeout=1.0),
        _run_deep_check(_check_nodus_status, timeout=1.0),
        _run_deep_check(_check_ai_providers_status, timeout=0.5),
    )

    checks = {
        "database": database,
        "redis": redis if redis.get("status") != "error" else {"status": "unavailable", "detail": redis.get("detail")},
        "mongo": mongo if mongo.get("status") != "error" else {"status": "unavailable", "detail": mongo.get("detail")},
        "scheduler": scheduler if scheduler.get("status") != "error" else {"status": "not_running", "detail": scheduler.get("detail")},
        "flow_registry": flow_registry if flow_registry.get("status") != "error" else {"status": "empty", "node_count": 0, "flow_count": 0},
        "worker": worker if worker.get("status") != "error" else {"status": "error", "detail": worker.get("detail")},
        "nodus": nodus if nodus.get("status") != "error" else {"status": "unavailable", "detail": nodus.get("detail")},
        "ai_providers": ai_providers if ai_providers.get("status") != "error" else {"status": "unavailable", "detail": ai_providers.get("detail")},
    }
    overall_status = "degraded" if any(
        check.get("status") not in {"ok", "not_configured", "not_applicable"} for check in checks.values()
    ) else "healthy"
    return {
        "status": overall_status,
        "instance_id": _INSTANCE_ID,
        "degraded_domains": _get_degraded_domains(),
        "checks": checks,
    }


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


@router.get("/health/deep", summary="Check Deep Health")
@limiter.limit("10/minute")
async def health_check_deep(request: Request):
    payload = await _build_deep_health_payload()
    return JSONResponse(status_code=200, content=payload)


@router.get("/ready", summary="Check Readiness")
@limiter.limit("120/minute")
def readiness(request: Request):
    from AINDY.platform_layer.health_service import get_readiness_report

    status_code, payload = get_readiness_report()
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/readiness", summary="Check Readiness (Kubernetes alias)")
@limiter.limit("120/minute")
def readiness_alias(request: Request):
    from AINDY.platform_layer.health_service import get_readiness_report

    status_code, payload = get_readiness_report()
    return JSONResponse(status_code=status_code, content=payload)
