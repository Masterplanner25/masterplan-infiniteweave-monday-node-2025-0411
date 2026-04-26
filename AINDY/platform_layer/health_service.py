from __future__ import annotations

import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from AINDY.config import settings
from AINDY.platform_layer.deployment_contract import (
    deployment_contract_summary,
    event_bus_required,
    get_api_runtime_state,
    queue_backend_required,
    redis_required,
    worker_required,
)
from AINDY.platform_layer.registry import get_degraded_domains
from AINDY.platform_layer.registry import get_all_health_checks

logger = logging.getLogger(__name__)

HealthStatus = Literal["ok", "degraded", "unavailable"]


@dataclass
class DependencyStatus:
    name: str
    status: HealthStatus
    latency_ms: float | None = None
    detail: str | None = None
    critical: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemHealth:
    tier: Literal["healthy", "degraded", "critical"]
    http_status: int
    dependencies: list[DependencyStatus] = field(default_factory=list)

    def to_dict(self) -> dict:
        domains = get_domain_health()
        degraded_domains = _merge_degraded_domains(domains)
        platform = build_platform_status(self.dependencies)
        return {
            "status": derive_public_status(self.tier, platform, domains),
            "tier": self.tier,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": settings.VERSION,
            "degraded_domains": degraded_domains,
            "degraded_apps": degraded_domains,
            "platform": platform,
            "domains": domains,
            "memory_ingest_queue": get_memory_ingest_queue_status(),
            "deployment_contract": deployment_contract_summary(),
            "dependencies": {
                dep.name: {
                    "status": dep.status,
                    "latency_ms": dep.latency_ms,
                    "detail": dep.detail,
                    **dep.metadata,
                }
                for dep in self.dependencies
            },
        }


_REDIS_HEALTH_TTL_SECONDS = 10.0
_HEALTH_CACHE_TTL = 10.0

_redis_health_lock = threading.Lock()
_redis_health_checked_at = 0.0
_redis_health_cached_result = False

_health_cache_lock = threading.Lock()
_health_cache: SystemHealth | None = None
_health_cache_checked_at = 0.0


def _normalize_domain_health_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"status": "degraded", "reason": "health check returned a non-dict result"}
    status = str(result.get("status") or "").lower()
    if status == "ok":
        return {"status": "ok"}
    if status == "degraded":
        normalized = {"status": "degraded"}
        if result.get("reason"):
            normalized["reason"] = str(result["reason"])
        return normalized
    if status:
        return {
            "status": "degraded",
            "reason": str(result.get("reason") or f"invalid health status: {status}"),
        }
    return {"status": "degraded", "reason": "health check returned no status"}


def get_domain_health(timeout_seconds: float = 2.0) -> dict[str, dict[str, Any]]:
    checks = get_all_health_checks()
    if not checks:
        return {}

    executor = ThreadPoolExecutor(max_workers=max(1, len(checks)))
    futures = {
        executor.submit(check_fn): app_name
        for app_name, check_fn in checks.items()
    }
    results: dict[str, dict[str, Any]] = {}
    try:
        done, not_done = wait(tuple(futures.keys()), timeout=timeout_seconds)
        for future in done:
            app_name = futures[future]
            try:
                results[app_name] = _normalize_domain_health_result(future.result())
            except Exception as exc:
                results[app_name] = {"status": "degraded", "reason": str(exc)}
        for future in not_done:
            app_name = futures[future]
            future.cancel()
            results[app_name] = {"status": "degraded", "reason": "health check timed out"}
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return {
        app_name: results[app_name]
        for app_name in sorted(results)
    }


def _merge_degraded_domains(domains: dict[str, dict[str, Any]]) -> list[str]:
    _ = domains
    return list(get_degraded_domains())


