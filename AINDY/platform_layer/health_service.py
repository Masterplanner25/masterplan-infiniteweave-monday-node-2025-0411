from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from AINDY.config import settings

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
        return {
            "status": self.tier,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": settings.VERSION,
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
            critical=False,
        ) if settings.REDIS_URL else DependencyStatus(
            name="redis",
            status="degraded",
            detail="REDIS_URL not configured (single-instance mode)",
            critical=False,
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
                critical=False,
            ) if settings.REDIS_URL else DependencyStatus(
                name="redis",
                status="degraded",
                detail="REDIS_URL not configured (single-instance mode)",
                critical=False,
            )

        if not settings.REDIS_URL:
            status = DependencyStatus(
                name="redis",
                status="degraded",
                detail="REDIS_URL not configured (single-instance mode)",
                critical=False,
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
                critical=False,
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
                critical=False,
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
            critical=False,
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
            critical=False,
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

        from AINDY.db.mongo_setup import ensure_mongo_ready

        original_timeout = settings.MONGO_HEALTH_TIMEOUT_MS
        try:
            settings.MONGO_HEALTH_TIMEOUT_MS = max(1, int(timeout * 1000))
            ensure_mongo_ready(required=True)
        finally:
            settings.MONGO_HEALTH_TIMEOUT_MS = original_timeout

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
    ]

    critical_down = any(dep.status == "unavailable" and dep.critical for dep in deps)
    any_degraded = any(dep.status in ("unavailable", "degraded") for dep in deps)

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
