from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from sqlalchemy.orm import Session

from AINDY.config import settings
from AINDY.core.execution_signal_helper import queue_system_event
from AINDY.core.execution_dispatcher import dispatch_job
from AINDY.db.database import SessionLocal
from AINDY.core.system_event_types import SystemEventTypes
from AINDY.memory.embedding_service import generate_embedding
from AINDY.platform_layer.async_job_service import _INLINE_ACTIVE, register_async_job

logger = logging.getLogger(__name__)

EMBEDDING_JOB_NAME = "memory.generate_embedding"
EMBEDDING_SWEEP_JOB_NAME = "memory.embedding_sweep"
EMBEDDING_SWEEP_LIMIT = 25


def enqueue_embedding(
    memory_id: str,
    *,
    user_id: str | None = None,
    trace_id: str | None = None,
    db: Session | None = None,
) -> str:
    inline_mode = _INLINE_ACTIVE.get()
    env_name = os.getenv("ENV", "").lower()
    testing_flag = os.getenv("TESTING", "false").lower() in {"1", "true", "yes"}
    if settings.is_testing or env_name == "test" or testing_flag or inline_mode:
        logger.info(
            "[EmbeddingJobs] Skipping embedding job during inline/test mode (memory=%s inline=%s)",
            memory_id,
            inline_mode,
        )
        return memory_id
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
        db=db,
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
    from AINDY.memory.memory_persistence import MemoryNodeModel

    memory_node = (
        db.query(MemoryNodeModel)
        .filter(MemoryNodeModel.id == uuid.UUID(str(payload["memory_id"])))
        .first()
    )
    if not memory_node:
        logger.warning("[EmbeddingJobs] memory node %s not found", payload["memory_id"])
        return {"memory_id": str(payload["memory_id"]), "embedding_pending": True, "status": "missing"}

    trace_id = payload.get("trace_id") or (memory_node.extra or {}).get("trace_id") or str(memory_node.id)
    parent_event_id = str(memory_node.source_event_id) if memory_node.source_event_id else None

    if not getattr(memory_node, "embedding_pending", True):
        return {
            "memory_id": str(memory_node.id),
            "embedding_pending": False,
            "embedding_status": memory_node.embedding_status,
            "status": "already_processed",
        }

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

    try:
        embedding = generate_embedding(memory_node.content)
        if not embedding or not any(float(value) != 0.0 for value in embedding):
            raise RuntimeError("Embedding generation returned an empty or zero vector")

        memory_node.embedding = embedding
        memory_node.embedding_pending = False
        memory_node.embedding_status = "complete"
        db.add(memory_node)
        db.commit()
        db.refresh(memory_node)

        queue_system_event(
            db=db,
            event_type=SystemEventTypes.EMBEDDING_COMPLETED,
            user_id=memory_node.user_id,
            trace_id=trace_id,
            parent_event_id=str(started_event_id) if started_event_id else parent_event_id,
            source="memory",
            payload={
                "memory_id": str(memory_node.id),
                "dimensions": len(embedding),
            },
            required=True,
        )
        return {
            "memory_id": str(memory_node.id),
            "embedding_pending": memory_node.embedding_pending,
            "embedding_status": memory_node.embedding_status,
        }
    except Exception as exc:
        logger.warning("[EmbeddingJobs] embedding deferred for %s: %s", memory_node.id, exc)
        memory_node.embedding_pending = True
        memory_node.embedding_status = "pending"
        db.add(memory_node)
        db.commit()
        db.refresh(memory_node)
        return {
            "memory_id": str(memory_node.id),
            "embedding_pending": memory_node.embedding_pending,
            "embedding_status": memory_node.embedding_status,
            "error": str(exc),
        }


def process_pending_embeddings(*, limit: int = EMBEDDING_SWEEP_LIMIT, db: Session | None = None) -> dict[str, Any]:
    from AINDY.memory.memory_persistence import MemoryNodeModel

    owns_session = db is None
    session = db or SessionLocal()
    try:
        pending_rows = (
            session.query(MemoryNodeModel)
            .filter(MemoryNodeModel.embedding_pending.is_(True))
            .order_by(MemoryNodeModel.created_at.asc(), MemoryNodeModel.id.asc())
            .limit(max(1, int(limit)))
            .all()
        )
        processed = 0
        completed = 0
        deferred = 0
        for row in pending_rows:
            result = process_embedding_job(
                {
                    "memory_id": str(row.id),
                    "trace_id": (row.extra or {}).get("trace_id") or str(row.id),
                },
                session,
            )
            processed += 1
            if result.get("embedding_pending"):
                deferred += 1
            else:
                completed += 1
        return {
            "job": EMBEDDING_SWEEP_JOB_NAME,
            "processed": processed,
            "completed": completed,
            "deferred": deferred,
        }
    finally:
        if owns_session:
            session.close()


def process_pending_embedding(memory_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        return process_embedding_job({"memory_id": memory_id, "trace_id": memory_id}, db)
    finally:
        db.close()