def build_platform_status(dependencies: list[DependencyStatus]) -> dict[str, str]:
    dep_by_name = {dep.name: dep for dep in dependencies}
    postgres = dep_by_name.get("postgres")
    schema = dep_by_name.get("schema")
    queue = dep_by_name.get("queue")
    redis = dep_by_name.get("redis")
    mongo = dep_by_name.get("mongo")

    database_ok = (
        postgres is not None
        and postgres.status == "ok"
        and (schema is None or schema.status == "ok" or not schema.critical)
    )

    execution_engine_ok = True
    if queue is not None and queue.critical:
        execution_engine_ok = queue.status == "ok"

    cache_ok = True
    if redis is not None:
        if redis.critical:
            cache_ok = redis.status == "ok"
        else:
            cache_ok = redis.status in {"ok", "degraded"}

    mongo_ok = True
    if mongo is not None:
        mongo_ok = mongo.status == "ok"

    scheduler_ok = True
    try:
        from AINDY.platform_layer import scheduler_service

        background_enabled = get_api_runtime_state().get("background_enabled", True)
        scheduler_role = get_api_runtime_state().get("scheduler_role", "disabled")
        if background_enabled and scheduler_role == "leader":
            scheduler = scheduler_service.get_scheduler()
            scheduler_ok = bool(getattr(scheduler, "running", False))
    except Exception:
        scheduler_ok = False

    return {
        "execution_engine": "ok" if execution_engine_ok else "degraded",
        "scheduler": "ok" if scheduler_ok else "degraded",
        "database": "ok" if database_ok else "degraded",
        "cache": "ok" if cache_ok else "degraded",
        "mongodb": "ok" if mongo_ok else "degraded",
    }


def derive_public_status(
    tier: Literal["healthy", "degraded", "critical"],
    platform: dict[str, str],
    domains: dict[str, dict[str, Any]],
) -> Literal["ok", "degraded", "unhealthy"]:
    if tier == "critical":
        return "unhealthy"
    if platform.get("database") == "degraded" or platform.get("execution_engine") == "degraded":
        return "unhealthy"
    if any(value == "degraded" for value in platform.values()):
        return "degraded"
    if any(result.get("status") != "ok" for result in domains.values()):
        return "degraded"
    return "ok"


def get_memory_ingest_queue_status() -> dict[str, Any]:
    try:
        from AINDY.memory.memory_ingest_service import configure_memory_ingest_queue

        snapshot = configure_memory_ingest_queue().snapshot()
        return {
            "depth": int(snapshot.get("depth", 0)),
            "capacity": int(snapshot.get("capacity", settings.AINDY_MEMORY_INGEST_QUEUE_MAX)),
            "dropped_total": int(snapshot.get("dropped_total", 0)),
            "worker_running": bool(snapshot.get("worker_running", False)),
        }
    except Exception as exc:
        return {
            "depth": 0,
            "capacity": int(settings.AINDY_MEMORY_INGEST_QUEUE_MAX),
            "dropped_total": 0,
            "worker_running": False,
            "detail": str(exc),
        }


def check_db_connectivity(db: Session) -> bool:
    db.execute(text("SELECT 1"))
    return True


def check_db_ready(db: Session) -> bool:
    db.execute(text("SELECT 1"))
    return True


def invalidate_redis_health_cache() -> None:
    global _redis_health_checked_at

    with _redis_health_lock:
        _redis_health_checked_at = 0.0


def _import_installed_alembic():
    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    root_dir = os.path.abspath(os.path.join(app_dir, os.pardir))
    removed: list[tuple[int, str]] = []
    for index in range(len(sys.path) - 1, -1, -1):
        path = sys.path[index]
        normalized = os.path.abspath(path or os.getcwd())
        if normalized in {app_dir, root_dir}:
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


def _postgres_probe_engine(timeout: float):
    url = make_url(settings.DATABASE_URL)
    connect_args: dict[str, object] = {}
    if url.get_backend_name().startswith("postgres"):
        connect_args["connect_timeout"] = max(1, int(timeout))
    return create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


