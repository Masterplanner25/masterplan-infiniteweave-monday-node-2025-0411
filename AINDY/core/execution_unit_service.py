"""
ExecutionUnitService — create, update, and query ExecutionUnit records.

All DB-touching methods are non-fatal: exceptions are caught and logged so
that EU failures never break the surrounding operation.

Status machine
--------------
  pending → executing → waiting → resumed → executing → completed
                                                      └→ failed
                                └→ executing  (backward compat)
                                └→ failed
                      └→ completed
                      └→ failed
  (completed and failed are terminal)
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_STATUS_TRANSITIONS: dict[str, set] = {
    "pending":   {"executing", "failed"},
    "executing": {"waiting", "resumed", "completed", "failed"},
    "waiting":   {"resumed", "executing", "failed"},  # "executing" kept for backward compat
    "resumed":   {"executing", "failed"},
    "completed": set(),
    "failed":    set(),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ExecutionUnitService:
    def __init__(self, db: Session):
        self.db = db

    # ── Create ────────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        eu_type: str,
        user_id=None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        parent_id=None,
        flow_run_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        extra: Optional[dict] = None,
        status: str = "pending",
    ):
        """
        Create and persist a new ExecutionUnit. Returns the EU on success,
        None on failure (non-fatal).
        """
        from AINDY.db.models.execution_unit import ExecutionUnit

        try:
            eu = ExecutionUnit(
                id=uuid.uuid4(),
                type=eu_type,
                status=status,
                user_id=_coerce_uuid(user_id),
                source_type=source_type,
                source_id=str(source_id) if source_id is not None else None,
                parent_id=_coerce_uuid(parent_id),
                flow_run_id=str(flow_run_id) if flow_run_id is not None else None,
                correlation_id=str(correlation_id) if correlation_id is not None else None,
                memory_context_ids=[],
                output_memory_ids=[],
                extra=extra,
                created_at=_now(),
                updated_at=_now(),
            )
            self.db.add(eu)
            self.db.flush()
            logger.debug(
                "[EU] created id=%s type=%s source=%s/%s",
                eu.id, eu_type, source_type, source_id,
            )
            return eu
        except Exception as exc:
            logger.warning("[EU] create failed — non-fatal | type=%s error=%s", eu_type, exc)
            return None

    # ── Status updates ────────────────────────────────────────────────────────

    def update_status(self, eu_id, new_status: str) -> bool:
        """
        Transition EU to new_status. Returns True on success, False otherwise.
        Validates the transition against the status machine.
        """
        from AINDY.db.models.execution_unit import ExecutionUnit

        try:
            eu = self.db.query(ExecutionUnit).filter(ExecutionUnit.id == _coerce_uuid(eu_id)).first()
            if eu is None:
                logger.debug("[EU] update_status: id=%s not found", eu_id)
                return False

            allowed = _STATUS_TRANSITIONS.get(eu.status, set())
            if new_status not in allowed:
                logger.warning(
                    "[EU] invalid transition %s→%s for id=%s", eu.status, new_status, eu_id
                )
                return False

            eu.status = new_status
            eu.updated_at = _now()
            if new_status in ("completed", "failed"):
                eu.completed_at = _now()
            self.db.flush()
            logger.debug("[EU] status %s→%s id=%s", eu.status, new_status, eu_id)
            return True
        except Exception as exc:
            logger.warning("[EU] update_status failed — non-fatal | id=%s error=%s", eu_id, exc)
            return False

    def resume_execution_unit(self, eu_id) -> bool:
        """
        Transition a waiting EU through ``resumed → executing`` and clear its
        ``wait_condition``.

        Two-step so audit queries can observe the ``resumed`` state between
        the wake signal being received and execution actually restarting.

        Idempotent: if the EU is already ``resumed``, ``executing``, or
        ``completed`` this method is a no-op and returns True so callers
        treat the skip as success.

        Returns True when both steps succeed (or when skipped as a duplicate),
        False on any failure (non-fatal).
        The caller does not need to transition to "executing" separately —
        this method does both.
        """
        from AINDY.db.models.execution_unit import ExecutionUnit

        # ── Idempotency guard ────────────────────────────────────────────────
        # Two callbacks are registered per flow WAIT (runner.resume + this one).
        # If the scheduler fires both, the second call must not re-emit events
        # or attempt an invalid status transition.
        _ALREADY_RESUMED = {"resumed", "executing", "completed"}
        try:
            _eu_check = self.db.query(ExecutionUnit).filter(
                ExecutionUnit.id == _coerce_uuid(eu_id)
            ).first()
            if _eu_check is not None and _eu_check.status in _ALREADY_RESUMED:
                logger.debug(
                    "[EU] resume_execution_unit: skipped duplicate resume id=%s status=%s",
                    eu_id, _eu_check.status,
                )
                return True
        except Exception as exc:
            logger.debug("[EU] resume_execution_unit: idempotency pre-check failed (continuing): %s", exc)
        # ── Normal path ──────────────────────────────────────────────────────

        ok = self.update_status(eu_id, "resumed")
        if not ok:
            logger.warning("[EU] resume_execution_unit: waiting→resumed failed id=%s", eu_id)
            return False
        # Clear wait_condition — the EU is no longer suspended.
        try:
            eu = self.db.query(ExecutionUnit).filter(
                ExecutionUnit.id == _coerce_uuid(eu_id)
            ).first()
            if eu is not None and eu.wait_condition is not None:
                eu.wait_condition = None
                eu.updated_at = _now()
                self.db.flush()
        except Exception as exc:
            logger.debug("[EU] clear wait_condition on resume failed (non-fatal): %s", exc)
        return self.update_status(eu_id, "executing")

    def set_wait_condition(self, eu_id, condition) -> bool:
        """
        Persist a ``WaitCondition`` on the EU when it enters ``"waiting"`` status.

        ``condition`` is accepted as a ``WaitCondition`` instance or a plain dict
        (already serialised).  Pass ``None`` to clear.  Non-fatal.
        """
        from AINDY.db.models.execution_unit import ExecutionUnit

        try:
            eu = self.db.query(ExecutionUnit).filter(
                ExecutionUnit.id == _coerce_uuid(eu_id)
            ).first()
            if eu is None:
                return False
            if condition is None:
                eu.wait_condition = None
            elif isinstance(condition, dict):
                eu.wait_condition = condition
            else:
                # WaitCondition instance — call to_dict() without hard import
                eu.wait_condition = condition.to_dict()
            eu.updated_at = _now()
            self.db.flush()
            logger.debug("[EU] wait_condition set eu_id=%s type=%s",
                         eu_id, (eu.wait_condition or {}).get("type"))
            return True
        except Exception as exc:
            logger.warning("[EU] set_wait_condition failed | id=%s error=%s", eu_id, exc)
            return False

    # ── Link helpers ──────────────────────────────────────────────────────────

    def link_flow_run(self, eu_id, flow_run_id: str) -> bool:
        from AINDY.db.models.execution_unit import ExecutionUnit

        try:
            eu = self.db.query(ExecutionUnit).filter(ExecutionUnit.id == _coerce_uuid(eu_id)).first()
            if eu is None:
                return False
            eu.flow_run_id = str(flow_run_id)
            eu.updated_at = _now()
            self.db.flush()
            return True
        except Exception as exc:
            logger.warning("[EU] link_flow_run failed — non-fatal | id=%s error=%s", eu_id, exc)
            return False

    def link_memory_context(self, eu_id, memory_ids: list) -> bool:
        """Replace memory_context_ids (called once, pre-execution)."""
        from AINDY.db.models.execution_unit import ExecutionUnit

        try:
            eu = self.db.query(ExecutionUnit).filter(ExecutionUnit.id == _coerce_uuid(eu_id)).first()
            if eu is None:
                return False
            eu.memory_context_ids = [str(m) for m in memory_ids]
            eu.updated_at = _now()
            self.db.flush()
            return True
        except Exception as exc:
            logger.warning("[EU] link_memory_context failed — non-fatal | id=%s error=%s", eu_id, exc)
            return False

    def append_output_memory(self, eu_id, memory_id) -> bool:
        """Append a single memory id to output_memory_ids."""
        from AINDY.db.models.execution_unit import ExecutionUnit

        try:
            eu = self.db.query(ExecutionUnit).filter(ExecutionUnit.id == _coerce_uuid(eu_id)).first()
            if eu is None:
                return False
            current = list(eu.output_memory_ids or [])
            mid = str(memory_id)
            if mid not in current:
                current.append(mid)
            eu.output_memory_ids = current
            eu.updated_at = _now()
            self.db.flush()
            return True
        except Exception as exc:
            logger.warning("[EU] append_output_memory failed — non-fatal | id=%s error=%s", eu_id, exc)
            return False

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_by_source(self, source_type: str, source_id: str):
        from AINDY.db.models.execution_unit import ExecutionUnit

        try:
            return (
                self.db.query(ExecutionUnit)
                .filter(
                    ExecutionUnit.source_type == source_type,
                    ExecutionUnit.source_id == str(source_id),
                )
                .order_by(ExecutionUnit.created_at.desc())
                .first()
            )
        except Exception as exc:
            logger.warning("[EU] get_by_source failed | source=%s/%s error=%s", source_type, source_id, exc)
            return None

    def get_by_correlation(self, correlation_id: str) -> list:
        from AINDY.db.models.execution_unit import ExecutionUnit

        try:
            return (
                self.db.query(ExecutionUnit)
                .filter(ExecutionUnit.correlation_id == str(correlation_id))
                .order_by(ExecutionUnit.created_at.asc())
                .all()
            )
        except Exception as exc:
            logger.warning("[EU] get_by_correlation failed | cid=%s error=%s", correlation_id, exc)
            return []

    def get_children(self, parent_eu_id) -> list:
        from AINDY.db.models.execution_unit import ExecutionUnit

        try:
            return (
                self.db.query(ExecutionUnit)
                .filter(ExecutionUnit.parent_id == _coerce_uuid(parent_eu_id))
                .order_by(ExecutionUnit.created_at.asc())
                .all()
            )
        except Exception as exc:
            logger.warning("[EU] get_children failed | parent=%s error=%s", parent_eu_id, exc)
            return []

    # ── View-only mappers (no DB required) ────────────────────────────────────

    @staticmethod
    def view_from_entity(entity_type: str, entity) -> dict:
        """Return an EU-shaped dict using an app-registered entity adapter."""
        from AINDY.platform_layer.registry import get_execution_adapter

        adapter = get_execution_adapter(entity_type)
        if adapter is None:
            raise ValueError(f"No execution adapter registered for {entity_type!r}")
        return adapter(entity)

    @staticmethod
    def view_from_agent_run(agent_run) -> dict:
        """Return an EU-shaped dict from an AgentRun ORM object without touching the DB."""
        objective = getattr(agent_run, "objective", None)
        return {
            "id": None,
            "type": "agent",
            "status": _map_agent_status(getattr(agent_run, "status", "pending")),
            "user_id": str(agent_run.user_id) if getattr(agent_run, "user_id", None) else None,
            "source_type": "agent_run",
            "source_id": str(agent_run.id),
            "parent_id": None,
            "flow_run_id": str(agent_run.flow_run_id) if getattr(agent_run, "flow_run_id", None) else None,
            "correlation_id": str(agent_run.correlation_id) if getattr(agent_run, "correlation_id", None) else None,
            "memory_context_ids": [],
            "output_memory_ids": [],
            "extra": {
                "objective": objective,
                "trace_id": str(agent_run.trace_id) if getattr(agent_run, "trace_id", None) else None,
            },
            "created_at": _iso(getattr(agent_run, "created_at", None)),
            "updated_at": _iso(getattr(agent_run, "updated_at", None)),
            "completed_at": _iso(getattr(agent_run, "completed_at", None)),
        }

    @staticmethod
    def view_from_flow_run(flow_run) -> dict:
        """Return an EU-shaped dict from a FlowRun ORM object without touching the DB."""
        return {
            "id": None,
            "type": "flow",
            "status": _map_flow_status(getattr(flow_run, "status", "pending")),
            "user_id": str(flow_run.user_id) if getattr(flow_run, "user_id", None) else None,
            "source_type": "flow_run",
            "source_id": str(flow_run.id),
            "parent_id": None,
            "flow_run_id": str(flow_run.id),
            "correlation_id": None,
            "memory_context_ids": [],
            "output_memory_ids": [],
            "extra": {
                "flow_name": getattr(flow_run, "flow_name", None),
                "workflow_type": getattr(flow_run, "workflow_type", None),
            },
            "created_at": _iso(getattr(flow_run, "created_at", None)),
            "updated_at": _iso(getattr(flow_run, "updated_at", None)),
            "completed_at": _iso(getattr(flow_run, "completed_at", None)),
        }

    @staticmethod
    def view_from_job_log(log) -> dict:
        """Return an EU-shaped dict from a JobLog ORM object without touching the DB."""
        return {
            "id": None,
            "type": "job",
            "status": _map_job_status(getattr(log, "status", "pending")),
            "user_id": str(log.user_id) if getattr(log, "user_id", None) else None,
            "source_type": "job_log",
            "source_id": str(log.id),
            "parent_id": None,
            "flow_run_id": None,
            "correlation_id": str(log.trace_id) if getattr(log, "trace_id", None) else str(log.id),
            "memory_context_ids": [],
            "output_memory_ids": [],
            "extra": {
                "task_name": getattr(log, "task_name", None),
                "job_name": getattr(log, "job_name", None),
                "source": getattr(log, "source", None),
                "attempt_count": getattr(log, "attempt_count", None),
                "max_attempts": getattr(log, "max_attempts", None),
            },
            "created_at": _iso(getattr(log, "created_at", None)),
            "updated_at": _iso(getattr(log, "updated_at", None)),
            "completed_at": _iso(getattr(log, "completed_at", None)),
        }

    # ── Serializer ────────────────────────────────────────────────────────────

    @staticmethod
    def to_dict(eu) -> dict:
        return {
            "id": str(eu.id) if eu.id else None,
            "type": eu.type,
            "status": eu.status,
            "user_id": str(eu.user_id) if eu.user_id else None,
            "source_type": eu.source_type,
            "source_id": eu.source_id,
            "parent_id": str(eu.parent_id) if eu.parent_id else None,
            "flow_run_id": eu.flow_run_id,
            "correlation_id": eu.correlation_id,
            "memory_context_ids": eu.memory_context_ids or [],
            "output_memory_ids": eu.output_memory_ids or [],
            "extra": eu.extra,
            "created_at": _iso(eu.created_at),
            "updated_at": _iso(eu.updated_at),
            "completed_at": _iso(eu.completed_at),
        }


# ── Private helpers ───────────────────────────────────────────────────────────

def _coerce_uuid(value):
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


def _iso(dt) -> Optional[str]:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _map_agent_status(status: str) -> str:
    return {
        "pending_approval": "pending",
        "approved": "pending",
        "executing": "executing",
        "completed": "completed",
        "failed": "failed",
        "rejected": "failed",
    }.get(status, "pending")


def _map_flow_status(status: str) -> str:
    return {
        "running": "executing",
        "waiting": "waiting",
        "success": "completed",
        "failed": "failed",
    }.get(status, "pending")


def _map_job_status(status: str) -> str:
    return {
        "pending": "pending",
        "queued": "pending",
        "deferred": "pending",
        "ignored": "pending",
        "running": "executing",
        "success": "completed",
        "completed": "completed",
        "failed": "failed",
        "error": "failed",
    }.get(status, "pending")

