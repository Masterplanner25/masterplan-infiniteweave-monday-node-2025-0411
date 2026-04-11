"""
db/models/nodus_trace_event.py — Per-step trace records for Nodus execution.

Each row captures one host-function call made during a Nodus script run —
e.g. recall(), remember(), emit(), set_state().  Rows are written in bulk
after the execution completes via _flush_nodus_traces() in
nodus_runtime_adapter.py.

Queried by:
  GET /platform/nodus/trace/{trace_id}

Design notes
============
* ``execution_unit_id`` and ``trace_id`` are both String(128) — they hold the
  same value in most executions (the flow-engine's execution_unit_id is used
  as the trace_id for all events emitted during that run).
* ``sequence`` preserves the call order within a single execution so the
  trace can be replayed or displayed as an ordered timeline.
* ``args_summary`` / ``result_summary`` are sanitised JSON blobs — large
  strings are truncated to 200 chars and dict/list shapes are summarised
  so the table never stores raw PII or bulky payloads.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from AINDY.db.database import Base


class NodusTraceEvent(Base):
    __tablename__ = "nodus_trace_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Correlates to the flow-engine execution / PersistentFlowRunner run
    execution_unit_id = Column(String(128), nullable=False, index=True)

    # Same value as execution_unit_id in standard runs — indexed separately
    # to allow future cross-execution trace correlation
    trace_id = Column(String(128), nullable=False, index=True)

    # Call order within this execution (1-based)
    sequence = Column(Integer, nullable=False, default=0)

    # Which host function was called (e.g. "recall", "remember", "emit")
    fn_name = Column(String(64), nullable=False)

    # Sanitised call arguments (truncated strings, summarised containers)
    args_summary = Column(JSON, nullable=True)

    # Sanitised return value
    result_summary = Column(JSON, nullable=True)

    # Wall-clock duration of the host function call in milliseconds
    duration_ms = Column(Integer, nullable=True)

    # "ok" | "error"
    status = Column(String(16), nullable=False, default="ok")

    # Error message when status == "error"
    error = Column(Text, nullable=True)

    # Script owner — used for ownership checks in the trace query endpoint
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # UTC wall-clock time of the call
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