def check_postgres(timeout: float = 2.0) -> DependencyStatus:
    start = time.monotonic()
    engine = None
    try:
        engine = _postgres_probe_engine(timeout)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency = round((time.monotonic() - start) * 1000, 2)
        return DependencyStatus(
            name="postgres",
            status="ok",
            latency_ms=latency,
            critical=True,
        )
    except Exception as exc:
        latency = round((time.monotonic() - start) * 1000, 2)
        return DependencyStatus(
            name="postgres",
            status="unavailable",
            latency_ms=latency,
            detail=str(exc),
            critical=True,
        )
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass


def check_redis(timeout: float = 1.0, *, use_cache: bool = True) -> DependencyStatus:
    global _redis_health_checked_at, _redis_health_cached_result

    start = time.monotonic()
    now = time.monotonic()
    if use_cache and (now - _redis_health_checked_at) < _REDIS_HEALTH_TTL_SECONDS:
        latency = round((time.monotonic() - start) * 1000, 2)
        return DependencyStatus(
            name="redis",
            status="ok" if _redis_health_cached_result else "unavailable",
            latency_ms=latency if settings.REDIS_URL else None,
            detail=None if (_redis_health_cached_result or settings.REDIS_URL) else "REDIS_URL not configured (single-instance mode)",
            critical=redis_required(),
        ) if settings.REDIS_URL else DependencyStatus(
            name="redis",
            status="degraded",
            detail="REDIS_URL not configured (single-instance mode)",
            critical=redis_required(),
        )

    with _redis_health_lock:
        now = time.monotonic()
        if use_cache and (now - _redis_health_checked_at) < _REDIS_HEALTH_TTL_SECONDS:
            latency = round((time.monotonic() - start) * 1000, 2)
            return DependencyStatus(
                name="redis",
                status="ok" if _redis_health_cached_result else "unavailable",
                latency_ms=latency if settings.REDIS_URL else None,
                detail=None if (_redis_health_cached_result or settings.REDIS_URL) else "REDIS_URL not configured (single-instance mode)",
                critical=redis_required(),
            ) if settings.REDIS_URL else DependencyStatus(
                name="redis",
                status="degraded",
                detail="REDIS_URL not configured (single-instance mode)",
                critical=redis_required(),
            )

        if not settings.REDIS_URL:
            status = DependencyStatus(
                name="redis",
                status="degraded",
                detail="REDIS_URL not configured (single-instance mode)",
                critical=redis_required(),
            )
            _redis_health_cached_result = False
            _redis_health_checked_at = now
            return status

        try:
            import redis as _redis_sync

            client = _redis_sync.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=timeout,
                socket_timeout=timeout,
            )
            client.ping()
            _redis_health_cached_result = True
            latency = round((time.monotonic() - start) * 1000, 2)
            status = DependencyStatus(
                name="redis",
                status="ok",
                latency_ms=latency,
                critical=redis_required(),
            )
        except Exception as exc:
            logger.warning("[health] Redis ping failed: %s", exc)
            _redis_health_cached_result = False
            latency = round((time.monotonic() - start) * 1000, 2)
            status = DependencyStatus(
                name="redis",
                status="unavailable",
                latency_ms=latency,
                detail=str(exc),
                critical=redis_required(),
            )

        _redis_health_checked_at = now
        return status


def check_redis_available(*, use_cache: bool = True) -> bool:
    return check_redis(use_cache=use_cache).status == "ok"


def check_queue() -> DependencyStatus:
    try:
        from AINDY.core.distributed_queue import get_queue_health_snapshot

        snapshot = get_queue_health_snapshot()
        status: HealthStatus = "degraded" if snapshot["degraded"] else "ok"
        detail = snapshot.get("reason")
        return DependencyStatus(
            name="queue",
            status=status,
            detail=detail,
            critical=queue_backend_required(),
            metadata={
                "backend": snapshot["backend"],
                "degraded": snapshot["degraded"],
                "redis_available": snapshot["redis_available"],
            },
        )
    except Exception as exc:
        return DependencyStatus(
            name="queue",
            status="unavailable",
            detail=str(exc),
            critical=queue_backend_required(),
            metadata={
                "backend": "unknown",
                "degraded": True,
                "redis_available": False,
            },
        )


