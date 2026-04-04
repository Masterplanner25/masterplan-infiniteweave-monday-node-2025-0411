"""
Resource Manager — A.I.N.D.Y. OS Resource Tracking and Quota Enforcement

Tracks CPU time, memory, and syscall counts per ExecutionUnit.
Enforces per-tenant and per-execution quotas.
Thread-safe; designed as a process-level singleton.

Quota defaults
--------------
  MAX_CPU_TIME_MS             30 000   (30 seconds per execution unit)
  MAX_MEMORY_BYTES           268 435 456  (256 MiB)
  MAX_SYSCALLS_PER_EXECUTION 100
  MAX_CONCURRENT_PER_TENANT  5

These can be overridden via environment variables:
  AINDY_QUOTA_CPU_MS
  AINDY_QUOTA_MEMORY_BYTES
  AINDY_QUOTA_MAX_SYSCALLS
  AINDY_QUOTA_MAX_CONCURRENT

Usage
-----
    from kernel.resource_manager import get_resource_manager

    rm = get_resource_manager()

    # Before executing:
    ok, reason = rm.can_execute(tenant_id="user-123", eu_id="eu-abc")
    if not ok:
        raise ResourceLimitError(reason)

    rm.mark_started("user-123", "eu-abc")
    try:
        ...
        rm.record_usage("eu-abc", {"cpu_time_ms": 250, "syscall_count": 3})
        ok, reason = rm.check_quota("eu-abc")
        if not ok:
            raise ResourceLimitError(reason)
    finally:
        rm.mark_completed("user-123", "eu-abc")
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Quota constants ───────────────────────────────────────────────────────────

def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


MAX_CPU_TIME_MS: int = _int_env("AINDY_QUOTA_CPU_MS", 30_000)
MAX_MEMORY_BYTES: int = _int_env("AINDY_QUOTA_MEMORY_BYTES", 256 * 1024 * 1024)
MAX_SYSCALLS_PER_EXECUTION: int = _int_env("AINDY_QUOTA_MAX_SYSCALLS", 100)
MAX_CONCURRENT_PER_TENANT: int = _int_env("AINDY_QUOTA_MAX_CONCURRENT", 5)

RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"


# ── Exceptions ────────────────────────────────────────────────────────────────

class ResourceLimitError(Exception):
    """Raised when a resource quota is exceeded during execution.

    The error message includes the RESOURCE_LIMIT_EXCEEDED code so callers
    can detect it without isinstance() checks.
    """


# ── Usage snapshot ────────────────────────────────────────────────────────────

@dataclass
class UsageSnapshot:
    """Accumulated resource usage for a single ExecutionUnit."""

    eu_id: str
    tenant_id: str
    cpu_time_ms: int = 0
    memory_bytes: int = 0
    syscall_count: int = 0

    def to_dict(self) -> dict:
        return {
            "eu_id": self.eu_id,
            "tenant_id": self.tenant_id,
            "cpu_time_ms": self.cpu_time_ms,
            "memory_bytes": self.memory_bytes,
            "syscall_count": self.syscall_count,
        }


# ── ResourceManager ───────────────────────────────────────────────────────────

class ResourceManager:
    """Thread-safe resource tracker and quota enforcer.

    Maintains in-memory usage counters for each active ExecutionUnit and
    per-tenant concurrency counts.  All methods are safe to call from
    multiple threads simultaneously.

    Lifecycle per execution unit:
        1. can_execute(tenant_id, eu_id)   → check quota before start
        2. mark_started(tenant_id, eu_id)  → increment active counter
        3. record_usage(eu_id, usage)      → accumulate usage deltas
        4. check_quota(eu_id)              → mid-execution limit check
        5. mark_completed(tenant_id, eu_id)→ decrement active counter

    Note: eu_id may be None for anonymous executions; those still
    count toward tenant concurrency but have no per-EU usage tracking.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # eu_id → UsageSnapshot
        self._usage: dict[str, UsageSnapshot] = {}
        # tenant_id → active execution count
        self._tenant_active: dict[str, int] = {}
        # eu_id → tenant_id (for cleanup on mark_completed with unknown eu_id)
        self._eu_tenant: dict[str, str] = {}

    # ── Pre-execution checks ──────────────────────────────────────────────────

    def can_execute(
        self,
        tenant_id: str,
        eu_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """Check whether an execution may start.

        Checks:
        1. Per-tenant concurrent execution limit.

        Args:
            tenant_id: Tenant (user) requesting execution.
            eu_id:     Optional ExecutionUnit ID (for logging).

        Returns:
            (True, None) if execution is allowed.
            (False, reason_str) if a quota is exceeded.
        """
        with self._lock:
            active = self._tenant_active.get(str(tenant_id), 0)
            if active >= MAX_CONCURRENT_PER_TENANT:
                reason = (
                    f"{RESOURCE_LIMIT_EXCEEDED}: tenant {tenant_id!r} has "
                    f"{active} active executions (max {MAX_CONCURRENT_PER_TENANT})"
                )
                logger.warning("[ResourceManager] %s eu=%s", reason, eu_id)
                return False, reason
        return True, None

    def check_quota(self, eu_id: str) -> tuple[bool, str | None]:
        """Check per-execution quotas for an in-progress ExecutionUnit.

        Checks:
        1. Cumulative CPU time.
        2. Syscall count.
        (Memory is tracked but not enforced here — it requires OS integration.)

        Args:
            eu_id: ExecutionUnit ID to check.

        Returns:
            (True, None) if within limits.
            (False, reason_str) if a quota is exceeded.
        """
        with self._lock:
            snap = self._usage.get(str(eu_id))
            if snap is None:
                return True, None

            if snap.cpu_time_ms > MAX_CPU_TIME_MS:
                reason = (
                    f"{RESOURCE_LIMIT_EXCEEDED}: eu {eu_id!r} exceeded "
                    f"cpu_time_ms limit ({snap.cpu_time_ms} > {MAX_CPU_TIME_MS})"
                )
                logger.warning("[ResourceManager] %s", reason)
                return False, reason

            if snap.syscall_count > MAX_SYSCALLS_PER_EXECUTION:
                reason = (
                    f"{RESOURCE_LIMIT_EXCEEDED}: eu {eu_id!r} exceeded "
                    f"syscall_count limit ({snap.syscall_count} > {MAX_SYSCALLS_PER_EXECUTION})"
                )
                logger.warning("[ResourceManager] %s", reason)
                return False, reason

        return True, None

    # ── Lifecycle hooks ───────────────────────────────────────────────────────

    def mark_started(self, tenant_id: str, eu_id: str | None = None) -> None:
        """Increment active execution counter for *tenant_id*.

        Also initialises the UsageSnapshot for *eu_id* if supplied.

        Args:
            tenant_id: The tenant starting an execution.
            eu_id:     Optional ExecutionUnit ID.
        """
        tid = str(tenant_id)
        with self._lock:
            self._tenant_active[tid] = self._tenant_active.get(tid, 0) + 1
            if eu_id:
                eid = str(eu_id)
                if eid not in self._usage:
                    self._usage[eid] = UsageSnapshot(eu_id=eid, tenant_id=tid)
                self._eu_tenant[eid] = tid

    def mark_completed(self, tenant_id: str, eu_id: str | None = None) -> None:
        """Decrement active execution counter for *tenant_id*.

        Does NOT remove the UsageSnapshot so callers can read final usage
        after completion.  The snapshot is retained in memory until
        ``purge_eu(eu_id)`` is called.

        Args:
            tenant_id: The tenant whose execution is completing.
            eu_id:     Optional ExecutionUnit ID.
        """
        tid = str(tenant_id)
        with self._lock:
            current = self._tenant_active.get(tid, 0)
            self._tenant_active[tid] = max(0, current - 1)

    # ── Usage recording ───────────────────────────────────────────────────────

    def record_usage(self, eu_id: str, usage: dict) -> None:
        """Accumulate resource usage for an ExecutionUnit.

        Deltas are ADDED to existing counters except memory_bytes which
        tracks the maximum observed value (high-water mark).

        Args:
            eu_id:  ExecutionUnit ID.
            usage:  Dict with keys: cpu_time_ms (int), memory_bytes (int),
                    syscall_count (int).  Missing keys are treated as 0.
        """
        eid = str(eu_id)
        with self._lock:
            if eid not in self._usage:
                # Anonymous usage tracking — no tenant association
                self._usage[eid] = UsageSnapshot(eu_id=eid, tenant_id="")
            snap = self._usage[eid]
            snap.cpu_time_ms += int(usage.get("cpu_time_ms", 0))
            snap.memory_bytes = max(
                snap.memory_bytes, int(usage.get("memory_bytes", 0))
            )
            snap.syscall_count += int(usage.get("syscall_count", 0))

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_usage(self, eu_id: str) -> dict:
        """Return the current UsageSnapshot for *eu_id* as a dict.

        Returns an empty usage dict if *eu_id* is unknown.
        """
        with self._lock:
            snap = self._usage.get(str(eu_id))
            if snap is None:
                return {"eu_id": eu_id, "cpu_time_ms": 0, "memory_bytes": 0, "syscall_count": 0}
            return snap.to_dict()

    def get_tenant_active(self, tenant_id: str) -> int:
        """Return the number of active executions for *tenant_id*."""
        with self._lock:
            return self._tenant_active.get(str(tenant_id), 0)

    def get_tenant_summary(self, tenant_id: str) -> dict:
        """Return a summary of resource usage for all EUs belonging to *tenant_id*.

        Aggregates across all known UsageSnapshots for the tenant.
        """
        tid = str(tenant_id)
        with self._lock:
            snaps = [s for s in self._usage.values() if s.tenant_id == tid]
            return {
                "tenant_id": tid,
                "active_executions": self._tenant_active.get(tid, 0),
                "execution_count": len(snaps),
                "total_cpu_time_ms": sum(s.cpu_time_ms for s in snaps),
                "peak_memory_bytes": max((s.memory_bytes for s in snaps), default=0),
                "total_syscalls": sum(s.syscall_count for s in snaps),
                "quota_limits": {
                    "max_cpu_time_ms": MAX_CPU_TIME_MS,
                    "max_memory_bytes": MAX_MEMORY_BYTES,
                    "max_syscalls_per_execution": MAX_SYSCALLS_PER_EXECUTION,
                    "max_concurrent_executions": MAX_CONCURRENT_PER_TENANT,
                },
            }

    def purge_eu(self, eu_id: str) -> None:
        """Remove the UsageSnapshot for *eu_id* from memory.

        Safe to call at any point after ``mark_completed()``.
        """
        with self._lock:
            self._usage.pop(str(eu_id), None)
            self._eu_tenant.pop(str(eu_id), None)

    def reset(self) -> None:
        """Clear ALL in-memory state.

        For use in tests only. Never call in production.
        """
        with self._lock:
            self._usage.clear()
            self._tenant_active.clear()
            self._eu_tenant.clear()


# ── Module-level singleton ────────────────────────────────────────────────────

_RESOURCE_MANAGER: ResourceManager | None = None
_RM_LOCK = threading.Lock()


def get_resource_manager() -> ResourceManager:
    """Return the module-level ResourceManager singleton.

    Thread-safe double-checked locking.  Use this in all production code.
    Tests should call ``ResourceManager()`` directly for isolation.
    """
    global _RESOURCE_MANAGER
    if _RESOURCE_MANAGER is None:
        with _RM_LOCK:
            if _RESOURCE_MANAGER is None:
                _RESOURCE_MANAGER = ResourceManager()
    return _RESOURCE_MANAGER
