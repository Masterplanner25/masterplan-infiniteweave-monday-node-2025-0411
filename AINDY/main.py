import json
import logging
import os
import sys
import time
import uuid
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from platform_layer.rate_limiter import limiter
from platform_layer import scheduler_service
from domain import task_services
from core.observability_events import emit_observability_event
from core.system_event_service import emit_error_event
from db.database import SessionLocal
from db.mongo_setup import init_mongo
from core.execution_guard import require_execution_context, validate_execution_contract
from routes import ROOT_ROUTERS, PLATFORM_ROUTERS, APP_ROUTERS, platform_router
from config import settings
from db.models.metrics_models import *
from db.models.request_metric import RequestMetric
from utils.trace_context import (
    _trace_id_ctx,
    reset_current_request,
    reset_current_trace_id,
    set_current_request,
    set_current_trace_id,
)

# --- Ensure root path is importable ---
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def _import_installed_alembic():
    """
    Import the site-packages Alembic package even though this repo also has
    /app/alembic for migration scripts, which otherwise shadows the package.
    """
    app_dir = os.path.abspath(os.path.dirname(__file__))
    removed: list[tuple[int, str]] = []
    for index in range(len(sys.path) - 1, -1, -1):
        path = sys.path[index]
        normalized = os.path.abspath(path or os.getcwd())
        if normalized in {app_dir, ROOT_DIR}:
            removed.append((index, path))
            sys.path.pop(index)
    try:
        from alembic.config import Config  # type: ignore
        from alembic.script import ScriptDirectory  # type: ignore
        from alembic.runtime.migration import MigrationContext  # type: ignore
        return Config, ScriptDirectory, MigrationContext
    except Exception:
        return None, None, None
    finally:
        for index, path in sorted(removed, key=lambda item: item[0]):
            sys.path.insert(index, path)


Config, ScriptDirectory, MigrationContext = _import_installed_alembic()


# For in-memory caching
# If you want to use Redis (uncomment and configure):
# from fastapi_cache.backends.redis import RedisBackend
# from redis import asyncio as aioredis


# ── Request-scoped logging context ──────────────────────────────────────────
# Backward-compatible alias: older tests and code still reference _request_id_ctx.
_request_id_ctx = _trace_id_ctx


