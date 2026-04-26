from __future__ import annotations

import uuid

from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
from AINDY.memory.embedding_jobs import process_pending_embeddings
from AINDY.memory.memory_persistence import MemoryNodeModel


def test_memory_write_succeeds_with_deferred_embedding_when_openai_would_fail(
    db_session,
    test_user,
    monkeypatch,
):
    dao = MemoryNodeDAO(db_session)
    monkeypatch.setattr(
        "AINDY.memory.embedding_service.generate_embedding",
        lambda text: (_ for _ in ()).throw(RuntimeError("openai unavailable")),
    )

    created = dao.save(
        content="Memory write should not block on OpenAI",
        source="pytest",
        tags=["async", "pending"],
        user_id=str(test_user.id),
        node_type="insight",
    )

    node = db_session.query(MemoryNodeModel).filter(
        MemoryNodeModel.id == uuid.UUID(created["id"])
    ).one()

    assert created["embedding_pending"] is True
    assert created["embedding_status"] == "pending"
    assert node.embedding is None
    assert node.embedding_pending is True
    assert node.embedding_status == "pending"


def test_embedding_worker_marks_nodes_complete_after_success(
    db_session,
    test_user,
    monkeypatch,
):
    dao = MemoryNodeDAO(db_session)
    created = dao.save(
        content="Background embedding success",
        source="pytest",
        tags=["worker"],
        user_id=str(test_user.id),
        node_type="insight",
        generate_embedding=False,
    )
    monkeypatch.setattr(
        "AINDY.memory.embedding_jobs.generate_embedding",
        lambda text: [0.4] * 1536,
    )

    result = process_pending_embeddings(db=db_session, limit=100000)
    node = db_session.query(MemoryNodeModel).filter(
        MemoryNodeModel.id == uuid.UUID(created["id"])
    ).one()

    assert result["processed"] >= 1
    assert result["completed"] >= 1
    assert node.embedding_pending is False
    assert node.embedding_status == "complete"
    assert node.embedding is not None


def test_embedding_worker_leaves_nodes_pending_when_openai_fails(
    db_session,
    test_user,
    monkeypatch,
):
    dao = MemoryNodeDAO(db_session)
    created = dao.save(
        content="Background embedding deferred",
        source="pytest",
        tags=["worker", "retry"],
        user_id=str(test_user.id),
        node_type="insight",
        generate_embedding=False,
    )
    monkeypatch.setattr(
        "AINDY.memory.embedding_jobs.generate_embedding",
        lambda text: (_ for _ in ()).throw(RuntimeError("openai timeout")),
    )

    result = process_pending_embeddings(db=db_session, limit=100000)
    node = db_session.query(MemoryNodeModel).filter(
        MemoryNodeModel.id == uuid.UUID(created["id"])
    ).one()

    assert result["processed"] >= 1
    assert result["deferred"] >= 1
    assert node.embedding is None
    assert node.embedding_pending is True
    assert node.embedding_status == "pending"


def test_similarity_search_excludes_pending_nodes(db_session, test_user):
    dao = MemoryNodeDAO(db_session)

    complete = dao.save(
        content="Complete embedding node",
        source="pytest",
        tags=["search"],
        user_id=str(test_user.id),
        node_type="insight",
        generate_embedding=False,
    )
    pending = dao.save(
        content="Pending embedding node",
        source="pytest",
        tags=["search"],
        user_id=str(test_user.id),
        node_type="insight",
        generate_embedding=False,
    )

    complete_row = db_session.query(MemoryNodeModel).filter(
        MemoryNodeModel.id == uuid.UUID(complete["id"])
    ).one()
    pending_row = db_session.query(MemoryNodeModel).filter(
        MemoryNodeModel.id == uuid.UUID(pending["id"])
    ).one()

    complete_row.embedding = [1.0] + [0.0] * 1535
    complete_row.embedding_pending = False
    complete_row.embedding_status = "complete"
    pending_row.embedding = [1.0] + [0.0] * 1535
    pending_row.embedding_pending = True
    pending_row.embedding_status = "pending"
    db_session.commit()

    results = dao.find_similar(
        query_embedding=[1.0] + [0.0] * 1535,
        limit=5,
        user_id=str(test_user.id),
    )

    assert [item["id"] for item in results] == [complete["id"]]