def check_mongo(timeout: float = 2.0) -> DependencyStatus:
    start = time.monotonic()
    try:
        if not getattr(settings, "MONGO_URL", None):
            return DependencyStatus(
                name="mongo",
                status="degraded",
                detail="MONGO_URL not configured (embeddings disabled)",
                critical=False,
            )
        if settings.SKIP_MONGO_PING:
            return DependencyStatus(
                name="mongo",
                status="degraded",
                detail="Mongo health ping skipped by configuration",
                critical=False,
            )

        from AINDY.db.mongo_setup import ensure_mongo_ready, ping_mongo

        ensure_mongo_ready(required=False)
        ping = ping_mongo()
        if ping.get("status") != "ok":
            latency = round((time.monotonic() - start) * 1000, 2)
            return DependencyStatus(
                name="mongo",
                status="unavailable",
                latency_ms=latency,
                detail=str(ping.get("reason") or "MongoDB ping failed"),
                critical=False,
            )

        latency = round((time.monotonic() - start) * 1000, 2)
        return DependencyStatus(
            name="mongo",
            status="ok",
            latency_ms=latency,
            critical=False,
        )
    except Exception as exc:
        latency = round((time.monotonic() - start) * 1000, 2)
        return DependencyStatus(
            name="mongo",
            status="unavailable",
            latency_ms=latency,
            detail=str(exc),
            critical=False,
        )


def check_schema() -> DependencyStatus:
    Config, ScriptDirectory, MigrationContext = _import_installed_alembic()
    if not (Config and ScriptDirectory and MigrationContext):
        return DependencyStatus(
            name="schema",
            status="degraded",
            detail="Schema check unavailable: alembic not installed",
            critical=False,
        )

    engine = None
    try:
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current = context.get_current_revision()

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
        script = ScriptDirectory.from_config(cfg)
        heads = set(script.get_heads())

        if current in heads:
            return DependencyStatus(name="schema", status="ok", critical=True)

        return DependencyStatus(
            name="schema",
            status="unavailable",
            detail=f"DB at {current!r}, head is {sorted(heads)!r}",
            critical=True,
        )
    except Exception as exc:
        return DependencyStatus(
            name="schema",
            status="degraded",
            detail=f"Schema check unavailable: {exc}",
            critical=False,
        )
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass


def check_ai_providers() -> DependencyStatus:
    from AINDY.kernel.circuit_breaker import (
        CircuitState,
        get_deepseek_circuit_breaker,
        get_openai_circuit_breaker,
    )

    def _summarize(cb) -> dict[str, Any]:
        state = cb.state
        result: dict[str, Any] = {
            "circuit": state.value,
            "failure_count": cb.failure_count,
        }
        if state != CircuitState.CLOSED:
            opened = cb.opened_at
            result["opened_at"] = opened.isoformat() if opened else None
        return result

    openai = _summarize(get_openai_circuit_breaker())
    deepseek = _summarize(get_deepseek_circuit_breaker())
    any_open = any(provider["circuit"] == "open" for provider in (openai, deepseek))
    return DependencyStatus(
        name="ai_providers",
        status="degraded" if any_open else "ok",
        critical=False,
        metadata={
            "openai": openai,
            "deepseek": deepseek,
        },
    )


