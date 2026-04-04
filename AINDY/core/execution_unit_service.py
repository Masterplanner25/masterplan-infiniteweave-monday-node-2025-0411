"""
ExecutionUnitService — create, update, and query ExecutionUnit records.

All DB-touching methods are non-fatal: exceptions are caught and logged so
that EU failures never break the surrounding Task / AgentRun / FlowRun operation.

Status machine
--------------
  pending → executing → waiting → completed
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
    "pending": {"executing", "failed"},
    "executing": {"waiting", "completed", "failed"},
    "waiting": {"executing", "failed"},
    "completed": set(),
    "failed": set(),
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
        from db.models.execution_unit import ExecutionUnit

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
        from db.models.execution_unit import ExecutionUnit

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

    # ── Link helpers ──────────────────────────────────────────────────────────

    def link_flow_run(self, eu_id, flow_run_id: str) -> bool:
        from db.models.execution_unit import ExecutionUnit

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
        from db.models.execution_unit import ExecutionUnit

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
        from db.models.execution_unit import ExecutionUnit

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
        from db.models.execution_unit import ExecutionUnit

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
        from db.models.execution_unit import ExecutionUnit

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
        from db.models.execution_unit import ExecutionUnit

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
    def view_from_task(task) -> dict:
        """Return an EU-shaped dict from a Task ORM object without touching the DB."""
        return {
            "id": None,
            "type": "task",
            "status": _map_task_status(getattr(task, "status", "pending")),
            "user_id": str(task.user_id) if getattr(task, "user_id", None) else None,
            "source_type": "task",
            "source_id": str(task.id),
            "parent_id": None,
            "flow_run_id": None,
            "correlation_id": None,
            "memory_context_ids": [],
            "output_memory_ids": [],
            "extra": {
                "task_name": getattr(task, "name", None),
                "category": getattr(task, "category", None),
                "priority": getattr(task, "priority", None),
            },
            "created_at": _iso(getattr(task, "created_at", None)),
            "updated_at": _iso(getattr(task, "updated_at", None)),
            "completed_at": _iso(getattr(task, "completed_at", None)),
        }

    @staticmethod
    def view_from_agent_run(agent_run) -> dict:
        """Return an EU-shaped dict from an AgentRun ORM object without touching the DB."""
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
                "goal": getattr(agent_run, "goal", None),
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


def _map_task_status(status: str) -> str:
    return {
        "pending": "pending",
        "in_progress": "executing",
        "paused": "waiting",
        "completed": "completed",
    }.get(status, "pending")


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