class RequestContextFilter(logging.Filter):
    """Inject request/trace IDs from ContextVar into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        trace_id = _trace_id_ctx.get()
        record.trace_id = trace_id
        record.request_id = trace_id
        return True


# config.py already called logging.basicConfig (FileHandler + StreamHandler).
# Upgrade all root-logger handlers in-place: attach the filter and apply the
# new format that includes [request_id].  No duplicate basicConfig call needed.
_REQUEST_LOG_FORMAT = "%(asctime)s - %(levelname)s - [trace=%(trace_id)s] - %(message)s"
_ctx_filter = RequestContextFilter()
for _handler in logging.root.handlers:
    _handler.addFilter(_ctx_filter)
    _handler.setFormatter(logging.Formatter(_REQUEST_LOG_FORMAT))

logger = logging.getLogger(__name__)


def _check_alembic_head() -> None:
    """Warn at startup if DB schema is behind the latest Alembic migration."""
    try:
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "check"],
            capture_output=True, text=True,
            cwd=os.path.dirname(__file__),
        )
        if result.returncode != 0:
            logger.warning(
                "[startup] Alembic schema is not at head — run `alembic upgrade head`.\n%s",
                result.stdout or result.stderr,
            )
        else:
            logger.info("[startup] Alembic schema is at head.")
    except Exception as exc:
        logger.warning("[startup] Could not verify Alembic schema: %s", exc)

def _ensure_dev_api_key():
    try:
        from platform_layer.api_key_service import hash_key
        from db.models.api_key import PlatformAPIKey
        from db.models.user import User   # ✅ ADD THIS
        import uuid

        db = SessionLocal()
        try:
            raw_key = settings.AINDY_API_KEY
            if not raw_key:
                logger.warning("No AINDY_API_KEY set; skipping dev key bootstrap")
                return

            key_hash = hash_key(raw_key)

            existing = db.query(PlatformAPIKey).filter_by(key_hash=key_hash).first()
            if existing:
                logger.info("Dev API key already exists.")
                return

            # 🔥 ensure a valid user exists
            user = db.query(User).first()
            if not user:
                user = User(
                    id=uuid.uuid4(),
                    email="dev@aindy.local",
                    hashed_password="dev",
                    is_active=True,
                )
                db.add(user)
                db.commit()
                logger.info("Dev user created.")

            dev_key = PlatformAPIKey(
                key_hash=key_hash,
                key_prefix=raw_key[:12],
                name="dev-key",
                user_id=user.id,
                scopes=["platform.admin"],
                is_active=True,
            )

            db.add(dev_key)
            db.commit()
            logger.info("Dev API key created and registered.")

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"Dev API key bootstrap skipped (non-fatal): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    cache_backend = os.getenv("AINDY_CACHE_BACKEND", "memory").lower()
    if settings.is_testing or os.getenv("PYTEST_CURRENT_TEST"):
        cache_backend = "memory"
    if cache_backend == "redis":
        try:
            from redis import asyncio as aioredis
            from fastapi_cache.backends.redis import RedisBackend
        except Exception as exc:
            logger.error("Redis cache backend unavailable: %s", exc)
            raise RuntimeError("Redis cache backend unavailable.") from exc
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is required for redis cache backend.")
        redis = aioredis.from_url(settings.REDIS_URL, encoding="utf8", decode_responses=True)
        FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
        logger.info("Cache backend initialized: redis")
    else:
        FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
        logger.info("Cache backend initialized: memory")

    init_mongo()

    if settings.ENV == "dev":
        _ensure_dev_api_key()

    # SECRET_KEY guard — reject insecure placeholder in production
    _placeholder = "dev-secret-change-in-production"
    if settings.SECRET_KEY == _placeholder:
        if settings.is_prod:
            raise RuntimeError(
                "SECRET_KEY is using the insecure default placeholder. "
                "Set a strong SECRET_KEY in your .env before running in production."
            )
        else:
            logger.warning(
                "SECRET_KEY is using the insecure default placeholder. "
                "This is acceptable for local development but MUST be changed before production."
            )

    enforce_schema = os.getenv("AINDY_ENFORCE_SCHEMA", "true").lower() in {"1", "true", "yes"}
    if enforce_schema and not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        if not (Config and ScriptDirectory and MigrationContext):
            logger.error("Schema guard unavailable: alembic not installed.")
            raise RuntimeError("Schema guard unavailable: alembic not installed.")
        db = SessionLocal()
        try:
            conn = db.connection()
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

            alembic_cfg = Config("alembic.ini")
            script = ScriptDirectory.from_config(alembic_cfg)
            heads = script.get_heads()

            if not current_rev or (current_rev not in heads):
                logger.error(
                    "Schema drift detected. current=%s heads=%s",
                    current_rev,
                    heads,
                )
                raise RuntimeError("Schema drift detected. Run alembic upgrade head.")
        finally:
            db.close()

    enable_background = os.getenv("AINDY_ENABLE_BACKGROUND_TASKS", "true").lower() in {"1", "true", "yes"}
    if settings.is_testing or os.getenv("PYTEST_CURRENT_TEST"):
        enable_background = False

    # Acquire the inter-instance DB lease first; only the leader starts APScheduler.
    # start_background_tasks() returns True iff this instance holds the lease.
    is_leader = task_services.start_background_tasks(enable=enable_background, log=logger)
    if is_leader:
        scheduler_service.start()

    # Register domain syscall handlers (must come before flow registration)
    from kernel.syscall_handlers import register_all_domain_handlers
    register_all_domain_handlers()

    # Register Flow Engine flows and nodes (static startup definitions)
    from runtime.flow_definitions import register_all_flows
    register_all_flows()

    # Restore dynamic platform registrations (flows, nodes, webhook subs) from DB.
    # Runs after register_all_flows() so static nodes are available for flow validation.
    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        from platform_layer.platform_loader import load_dynamic_registry
        _loader_db = SessionLocal()
        try:
            _loader_stats = load_dynamic_registry(_loader_db)
            logger.info(
                "Dynamic registry restored: nodes=%d flows=%d webhooks=%d",
                _loader_stats.get("nodes_loaded", 0),
                _loader_stats.get("flows_loaded", 0),
                _loader_stats.get("webhooks_loaded", 0),
            )
        except Exception as _loader_exc:
            logger.warning("Dynamic registry restore failed (non-fatal): %s", _loader_exc)
        finally:
            _loader_db.close()

    # Enforce execution boundary: no router may import services directly
    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        from core.router_guard import RouterBoundaryViolation, validate_router_boundary
        try:
            validate_router_boundary()
        except RouterBoundaryViolation as _rbv:
            logger.error("EXECUTION BOUNDARY VIOLATED:\n%s", _rbv)
            raise RuntimeError(str(_rbv)) from _rbv

    # Sprint N+7: Recover any FlowRun/AgentRun rows stranded by prior crash
    if enable_background and not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        from agents.stuck_run_service import scan_and_recover_stuck_runs
        _scan_db = SessionLocal()
        try:
            scan_and_recover_stuck_runs(_scan_db)
        except Exception as _scan_exc:
            logger.warning("Stuck-run startup scan failed (non-fatal): %s", _scan_exc)
        finally:
            _scan_db.close()

    # Seed system identity
    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        from db.models.author_model import AuthorDB
        from datetime import datetime
        db = SessionLocal()
        try:
            system_id = "author-system"
            existing = db.query(AuthorDB).filter_by(id=system_id).first()
            if not existing:
                system_author = AuthorDB(
                    id=system_id,
                    name="A.I.N.D.Y. System",
                    platform="Internal Core",
                    notes="Autogenerated identity for runtime self-reference.",
                    joined_at=datetime.utcnow(),
                    last_seen=datetime.utcnow(),
                )
                db.add(system_author)
                db.commit()
                logger.info("Seeded system author: A.I.N.D.Y. System")
            else:
                existing.last_seen = datetime.utcnow()
                db.commit()
                logger.info("System author already present, timestamp refreshed.")
        except Exception as e:
            logger.warning(f"System identity seed failed (non-fatal): {e}")
        finally:
            db.close()

    # Warn if DB schema is behind the latest migration (non-fatal)
    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            _check_alembic_head()
        except Exception as _alembic_exc:
            logger.warning("[startup] Alembic head check raised unexpectedly: %s", _alembic_exc)

    yield
    # --- Shutdown ---
    task_services.stop_background_tasks(log=logger)
    scheduler_service.stop()
    try:
        from platform_layer.async_job_service import shutdown_async_jobs

        shutdown_async_jobs(wait=True)
    except Exception as exc:
        logger.warning("Async job shutdown failed (non-fatal): %s", exc)


app = FastAPI(title="A.I.N.D.Y. Memory Bridge", lifespan=lifespan)

# Rate limiting — protects AI/expensive endpoints from abuse
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Root — health probes + auth (no prefix; stable k8s / RFC paths)
for route in ROOT_ROUTERS:
    app.include_router(route, dependencies=[Depends(require_execution_context)])

# Platform — runtime API  (/platform/*)
for route in PLATFORM_ROUTERS:
    app.include_router(route, prefix="/platform", dependencies=[Depends(require_execution_context)])
# platform_router carries /platform internally; mount without extra prefix.
# Mount it after the static platform routers so /platform/flows/runs and other
# fixed console routes are not shadowed by dynamic path params like /flows/{name}.
app.include_router(platform_router, dependencies=[Depends(require_execution_context)])

# Apps — domain features  (/apps/*)
for route in APP_ROUTERS:
    app.include_router(route, prefix="/apps", dependencies=[Depends(require_execution_context)])

if os.getenv("AINDY_ENABLE_LEGACY_SURFACE", "false").lower() in {"1", "true", "yes"}:
    for route in APP_ROUTERS:
        app.include_router(route, dependencies=[Depends(require_execution_context)])

# CORS — explicit origins only (wildcard + credentials is a security violation)
import os as _os
_ALLOWED_ORIGINS = [
    o.strip()
    for o in _os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://localhost:5000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.exception_handler(HTTPException)
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Invalid request",
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
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

def _extract_user_id_from_request(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        from services.auth_service import decode_access_token
        payload = decode_access_token(token)
        if not payload or "sub" not in payload:
            return None
        return uuid.UUID(str(payload["sub"]))
    except Exception:
        return None


@app.middleware("http")
async def enforce_execution_contract(request: Request, call_next):
    request_token = set_current_request(request)
    try:
        response = await call_next(request)
        validate_execution_contract(request)
        return response
    finally:
        reset_current_request(request_token)


@app.middleware("http")
async def log_requests(request, call_next):
    trace_id = str(uuid.uuid4())
    trace_token = set_current_trace_id(trace_id)
    request.state.trace_id = trace_id
    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Request-ID"] = trace_id

        user_id = _extract_user_id_from_request(request)
        log_payload = {
            "event": "request_complete",
            "trace_id": trace_id,
            "request_id": trace_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "user_id": str(user_id) if user_id else None,
        }
        logger.info(json.dumps(log_payload, ensure_ascii=False))

        db = None
        try:
            db = SessionLocal()
            db.add(
                RequestMetric(
                    request_id=trace_id,
                    trace_id=trace_id,
                    user_id=user_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
            )
            db.commit()
        except Exception as exc:
            logger.warning("Failed to record request metric: %s", exc)
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception as exc:
                    emit_observability_event(
                        logger,
                        event="request_metric_session_close_failed",
                        trace_id=trace_id,
                        request_id=trace_id,
                        error=str(exc),
                    )
        return response
    finally:
        reset_current_trace_id(trace_token)

@app.get("/")
def home():
    return {"message": "A.I.N.D.Y. API is running!"}


