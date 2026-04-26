import json
import logging
import os
import sys
import time
import uuid
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import create_engine
from contextlib import asynccontextmanager

from AINDY.platform_layer import scheduler_service
from AINDY.platform_layer.deployment_contract import (
    background_tasks_enabled,
    event_bus_required,
    publish_api_runtime_state,
    reset_runtime_state,
)
from AINDY.platform_layer.cache_backend import NoOpCacheBackend
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.platform_layer.registry import (
    emit_event,
    get_plugin_boot_order,
    get_legacy_root_routers,
    get_routers,
    load_plugins,
    run_startup_hooks,
)
from AINDY.core.system_event_service import emit_error_event
from AINDY.db.database import SessionLocal
from AINDY.db.mongo_setup import ensure_mongo_ready, ping_mongo

# Backward compatibility for tests that monkeypatch main.init_mongo directly.
init_mongo = ensure_mongo_ready
from AINDY.core.execution_guard import require_execution_context, validate_execution_contract
from AINDY.routes import (
    APP_ROUTERS,
    LEGACY_ROOT_ROUTERS,
    PLATFORM_ROUTERS,
    ROOT_ROUTERS,
    platform_router,
)
from AINDY.config import settings
from AINDY.core.distributed_queue import QueueSaturatedError, validate_queue_backend
from AINDY.core.observability_events import emit_recovery_failure
from AINDY.kernel.circuit_breaker import CircuitOpenError
from AINDY.platform_layer.health_service import check_redis_available
from AINDY.platform_layer.trace_context import (
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

from apps._bootstrap_validator import BootstrapDependencyError, validate_bootstrap_deps


def _import_installed_alembic():
    """
    Import the site-packages Alembic package even though this repo also has
    repo-local alembic/ for migration scripts, which otherwise shadows the package.
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



logger = logging.getLogger("AINDY.main")
_OPENAI_PROJECT_KEY_PREFIX = "sk-" + "proj-"
try:
    validate_bootstrap_deps(os.path.join(ROOT_DIR, "apps"))
except BootstrapDependencyError as exc:
    logger.critical("Bootstrap dependency validation failed:\n%s", exc)
    raise RuntimeError(str(exc)) from exc

try:
    _resolved_boot_order = get_plugin_boot_order()
    if _resolved_boot_order:
        logger.info("Boot order resolved: %s", " -> ".join(_resolved_boot_order))
    load_plugins()
except RuntimeError:
    raise
except Exception as exc:
    logger.warning("Plugin loading skipped: %s", exc)


def _check_alembic_head() -> None:
    """Warn at startup if DB schema is behind the latest Alembic migration."""
    if not (Config and ScriptDirectory and MigrationContext):
        logger.warning("Schema guard unavailable: alembic not installed.")
        return

    try:
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()

        if current_rev != head_rev:
            logger.warning(
                "[startup] Alembic schema is not at head (db=%s head=%s).",
                current_rev,
                head_rev,
            )
        else:
            logger.info("[startup] Alembic schema is at head.")
    except Exception as exc:
        logger.warning("[startup] Could not verify Alembic schema: %s", exc)

def _ensure_dev_api_key():
    try:
        from AINDY.platform_layer.api_key_service import hash_key
        from AINDY.db.models.api_key import PlatformAPIKey
        from AINDY.db.models.user import User   # ✅ ADD THIS
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
                user = db.query(User).filter(User.id == existing.user_id).first()
                if user and not user.is_admin:
                    user.is_admin = True
                    db.commit()
                    logger.info("Existing dev key user elevated to admin.")
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
                    is_admin=True,
                )
                db.add(user)
                db.commit()
                logger.info("Dev user created.")
            elif not user.is_admin:
                user.is_admin = True
                db.commit()
                logger.info("Dev user elevated to admin.")

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


def _check_redis_available() -> bool:
    return check_redis_available(use_cache=False)


def _enforce_redis_startup_guard() -> None:
    if settings.is_testing:
        return
    if not settings.requires_redis:
        return
    if not settings.REDIS_URL:
        raise RuntimeError(
            "REDIS_URL is required in non-development deployments. "
            "Set REDIS_URL in your environment or set "
            "AINDY_REQUIRE_REDIS=false to allow single-instance mode."
        )
    if not _check_redis_available():
        raise RuntimeError(
            "Redis is configured but not reachable at startup. "
            "Verify REDIS_URL and Redis availability before starting."
        )
    logger.info("[startup] Redis connectivity verified.")


def _enforce_event_bus_startup_guard() -> None:
    if settings.is_testing:
        return
    if not event_bus_required():
        return
    if os.getenv("AINDY_EVENT_BUS_ENABLED", "true").lower() in {"0", "false", "no", "off"}:
        raise RuntimeError(
            "AINDY_EVENT_BUS_ENABLED=false is not permitted when Redis-backed deployment "
            "contracts are required. Enable the event bus for production-safe WAIT/RESUME behavior."
        )


def _enforce_cache_backend_coherence() -> None:
    """
    Reject configurations where requires_redis=True but the cache backend
    is set to memory. Two instances cannot share a memory cache; one would
    silently serve stale data to the other's clients.
    """
    if settings.is_testing:
        return
    if not settings.requires_redis:
        return

    cache_backend = settings.AINDY_CACHE_BACKEND.lower()

    if cache_backend == "memory":
        message = (
            "AINDY_CACHE_BACKEND=memory is not permitted when Redis is required "
            f"(ENV={settings.ENV!r}, AINDY_REQUIRE_REDIS={settings.AINDY_REQUIRE_REDIS}). "
            "Multiple instances cannot share an in-memory cache — each instance would "
            "serve inconsistent data. "
            "Set AINDY_CACHE_BACKEND=redis and provide REDIS_URL, "
            "or set AINDY_CACHE_BACKEND=off to explicitly disable caching."
        )
        if settings.is_prod:
            raise RuntimeError(message)
        logger.warning("[startup] Cache backend misconfiguration: %s", message)

    if cache_backend == "redis" and not settings.REDIS_URL:
        if not settings.is_prod:
            logger.warning(
                "[startup] AINDY_CACHE_BACKEND=redis but REDIS_URL is not set. "
                "Caching will be disabled. Set REDIS_URL or change "
                "AINDY_CACHE_BACKEND=off to suppress this warning."
            )


def _check_worker_presence(log) -> None:
    """
    Warn at startup when EXECUTION_MODE=distributed but no worker heartbeat is detected.

    This is a non-fatal advisory check. The server starts regardless — but operators
    need to know that jobs will queue silently if no worker is running.
    """
    from AINDY.config import settings

    if not settings.REDIS_URL:
        log.error(
            "[startup] EXECUTION_MODE=distributed requires REDIS_URL. "
            "Jobs will fail to enqueue. Set REDIS_URL or change EXECUTION_MODE=thread."
        )
        return

    heartbeat_key = "aindy:worker:heartbeat"
    try:
        import redis as _redis

        client = _redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        last_beat = client.get(heartbeat_key)
        if last_beat is None:
            log.warning(
                "[startup] EXECUTION_MODE=distributed: no worker heartbeat found in Redis "
                "(key=%s). If no worker process is running, enqueued jobs will not be "
                "processed. Start a worker with: "
                "WORKER_CONCURRENCY=1 python -m AINDY.worker.worker_loop",
                heartbeat_key,
            )
        else:
            log.info(
                "[startup] Worker heartbeat detected (last_beat=%s).", last_beat.decode()
            )
    except Exception as exc:
        log.warning(
            "[startup] Could not check worker heartbeat (Redis error: %s). "
            "If EXECUTION_MODE=distributed, ensure a worker process is running.",
            exc,
        )


def _check_nodus_importable() -> tuple[bool, str]:
    """Return whether the Nodus VM is importable plus a detail string."""
    nodus_path = os.environ.get("NODUS_SOURCE_PATH")
    if not nodus_path:
        return False, "NODUS_SOURCE_PATH is not set"

    if nodus_path not in sys.path:
        sys.path.insert(0, nodus_path)
    try:
        import importlib

        importlib.import_module("nodus.runtime.embedding")
        return True, nodus_path
    except ImportError as exc:
        return False, f"Nodus VM not importable from NODUS_SOURCE_PATH={nodus_path}: {exc}"


def _enforce_nodus_gate() -> None:
    """Enforce Nodus availability when any registered flow node requires it."""
    nodus_available, nodus_detail = _check_nodus_importable()

    from AINDY.runtime.flow_engine import NODE_REGISTRY as _NODE_REGISTRY

    registered_nodus_nodes = sorted(
        name
        for name in _NODE_REGISTRY
        if name == "nodus.execute" or name.startswith("nodus.")
    )

    if not registered_nodus_nodes:
        if not nodus_available:
            logger.info("[startup] Nodus VM not available; no Nodus nodes registered, skipping.")
        return

    if nodus_available:
        logger.info(
            "[startup] Nodus VM verified for %d registered nodus.* node(s).",
            len(registered_nodus_nodes),
        )
        return

    message = (
        "[startup] Registered Nodus nodes require the Nodus VM, but it is unavailable. "
        f"Registered nodes: {registered_nodus_nodes}. "
        f"{nodus_detail}. "
        "Set NODUS_SOURCE_PATH to the Nodus VM source directory."
    )
    if settings.is_prod:
        raise RuntimeError(message)
    logger.warning(message)


def _verify_flow_engines_started() -> None:
    """Log and validate the dual-engine runtime registration state."""
    from AINDY.runtime import get_engine_status, verify_engine_registration

    status = verify_engine_registration()
    logger.info(
        "[startup] Flow engines ready: dag_nodes=%d nodus_nodes=%d nodus_available=%s",
        status["dag_engine"]["registered_nodes"],
        status["nodus_engine"]["registered_nodes"],
        status["nodus_engine"]["available"],
    )


def _verify_required_syscalls_registered() -> None:
    """Verify that required syscalls are present after bootstrap."""
    from AINDY.kernel.syscall_registry import get_registered_syscalls
    from AINDY.platform_layer.registry import get_required_syscalls

    _required_syscalls = get_required_syscalls()
    if not _required_syscalls:
        return

    _registered_syscalls = set(get_registered_syscalls())
    _missing_syscalls = [
        name for name in _required_syscalls if name not in _registered_syscalls
    ]
    if _missing_syscalls:
        _syscall_message = (
            "[startup] Required syscalls missing after bootstrap: %s. "
            "Syscall-dependent flows will fail at runtime. "
            "Check that domain bootstrap modules loaded without errors."
        )
        if settings.is_prod and not settings.is_testing:
            logger.error(_syscall_message, _missing_syscalls)
            raise RuntimeError(
                f"Required syscalls not registered after bootstrap: {_missing_syscalls}"
            )
        logger.warning(_syscall_message, _missing_syscalls)
    else:
        logger.info(
            "[startup] Syscall registration verified: %d required syscall(s) present.",
            len(_required_syscalls),
        )


def _log_async_job_capacity_advisory() -> None:
    """Log startup guidance for async job capacity in thread mode."""
    if settings.is_testing:
        return
    if not settings.AINDY_JOB_WARN_CAPACITY:
        return
    if settings.EXECUTION_MODE != "thread":
        return

    _pool_size = settings.AINDY_ASYNC_JOB_WORKERS
    _queue_max = settings.AINDY_ASYNC_QUEUE_MAXSIZE
    _ai_job_duration_s = 15
    _throughput = _pool_size / _ai_job_duration_s

    if _pool_size < 8:
        logger.warning(
            "[startup] Thread pool is small for AI workloads: "
            "AINDY_ASYNC_JOB_WORKERS=%d. At ~%ds/job this sustains "
            "%.1f jobs/second. Recommend at least 8 workers, or switch "
            "to EXECUTION_MODE=distributed for multi-user deployments.",
            _pool_size,
            _ai_job_duration_s,
            _throughput,
        )
    else:
        logger.info(
            "[startup] Thread pool configured: workers=%d queue_max=%d "
            "(estimated throughput=%.1f jobs/s at 15s/job). "
            "For multi-user or high-throughput deployments, consider "
            "EXECUTION_MODE=distributed.",
            _pool_size,
            _queue_max,
            _throughput,
        )

    if settings.AINDY_ASYNC_MAX_CONCURRENT_PER_USER == 0:
        logger.warning(
            "[startup] AINDY_ASYNC_MAX_CONCURRENT_PER_USER=0 (no per-user cap). "
            "A single user can exhaust the full thread pool. "
            "Set AINDY_ASYNC_MAX_CONCURRENT_PER_USER=2 to enforce fairness."
        )


def _cache_behavior_mode() -> str:
    if settings.is_testing or os.getenv("PYTEST_CURRENT_TEST"):
        return "testing"
    if settings.is_dev:
        return "development"
    return "production"


def _update_db_pool_metrics() -> None:
    """Scrape SQLAlchemy pool stats into Prometheus gauges."""
    try:
        from AINDY.db.database import get_pool_status
        from AINDY.platform_layer.metrics import (
            db_pool_checkedout,
            db_pool_overflow,
            db_pool_size,
        )

        status = get_pool_status()
        db_pool_size.set(status.get("pool_size", 0))
        db_pool_checkedout.set(status.get("checkedout", 0))
        db_pool_overflow.set(status.get("overflow", 0))
    except Exception as exc:
        logger.warning("DB pool metrics scrape failed (non-fatal): %s", exc)


def _remaining_shutdown_budget(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _initialize_cache_backend() -> str:
    """Initialize FastAPICache with explicit multi-instance semantics.

    Returns one of: ``redis``, ``memory``, ``disabled``.
    """
    cache_backend = settings.AINDY_CACHE_BACKEND.lower()
    behavior_mode = _cache_behavior_mode()

    if behavior_mode == "testing":
        FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
        logger.info("Cache backend initialized: memory (testing mode)")
        return "memory"

    if cache_backend == "redis":
        try:
            from redis import asyncio as aioredis
            from fastapi_cache.backends.redis import RedisBackend
        except Exception as exc:
            if behavior_mode == "production":
                FastAPICache.init(NoOpCacheBackend(), prefix="fastapi-cache")
                logger.warning(
                    "Redis cache backend unavailable in production; caching disabled "
                    "to avoid instance-local divergence: %s",
                    exc,
                )
                return "disabled"
            logger.warning("Redis cache backend unavailable; falling back to memory cache: %s", exc)
            FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
            return "memory"

        if not settings.REDIS_URL:
            if behavior_mode == "production":
                FastAPICache.init(NoOpCacheBackend(), prefix="fastapi-cache")
                logger.warning(
                    "[cache] AINDY_CACHE_BACKEND=redis but REDIS_URL is not set in production: "
                    "caching DISABLED. All cache misses will hit the database. "
                    "Set REDIS_URL to enable distributed caching."
                )
                return "disabled"
            logger.warning(
                "AINDY_CACHE_BACKEND=redis but REDIS_URL is not set; "
                "falling back to in-memory cache for local development."
            )
            FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
            return "memory"

        try:
            redis = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf8",
                decode_responses=True,
            )
            FastAPICache.init(RedisBackend(redis), prefix="fastapi-cache")
            logger.info("Cache backend initialized: redis")
            return "redis"
        except Exception as exc:
            if behavior_mode == "production":
                FastAPICache.init(NoOpCacheBackend(), prefix="fastapi-cache")
                logger.warning(
                    "Redis cache initialization failed in production; caching disabled "
                    "to avoid instance-local divergence: %s",
                    exc,
                )
                return "disabled"
            logger.warning(
                "Redis cache initialization failed; falling back to in-memory cache for development: %s",
                exc,
            )
            FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
            return "memory"

    if cache_backend == "memory":
        if behavior_mode == "production":
            FastAPICache.init(NoOpCacheBackend(), prefix="fastapi-cache")
            logger.warning(
                "[cache] AINDY_CACHE_BACKEND=memory in production: caching DISABLED. "
                "In-memory caches are not safe for multi-instance deployments. "
                "Use AINDY_CACHE_BACKEND=redis with REDIS_URL, or "
                "AINDY_CACHE_BACKEND=off to silence this warning."
            )
            return "disabled"
        FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
        logger.info("Cache backend initialized: memory")
        return "memory"

    if cache_backend in {"off", "disabled", "none"}:
        FastAPICache.init(NoOpCacheBackend(), prefix="fastapi-cache")
        logger.info("Cache backend initialized: disabled")
        return "disabled"

    raise RuntimeError(
        f"Unsupported AINDY_CACHE_BACKEND={settings.AINDY_CACHE_BACKEND!r}. "
        "Expected one of: redis, memory, off."
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    reset_runtime_state()
    publish_api_runtime_state(
        startup_complete=False,
        background_enabled=False,
        scheduler_role="disabled",
        event_bus_ready=False,
    )
    # SECRET_KEY guard — reject insecure placeholder outside local dev/test
    _placeholder = "dev-secret-change-in-production"
    if settings.SECRET_KEY == _placeholder:
        if settings.requires_redis:
            raise RuntimeError(
                "SECRET_KEY is using the insecure default placeholder. "
                "Set a strong SECRET_KEY in your .env before running in non-development deployments."
            )
        else:
            logger.warning(
                "SECRET_KEY is using the insecure default placeholder. "
                "This is acceptable for local development but MUST be changed before production."
            )
    _min_key_length = 32
    if not settings.is_testing and len(settings.SECRET_KEY) < _min_key_length:
        if settings.requires_redis:
            raise RuntimeError(
                f"SECRET_KEY is too short ({len(settings.SECRET_KEY)} chars). "
                f"Minimum required: {_min_key_length} characters for non-development deployments."
            )
        else:
            logger.warning(
                "SECRET_KEY is short (%d chars). Use at least %d chars in production.",
                len(settings.SECRET_KEY), _min_key_length,
            )

    # Redis production guard
    _enforce_redis_startup_guard()
    _enforce_event_bus_startup_guard()
    _enforce_cache_backend_coherence()
    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        if not settings.REDIS_URL and not settings.requires_redis:
            logger.warning(
                "[startup] Redis is not configured (REDIS_URL is unset). "
                "Running in single-instance mode. WAIT/RESUME events will not "
                "propagate across multiple instances. Set REDIS_URL and "
                "AINDY_REQUIRE_REDIS=true for multi-instance deployments."
            )
    logger.info(
        "Startup config: ENV=%s requires_redis=%s execution_mode=%s cache=%s",
        settings.ENV,
        settings.requires_redis,
        settings.EXECUTION_MODE,
        settings.AINDY_CACHE_BACKEND,
    )

    # Cache backend selection:
    # "redis"  - correct for multi-instance deployments (requires REDIS_URL)
    # "memory" - single-process only; two instances will have independent caches
    # Falls back to memory if REDIS_URL is absent regardless of this setting.
    cache_mode = _initialize_cache_backend()
    logger.info("Cache behavior mode: %s", cache_mode)

    try:
        ensure_mongo_ready(required=settings.MONGO_REQUIRED)
        mongo_status = ping_mongo()
        if mongo_status.get("status") != "ok":
            logger.warning(
                "MongoDB unavailable at startup — social features degraded: %s",
                mongo_status.get("reason"),
            )
    except Exception as exc:
        logger.warning("MongoDB init failed — social features degraded: %s", exc)

    if settings.ENV == "dev":
        _ensure_dev_api_key()

    if settings.is_prod and str(settings.OPENAI_API_KEY).startswith(_OPENAI_PROJECT_KEY_PREFIX):
        logger.warning(
            "OPENAI_API_KEY uses the project-key prefix in production; verify rotation after any potential exposure."
        )

    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        validate_queue_backend()
    if (
        not settings.is_testing
        and not os.getenv("PYTEST_CURRENT_TEST")
        and settings.EXECUTION_MODE == "distributed"
    ):
        _check_worker_presence(logger)
    _log_async_job_capacity_advisory()

    enforce_schema = os.getenv("AINDY_ENFORCE_SCHEMA", "true").lower() in {"1", "true", "yes"}
    if not enforce_schema and settings.is_prod:
        raise RuntimeError(
            "AINDY_ENFORCE_SCHEMA=false is not permitted in production (ENV=production). "
            "Schema enforcement is a required safety gate. "
            "To deploy with a schema change, run: alembic upgrade head"
        )
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
    elif not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        logger.warning(
            "[startup] Schema enforcement is DISABLED (AINDY_ENFORCE_SCHEMA=false). "
            "The server will start even if the database schema is behind migrations. "
            "This is only safe for development. Do not use in production."
        )

    enable_background = background_tasks_enabled()
    publish_api_runtime_state(background_enabled=enable_background)

    startup_results = emit_event(
        "system.startup",
        {"enable": enable_background, "log": logger, "source": "main"},
    )
    is_leader = enable_background and all(result is not False for result in startup_results)
    scheduler_role = "disabled"
    if is_leader:
        scheduler_service.start()
        _sched = scheduler_service.get_scheduler()
        if not getattr(_sched, "running", False):
            raise RuntimeError(
                "APScheduler failed to start. Check apscheduler installation."
            )
        _update_db_pool_metrics()
        _sched.add_job(
            _update_db_pool_metrics,
            trigger="interval",
            seconds=30,
            id="db_pool_metrics_tick",
            name="DB pool metrics tick",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        scheduler_role = "leader"
    elif enable_background:
        scheduler_role = "follower"
    publish_api_runtime_state(scheduler_role=scheduler_role)

    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        from AINDY.core.request_metric_writer import get_writer as get_metric_writer

        get_metric_writer().start()
    try:
        from AINDY.platform_layer.async_job_service import start_async_job_service
        from AINDY.memory.memory_ingest_service import configure_memory_ingest_queue

        start_async_job_service()
        configure_memory_ingest_queue().start()
    except Exception as exc:
        logger.warning("Async shutdown services startup failed: %s", exc)

    # Register domain syscall handlers (must come before flow registration)
    from AINDY.kernel.syscall_handlers import register_all_domain_handlers
    register_all_domain_handlers()
    _verify_required_syscalls_registered()

    # Register Flow Engine flows and nodes (static startup definitions)
    from AINDY.runtime.flow_definitions import register_all_flows
    register_all_flows()
    from AINDY.runtime import (
        flow_definitions_engine,
        flow_definitions_memory,
        flow_definitions_observability,
    )
    flow_definitions_memory.register()
    flow_definitions_engine.register()
    flow_definitions_observability.register()
    _enforce_nodus_gate()
    _verify_flow_engines_started()

    # Verify that domain-declared required flow nodes were actually registered —
    # silent failures in flow modules can otherwise produce a running server with
    # a broken flow graph.
    from AINDY.platform_layer.registry import get_required_flow_nodes
    from AINDY.runtime.flow_engine import NODE_REGISTRY as _NODE_REGISTRY
    _required_nodes = get_required_flow_nodes()
    _missing_nodes = [n for n in _required_nodes if n not in _NODE_REGISTRY]
    if _missing_nodes:
        message = (
            "[startup] Required flow nodes missing from registry after bootstrap: %s. "
            "Cross-domain flows will be unavailable for these nodes."
        )
        if settings.is_prod:
            logger.error(message, _missing_nodes)
            raise RuntimeError(
                f"Required flow nodes missing after bootstrap: {_missing_nodes}"
            )
        logger.error(message, _missing_nodes)

    # Restore dynamic platform registrations (flows, nodes, webhook subs) from DB.
    # Runs after register_all_flows() so static nodes are available for flow validation.
    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        from AINDY.platform_layer.platform_loader import (
            load_dynamic_registry,
            verify_restore_completeness,
        )
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
        _restore_verify_db = SessionLocal()
        try:
            _restore_result = await verify_restore_completeness(_restore_verify_db)
            logger.info(
                "Registry restore complete: flows=%d/%d nodes=%d/%d webhooks=%d/%d",
                _restore_result["flows"]["registry_count"],
                _restore_result["flows"]["db_count"],
                _restore_result["nodes"]["registry_count"],
                _restore_result["nodes"]["db_count"],
                _restore_result["webhooks"]["registry_count"],
                _restore_result["webhooks"]["db_count"],
            )
            if not _restore_result["all_ok"]:
                logger.error(
                    "Registry restore INCOMPLETE — some capabilities were not restored"
                )
        finally:
            _restore_verify_db.close()

    # Enforce execution boundary: no router may import services directly
    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        from AINDY.core.router_guard import RouterBoundaryViolation, validate_router_boundary
        try:
            validate_router_boundary()
        except RouterBoundaryViolation as _rbv:
            logger.error("EXECUTION BOUNDARY VIOLATED:\n%s", _rbv)
            raise RuntimeError(str(_rbv)) from _rbv

    # Sprint N+7: Recover any FlowRun/AgentRun rows stranded by prior crash
    if enable_background and not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        from AINDY.agents.stuck_run_service import scan_and_recover_stuck_runs
        _scan_db = SessionLocal()
        try:
            _recovered = scan_and_recover_stuck_runs(
                _scan_db,
                staleness_minutes=settings.STUCK_RUN_THRESHOLD_MINUTES,
            )
            if _recovered:
                logger.info("[startup] Stuck-run scan recovered %d run(s)", _recovered)
                try:
                    from AINDY.platform_layer.metrics import startup_recovery_runs_recovered_total

                    startup_recovery_runs_recovered_total.labels(
                        recovery_type="stuck_runs"
                    ).inc(_recovered)
                except Exception:
                    pass
        except Exception as _scan_exc:
            emit_recovery_failure("stuck_runs", _scan_exc, _scan_db, logger=logger)
        finally:
            _scan_db.close()

    # Distributed event bus: subscribe to Redis pub/sub on ALL instances so
    # that resume events emitted by any instance wake flows registered in this
    # instance's local _waiting dict.  Must start BEFORE rehydration so the
    # thread is ready when the first event arrives.  Non-fatal: if Redis is
    # unavailable the system falls back to local-only notify_event behaviour.
    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            from AINDY.kernel.event_bus import get_event_bus
            get_event_bus().start_subscriber()
            publish_api_runtime_state(event_bus_ready=True)
        except Exception as _bus_exc:
            publish_api_runtime_state(event_bus_ready=False)
            if event_bus_required():
                raise RuntimeError(
                    f"Event bus subscriber failed to start: {_bus_exc}"
                ) from _bus_exc
            logger.warning(
                "[startup] Event bus subscriber failed to start (non-fatal): %s", _bus_exc
            )
        try:
            from AINDY.kernel.event_bus import get_event_bus

            _bus = get_event_bus()
            _bus_status = _bus.get_status()
            if _bus_status.get("mode") == "local-only" and not settings.requires_redis:
                logger.warning(
                    "[startup] WAIT/RESUME is operating in LOCAL-ONLY mode. "
                    "Flows that enter WAIT on one instance CANNOT be resumed by "
                    "events received on a different instance. "
                    "For multi-instance deployments, set REDIS_URL and ensure "
                    "the event bus subscriber is running (AINDY_EVENT_BUS_ENABLED=true)."
                )
            elif _bus_status.get("mode") == "cross-instance":
                logger.info(
                    "[startup] WAIT/RESUME propagation: cross-instance (Redis pub/sub active)."
                )
        except Exception as _status_exc:
            logger.debug("[startup] Could not check event bus propagation mode: %s", _status_exc)

    # WAIT rehydration: re-register all waiting EUs with the SchedulerEngine.
    # Must run after SchedulerEngine is initialised (above) and after the
    # stuck-run scan (which may transition some EUs out of waiting status).
    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        from AINDY.core.wait_rehydration import rehydrate_waiting_eus
        _rehydrate_db = SessionLocal()
        try:
            _n_rehydrated = rehydrate_waiting_eus(_rehydrate_db)
            if _n_rehydrated:
                logger.info("[startup] WAIT rehydration registered %d EU(s)", _n_rehydrated)
        except Exception as _rehydrate_exc:
            emit_recovery_failure("wait_eus", _rehydrate_exc, _rehydrate_db, logger=logger)
        finally:
            _rehydrate_db.close()

    # FlowRun WAIT rehydration: reconstruct PersistentFlowRunner callbacks for
    # all FlowRuns with status="waiting" so they can be resumed when their
    # event fires.  Must run after register_all_flows() so FLOW_REGISTRY is
    # populated, and after EU rehydration so the scheduler entry for the same
    # run_id already has the EU-level callback when we add the flow callback.
    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        from AINDY.core.flow_run_rehydration import rehydrate_waiting_flow_runs
        _flow_rehydrate_db = SessionLocal()
        try:
            _n_flow_rehydrated = rehydrate_waiting_flow_runs(_flow_rehydrate_db)
            if _n_flow_rehydrated:
                logger.info(
                    "[startup] FlowRun rehydration registered %d run(s)", _n_flow_rehydrated
                )
        except Exception as _flow_rehydrate_exc:
            emit_recovery_failure(
                "flow_runs", _flow_rehydrate_exc, _flow_rehydrate_db, logger=logger
            )
        finally:
            _flow_rehydrate_db.close()

    if not settings.is_testing and not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            from AINDY.kernel.scheduler_engine import get_scheduler_engine
            from AINDY.kernel.event_bus import get_event_bus
            get_scheduler_engine().mark_rehydration_complete()
            get_event_bus().drain_buffered_events()
        except Exception as _drain_exc:
            emit_recovery_failure("event_drain", _drain_exc, None, logger=logger)
    else:
        try:
            from AINDY.kernel.scheduler_engine import get_scheduler_engine

            get_scheduler_engine().mark_rehydration_complete()
        except Exception as exc:
            logger.debug("[startup] Test-mode scheduler rehydration mark skipped: %s", exc)

    run_startup_hooks(
        {
            "is_testing": settings.is_testing or bool(os.getenv("PYTEST_CURRENT_TEST")),
            "log": logger,
            "session_factory": SessionLocal,
            "source": "main",
        }
    )
    publish_api_runtime_state(startup_complete=True)

    yield
    # --- Shutdown ---
    shutdown_deadline = time.monotonic() + float(settings.AINDY_SHUTDOWN_TIMEOUT_SECONDS)
    publish_api_runtime_state(startup_complete=False, event_bus_ready=False)
    emit_event("system.shutdown", {"log": logger, "source": "main"})
    try:
        from AINDY.platform_layer.async_job_service import stop_async_job_service

        stop_async_job_service(
            timeout_seconds=_remaining_shutdown_budget(shutdown_deadline),
            reopen=settings.is_testing,
        )
    except Exception as exc:
        logger.warning("Async job shutdown failed (non-fatal): %s", exc)
    try:
        from AINDY.memory.memory_ingest_service import configure_memory_ingest_queue

        configure_memory_ingest_queue().stop(
            timeout=_remaining_shutdown_budget(shutdown_deadline),
            drain=True,
        )
    except Exception as exc:
        logger.warning("Memory ingest queue shutdown failed: %s", exc)
    try:
        from AINDY.core.request_metric_writer import get_writer as get_metric_writer

        get_metric_writer().stop(timeout=_remaining_shutdown_budget(shutdown_deadline))
    except Exception as exc:
        logger.warning("Request metric writer shutdown failed: %s", exc)
    try:
        scheduler_service.stop(
            timeout_seconds=_remaining_shutdown_budget(shutdown_deadline)
        )
    except Exception as exc:
        logger.warning("Scheduler shutdown failed (non-fatal): %s", exc)
    try:
        from AINDY.kernel.event_bus import get_event_bus

        get_event_bus().stop(timeout=_remaining_shutdown_budget(shutdown_deadline))
    except Exception as exc:
        logger.warning("Event bus shutdown failed (non-fatal): %s", exc)
    if settings.is_testing:
        try:
            from AINDY.kernel.scheduler_engine import get_scheduler_engine

            get_scheduler_engine().reset()
        except Exception as exc:
            logger.debug("Scheduler engine reset skipped during test teardown: %s", exc)
    try:
        from AINDY.db.mongo_setup import close_mongo_client

        close_mongo_client()
    except Exception as exc:
        logger.warning("MongoDB shutdown failed (non-fatal): %s", exc)
    try:
        from AINDY.db.database import engine

        if not settings.is_testing:
            engine.dispose()
    except Exception as exc:
        logger.warning("Database engine disposal failed (non-fatal): %s", exc)
    logger.info("shutdown complete")