def get_system_health(*, force: bool = False) -> SystemHealth:
    global _health_cache, _health_cache_checked_at

    now = time.monotonic()
    if not force:
        with _health_cache_lock:
            if _health_cache is not None and (now - _health_cache_checked_at) < _HEALTH_CACHE_TTL:
                return _health_cache

    deps = [
        check_postgres(),
        check_redis(),
        check_queue(),
        check_mongo(),
        check_schema(),
        check_ai_providers(),
    ]

    degraded_domains = get_degraded_domains()
    critical_down = any(dep.status == "unavailable" and dep.critical for dep in deps)
    any_degraded = bool(degraded_domains) or any(
        dep.status in ("unavailable", "degraded") for dep in deps
    )

    if critical_down:
        tier = "critical"
        http_status = 503
    elif any_degraded:
        tier = "degraded"
        http_status = 200
    else:
        tier = "healthy"
        http_status = 200

    try:
        from AINDY.platform_layer.metrics import system_health_tier

        system_health_tier.set({"healthy": 0, "degraded": 1, "critical": 2}[tier])
    except Exception:
        pass

    result = SystemHealth(tier=tier, http_status=http_status, dependencies=deps)
    with _health_cache_lock:
        _health_cache = result
        _health_cache_checked_at = now
    return result


def get_readiness_report() -> tuple[int, dict[str, Any]]:
    if settings.is_testing:
        return 200, {
            "status": "ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {"testing_mode": True},
            "required_failures": [],
            "deployment_contract": deployment_contract_summary(),
        }

    health = get_system_health(force=True)
    api_state = get_api_runtime_state()
    dependency_by_name = {dep.name: dep for dep in health.dependencies}

    checks: dict[str, Any] = {
        "startup_complete": bool(api_state.get("startup_complete")),
        "scheduler_role": api_state.get("scheduler_role", "disabled"),
        "background_enabled": bool(api_state.get("background_enabled")),
        "event_bus_ready": bool(api_state.get("event_bus_ready")),
        "degraded_domains": get_degraded_domains(),
    }

    failures: list[str] = []
    if not checks["startup_complete"]:
        failures.append("startup_incomplete")

    postgres = dependency_by_name.get("postgres")
    if postgres is not None:
        checks["postgres"] = postgres.status
        if postgres.status != "ok":
            failures.append("postgres")

    schema = dependency_by_name.get("schema")
    if schema is not None:
        checks["schema"] = schema.status
        if schema.critical and schema.status != "ok":
            failures.append("schema")

    redis = dependency_by_name.get("redis")
    if redis is not None:
        checks["redis"] = redis.status
        if redis_required() and redis.status != "ok":
            failures.append("redis")

    queue = dependency_by_name.get("queue")
    if queue is not None:
        checks["queue"] = queue.status
        checks["queue_backend"] = queue.metadata.get("backend")
        if queue_backend_required() and queue.status != "ok":
            failures.append("queue")

    if checks["background_enabled"] and checks["scheduler_role"] == "leader":
        try:
            from AINDY.platform_layer import scheduler_service

            scheduler = scheduler_service.get_scheduler()
            checks["scheduler"] = "ok" if getattr(scheduler, "running", False) else "not_running"
        except Exception as exc:
            checks["scheduler"] = "not_running"
            checks["scheduler_detail"] = str(exc)
        if checks["scheduler"] != "ok":
            failures.append("scheduler")
    else:
        checks["scheduler"] = checks["scheduler_role"]

    if event_bus_required():
        if not checks["event_bus_ready"]:
            failures.append("event_bus")

    if worker_required():
        worker = _check_worker_heartbeat()
        checks["worker"] = worker["status"]
        if worker.get("detail"):
            checks["worker_detail"] = worker["detail"]
        if worker["status"] != "ok":
            failures.append("worker")
    else:
        checks["worker"] = "not_required"

    status_code = 200 if not failures else 503
    return status_code, {
        "status": "ready" if not failures else "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "required_failures": failures,
        "deployment_contract": deployment_contract_summary(),
    }


def _check_worker_heartbeat() -> dict[str, str]:
    if not settings.REDIS_URL:
        return {"status": "missing", "detail": "REDIS_URL not configured"}
    try:
        import redis as _redis

        client = _redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        val = client.get("aindy:worker:heartbeat")
        if val is None:
            return {"status": "missing", "detail": "No worker heartbeat in Redis"}
        return {"status": "ok", "detail": f"last_beat={val.decode()}"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
