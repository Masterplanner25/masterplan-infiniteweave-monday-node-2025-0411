from __future__ import annotations

import uuid

from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
from AINDY.db.models.user import User
from AINDY.memory.embedding_jobs import process_embedding_job
from AINDY.memory.embedding_service import EmbeddingFailedError
from AINDY.memory.memory_persistence import MemoryNodeModel
from AINDY.memory.memory_scoring_service import score_memory
from AINDY.runtime.memory import MemoryOrchestrator


def _create_user(session, *, email: str) -> User:
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        hashed_password="test",
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_embedding_failure_keeps_raw_memory_and_remains_pending(pg_db_session, monkeypatch):
    session = pg_db_session()
    user = _create_user(session, email="embedding-failure@example.com")
    dao = MemoryNodeDAO(session)

    created = dao.save(
        content="raw memory survives failed embedding",
        source="pytest",
        tags=["memory", "failure"],
        user_id=str(user.id),
        node_type="insight",
        generate_embedding=False,
    )

    monkeypatch.setattr(
        "AINDY.memory.embedding_jobs.generate_embedding",
        lambda text: (_ for _ in ()).throw(EmbeddingFailedError("embedding offline")),
    )

    result = process_embedding_job({"memory_id": created["id"], "trace_id": "trace-failed"}, session)

    node = session.query(MemoryNodeModel).filter(MemoryNodeModel.id == uuid.UUID(created["id"])).one()

    assert result["embedding_pending"] is True
    assert result["embedding_status"] == "pending"
    assert node.content == "raw memory survives failed embedding"
    assert node.embedding is None
    assert node.embedding_pending is True
    assert node.embedding_status == "pending"


def test_ingest_embed_retrieve_and_score_uses_embeddings(pg_db_session, monkeypatch):
    session = pg_db_session()
    user = _create_user(session, email="embedding-success@example.com")
    dao = MemoryNodeDAO(session)

    target = dao.save(
        content="Launch strategy for enterprise analytics rollout",
        source="pytest",
        tags=["launch"],
        user_id=str(user.id),
        node_type="insight",
        generate_embedding=False,
    )
    distractor = dao.save(
        content="Weekly grocery checklist and meal prep",
        source="pytest",
        tags=["launch"],
        user_id=str(user.id),
        node_type="insight",
        generate_embedding=False,
    )

    target_row = session.query(MemoryNodeModel).filter(MemoryNodeModel.id == uuid.UUID(target["id"])).one()
    distractor_row = session.query(MemoryNodeModel).filter(MemoryNodeModel.id == uuid.UUID(distractor["id"])).one()
    target_row.embedding = [1.0] + [0.0] * 1535
    target_row.embedding_pending = False
    target_row.embedding_status = "complete"
    target_row.impact_score = 4.0
    target_row.usage_count = 6
    distractor_row.embedding = [0.0, 1.0] + [0.0] * 1534
    distractor_row.embedding_pending = False
    distractor_row.embedding_status = "complete"
    distractor_row.impact_score = 0.5
    session.commit()

    monkeypatch.setattr(
        "AINDY.memory.embedding_service.generate_query_embedding",
        lambda query: [1.0] + [0.0] * 1535,
    )

    orchestrator = MemoryOrchestrator(MemoryNodeDAO)
    context = orchestrator.get_context(
        user_id=str(user.id),
        query="analytics launch rollout",
        db=session,
        operation_type="analysis",
        metadata={"limit": 2},
    )

    assert context.items
    assert context.items[0].id == target["id"]
    assert context.items[0].similarity > context.items[1].similarity
    assert context.items[0].score > 0

    scored = score_memory(
        {
            "impact_score": target_row.impact_score,
            "usage_count": target_row.usage_count,
            "memory_type": target_row.memory_type,
            "created_at": target_row.created_at.isoformat(),
            "extra": {},
        }
    )
    assert scored > 0
