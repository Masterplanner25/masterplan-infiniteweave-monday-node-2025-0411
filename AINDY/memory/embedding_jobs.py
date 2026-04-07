from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from core.execution_signal_helper import queue_system_event
from db.database import SessionLocal
from core.execution_dispatcher import dispatch_job
from platform_layer.async_job_service import register_async_job
from memory.embedding_service import generate_embedding
from core.system_event_service import emit_error_event
from core.system_event_types import SystemEventTypes

logger = logging.getLogger(__name__)

EMBEDDING_JOB_NAME = "memory.generate_embedding"
EMBEDDING_RETRY_DELAYS = (1, 2, 4)


def enqueue_embedding(memory_id: str, *, user_id: str | None = None, trace_id: str | None = None) -> str:
    result = dispatch_job(
        task_name=EMBEDDING_JOB_NAME,
        payload={
            "memory_id": memory_id,
            "trace_id": trace_id or memory_id,
            "user_id": user_id,
        },
        user_id=user_id,
        source="memory",
        max_attempts=1,
        execute_inline_in_test_mode=False,
    )
    return result.meta["log_id"]


def _set_embedding_status(db, memory_node, status: str, embedding: list[float] | None = None) -> None:
    memory_node.embedding_status = status
    if embedding is not None:
        memory_node.embedding = embedding
    db.add(memory_node)
    db.commit()
    db.refresh(memory_node)


@register_async_job(EMBEDDING_JOB_NAME)
def process_embedding_job(payload: dict[str, Any], db):
    from memory.memory_persistence import MemoryNodeModel

    memory_node = (
        db.query(MemoryNodeModel)
        .filter(MemoryNodeModel.id == uuid.UUID(str(payload["memory_id"])))
        .first()
    )
    if not memory_node:
        raise RuntimeError(f"Memory node {payload['memory_id']} not found")

    trace_id = payload.get("trace_id") or (memory_node.extra or {}).get("trace_id") or str(memory_node.id)
    parent_event_id = str(memory_node.source_event_id) if memory_node.source_event_id else None

    started_event_id = queue_system_event(
        db=db,
        event_type=SystemEventTypes.EMBEDDING_STARTED,
        user_id=memory_node.user_id,
        trace_id=trace_id,
        parent_event_id=parent_event_id,
        source="memory",
        payload={"memory_id": str(memory_node.id)},
        required=True,
    )

    for attempt, delay_seconds in enumerate(EMBEDDING_RETRY_DELAYS, start=1):
        try:
            _set_embedding_status(db, memory_node, "pending")
            embedding = generate_embedding(memory_node.content)
            if not embedding or not any(float(value) != 0.0 for value in embedding):
                raise RuntimeError("Embedding generation returned an empty or zero vector")

            _set_embedding_status(db, memory_node, "complete", embedding=embedding)
            queue_system_event(
                db=db,
                event_type=SystemEventTypes.EMBEDDING_COMPLETED,
                user_id=memory_node.user_id,
                trace_id=trace_id,
                parent_event_id=str(started_event_id) if started_event_id else parent_event_id,
                source="memory",
                payload={
                    "memory_id": str(memory_node.id),
                    "attempt": attempt,
                    "dimensions": len(embedding),
                },
                required=True,
            )
            return {
                "memory_id": str(memory_node.id),
                "embedding_status": memory_node.embedding_status,
                "attempt": attempt,
            }
        except Exception as exc:
            logger.warning("[EmbeddingJobs] embedding attempt %s failed for %s: %s", attempt, memory_node.id, exc)
            if attempt == len(EMBEDDING_RETRY_DELAYS):
                _set_embedding_status(db, memory_node, "failed")
                queue_system_event(
                    db=db,
                    event_type=SystemEventTypes.EMBEDDING_FAILED,
                    user_id=memory_node.user_id,
                    trace_id=trace_id,
                    parent_event_id=str(started_event_id) if started_event_id else parent_event_id,
                    source="memory",
                    payload={
                        "memory_id": str(memory_node.id),
                        "attempt": attempt,
                        "error": str(exc),
                    },
                    required=True,
                )
                emit_error_event(
                    db=db,
                    error_type="embedding_job",
                    message=str(exc),
                    user_id=memory_node.user_id,
                    trace_id=trace_id,
                    parent_event_id=str(started_event_id) if started_event_id else parent_event_id,
                    source="memory",
                    payload={"memory_id": str(memory_node.id), "attempt": attempt},
                    required=True,
                )
                return {
                    "memory_id": str(memory_node.id),
                    "embedding_status": memory_node.embedding_status,
                    "attempt": attempt,
                    "error": str(exc),
                }
            time.sleep(delay_seconds)


def process_pending_embedding(memory_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        return process_embedding_job({"memory_id": memory_id, "trace_id": memory_id}, db)
    finally:
        db.close()


