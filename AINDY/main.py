import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

import AINDY.startup as _startup
from AINDY.config import settings
from AINDY.db.database import SessionLocal
from AINDY.exception_handlers import _extract_user_id_from_request, queue_saturated_exception_handler, register_exception_handlers
from AINDY.middleware import (
    _AINDY_SERVICE_KEY,
    _is_metrics_ip_allowed,
    _request_id_ctx,
    RequestContextFilter,
    log_requests,
    register_middleware,
)
from AINDY.routing import register_routes
from AINDY.startup import init_mongo

FastAPICache = _startup.FastAPICache
ensure_mongo_ready = _startup.ensure_mongo_ready
ping_mongo = _startup.ping_mongo
validate_queue_backend = _startup.validate_queue_backend
emit_event = _startup.emit_event
_check_worker_presence = _startup._check_worker_presence
_check_nodus_importable = _startup._check_nodus_importable
_STARTUP_SYNC_NAMES = ("settings", "FastAPICache", "ensure_mongo_ready", "ping_mongo", "validate_queue_backend", "emit_event", "_check_worker_presence", "_check_nodus_importable")


def _call_startup(function_name: str):
    _target = getattr(_startup, function_name)
    _saved = {name: getattr(_startup, name) for name in _STARTUP_SYNC_NAMES}
    try:
        for name in _STARTUP_SYNC_NAMES:
            setattr(_startup, name, getattr(sys.modules[__name__], name))
        return _target()
    finally:
        for name, value in _saved.items():
            setattr(_startup, name, value)


def _enforce_cache_backend_coherence(): return _call_startup("_enforce_cache_backend_coherence")
def _verify_required_syscalls_registered(): return _call_startup("_verify_required_syscalls_registered")
def _initialize_cache_backend(): return _call_startup("_initialize_cache_backend")
def _enforce_redis_startup_guard(): return _call_startup("_enforce_redis_startup_guard")
def _enforce_event_bus_startup_guard(): return _call_startup("_enforce_event_bus_startup_guard")
def _enforce_nodus_gate(): return _call_startup("_enforce_nodus_gate")

_DEFAULT_ENFORCE_REDIS_STARTUP_GUARD = _enforce_redis_startup_guard
_DEFAULT_ENFORCE_EVENT_BUS_STARTUP_GUARD = _enforce_event_bus_startup_guard


@asynccontextmanager
async def lifespan(app):
    _saved = {name: getattr(_startup, name) for name in _STARTUP_SYNC_NAMES}
    _helper_saves = {}
    try:
        for name in _STARTUP_SYNC_NAMES:
            setattr(_startup, name, getattr(sys.modules[__name__], name))
        if _enforce_redis_startup_guard is not _DEFAULT_ENFORCE_REDIS_STARTUP_GUARD:
            _helper_saves["_enforce_redis_startup_guard"] = _startup._enforce_redis_startup_guard
            _startup._enforce_redis_startup_guard = _enforce_redis_startup_guard
        if _enforce_event_bus_startup_guard is not _DEFAULT_ENFORCE_EVENT_BUS_STARTUP_GUARD:
            _helper_saves["_enforce_event_bus_startup_guard"] = _startup._enforce_event_bus_startup_guard
            _startup._enforce_event_bus_startup_guard = _enforce_event_bus_startup_guard
        async with _startup.lifespan(app) as state:
            yield state
    finally:
        for name, value in _saved.items():
            setattr(_startup, name, value)
        for name, value in _helper_saves.items():
            setattr(_startup, name, value)


def create_app() -> FastAPI:
    app = FastAPI(title="A.I.N.D.Y. Memory Bridge", lifespan=lifespan)
    register_middleware(app)
    register_routes(app)
    register_exception_handlers(app)
    return app

app = create_app()
