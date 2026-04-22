from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from AINDY.db.models.background_task_lease import BackgroundTaskLease


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def supports_managed_transactions(db: Session) -> bool:
    in_transaction = getattr(db, "in_transaction", None)
    if not callable(in_transaction):
        return False
    try:
        return isinstance(in_transaction(), bool)
    except Exception:
        return False


@contextmanager
def transaction_scope(db: Session):
    """Use one transaction for the logical update, without nesting commits."""
    if supports_managed_transactions(db):
        if db.in_transaction():
            yield False
            return
        with db.begin():
            yield True
        return

    try:
        yield None
        commit = getattr(db, "commit", None)
        if callable(commit):
            commit()
    except Exception:
        rollback = getattr(db, "rollback", None)
        if callable(rollback):
            rollback()
        raise


def acquire_execution_lease(
    db: Session,
    *,
    name: str,
    owner_id: str,
    ttl_seconds: int,
) -> bool:
    redis_result = _try_redis_lock(name, owner_id, ttl_seconds)
    if redis_result is not None:
        return redis_result
    return _acquire_db_lease(
        db,
        name=name,
        owner_id=owner_id,
        ttl_seconds=ttl_seconds,
    )


def _try_redis_lock(name: str, owner_id: str, ttl_seconds: int) -> bool | None:
    """
    Attempt to acquire a distributed lock via Redis SETNX.

    Returns:
        True  — lock acquired
        False — lock held by another owner
        None  — Redis unavailable or not configured (caller should fall back to DB)
    """
    try:
        from AINDY.config import settings

        if not settings.REDIS_URL:
            return None

        import redis as _redis

        client = _redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        lock_key = f"aindy:lease:{name}"
        acquired = client.set(lock_key, owner_id, nx=True, ex=ttl_seconds)
        return bool(acquired)
    except Exception:
        return None


def _release_redis_lock(name: str, owner_id: str) -> None:
    """Release a Redis lock only if this owner holds it (Lua script for atomicity)."""
    try:
        from AINDY.config import settings

        if not settings.REDIS_URL:
            return

        import redis as _redis

        client = _redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        lock_key = f"aindy:lease:{name}"
        _LUA_RELEASE = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        client.eval(_LUA_RELEASE, 1, lock_key, owner_id)
    except Exception:
        pass


def _acquire_db_lease(
    db: Session,
    *,
    name: str,
    owner_id: str,
    ttl_seconds: int,
) -> bool:
    now = utcnow()
    expires_at = now + timedelta(seconds=ttl_seconds)
    if supports_managed_transactions(db):
        lease = (
            db.execute(
                select(BackgroundTaskLease)
                .where(BackgroundTaskLease.name == name)
                .with_for_update()
            )
            .scalar_one_or_none()
        )
    else:
        lease = (
            db.query(BackgroundTaskLease)
            .filter(BackgroundTaskLease.name == name)
            .first()
        )
    if lease is not None:
        lease_expiry = lease.expires_at
        if isinstance(lease_expiry, datetime) and lease_expiry.tzinfo is None:
            lease_expiry = lease_expiry.replace(tzinfo=timezone.utc)
        if isinstance(lease_expiry, datetime) and lease_expiry > now and lease.owner_id != owner_id:
            return False
        lease.owner_id = owner_id
        lease.acquired_at = now
        lease.heartbeat_at = now
        lease.expires_at = expires_at
        db.add(lease)
        db.flush()
        return True

    try:
        with db.begin_nested():
            db.add(
                BackgroundTaskLease(
                    name=name,
                    owner_id=owner_id,
                    acquired_at=now,
                    heartbeat_at=now,
                    expires_at=expires_at,
                )
            )
            db.flush()
        return True
    except IntegrityError:
        return False


def make_execution_owner_id() -> str:
    return f"analytics-{uuid.uuid4()}"
