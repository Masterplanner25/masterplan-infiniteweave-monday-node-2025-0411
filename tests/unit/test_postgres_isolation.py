from __future__ import annotations

import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from AINDY.core.execution_unit_service import ExecutionUnitService
from AINDY.db.database import Base
from AINDY.db.models.execution_unit import ExecutionUnit
from AINDY.db.models.user import User
from AINDY.kernel.syscall_dispatcher import SyscallDispatcher, SyscallContext
from apps.agent.models.agent_run import AgentRun


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.getenv("DATABASE_URL", "").startswith("postgresql"),
        reason="postgres-only test module",
    ),
]


def _build_session_factory():
    import AINDY.db.model_registry  # noqa: F401
    import AINDY.memory.memory_persistence  # noqa: F401
    import apps.bootstrap

    apps.bootstrap.bootstrap_models()

    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(bind=engine, checkfirst=True)
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=engine,
    )


def _seed_user(session_factory) -> str:
    user_id = uuid.uuid4()
    session = session_factory()
    try:
        session.add(
            User(
                id=user_id,
                email=f"{user_id}@example.com",
                hashed_password="test",
                is_active=True,
            )
        )
        session.commit()
    finally:
        session.close()
    return str(user_id)


@pytest.mark.postgres
def test_execution_units_isolated_between_users():
    engine, session_factory = _build_session_factory()
    user_a = _seed_user(session_factory)
    user_b = _seed_user(session_factory)

    start_barrier = threading.Barrier(2)
    results: dict[str, tuple[int, set[str]]] = {}
    lock = threading.Lock()

    def _worker(user_id: str):
        session = session_factory()
        try:
            start_barrier.wait()
            service = ExecutionUnitService(session)
            eu = service.create(
                eu_type="agent",
                user_id=user_id,
                source_type="test",
                source_id=str(uuid.uuid4()),
                correlation_id=str(uuid.uuid4()),
                status="pending",
                extra={},
            )
            assert eu is not None
            session.commit()
            own_rows = session.query(ExecutionUnit).filter(ExecutionUnit.user_id == uuid.UUID(user_id)).all()
            with lock:
                results[user_id] = (len(own_rows), {str(row.user_id) for row in own_rows})
        finally:
            session.close()

    threads = [
        threading.Thread(target=_worker, args=(user_a,)),
        threading.Thread(target=_worker, args=(user_b,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    verification = session_factory()
    try:
        total_count = verification.query(ExecutionUnit).count()
    finally:
        verification.close()
        engine.dispose()

    assert results[user_a][0] == 1
    assert results[user_a][1] == {user_a}
    assert results[user_b][0] == 1
    assert results[user_b][1] == {user_b}
    assert total_count == 2


@pytest.mark.postgres
def test_agent_run_fk_cascade_on_user_delete():
    engine, session_factory = _build_session_factory()
    user_id = _seed_user(session_factory)
    user_uuid = uuid.UUID(user_id)

    session = session_factory()
    try:
        session.add_all(
            [
                AgentRun(user_id=user_uuid, goal="run one", agent_type="default", status="pending_approval"),
                AgentRun(user_id=user_uuid, goal="run two", agent_type="default", status="pending_approval"),
            ]
        )
        session.commit()
        assert session.query(AgentRun).filter(AgentRun.user_id == user_uuid).count() == 2

        with pytest.raises(IntegrityError):
            session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_uuid})
            session.commit()
        session.rollback()

        remaining = session.query(AgentRun).filter(AgentRun.user_id == user_uuid).count()
        assert remaining == 2
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgres
def test_concurrent_agent_runs_same_user_no_eu_duplication():
    engine, session_factory = _build_session_factory()
    user_id = _seed_user(session_factory)
    start_barrier = threading.Barrier(2)
    source_ids: list[str] = []
    lock = threading.Lock()

    def _worker():
        session = session_factory()
        try:
            source_id = str(uuid.uuid4())
            start_barrier.wait()
            eu = ExecutionUnitService(session).create(
                eu_type="agent",
                user_id=user_id,
                source_type="agent_run",
                source_id=source_id,
                correlation_id=str(uuid.uuid4()),
                status="pending",
                extra={},
            )
            assert eu is not None
            session.commit()
            with lock:
                source_ids.append(source_id)
        finally:
            session.close()

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    verification = session_factory()
    try:
        rows = verification.query(ExecutionUnit).filter(ExecutionUnit.user_id == uuid.UUID(user_id)).all()
    finally:
        verification.close()
        engine.dispose()

    assert len(rows) == 2
    assert {row.source_id for row in rows} == set(source_ids)


@pytest.mark.postgres
def test_syscall_quota_enforced_under_concurrent_load():
    counter = {"value": 0}
    guard = threading.Lock()
    barrier = threading.Barrier(5)
    results: list[dict] = []
    result_lock = threading.Lock()

    class _MockRM:
        def check_quota(self, execution_unit_id):
            del execution_unit_id
            with guard:
                counter["value"] += 1
                if counter["value"] == 1:
                    return True, ""
            return False, "quota_exceeded"

        def record_usage(self, execution_unit_id, usage):
            del execution_unit_id, usage
            return None

    ctx = SyscallContext(
        execution_unit_id="eu-postgres-quota",
        user_id="00000000-0000-0000-0000-000000000001",
        capabilities=["memory.read"],
        trace_id="trace-postgres-quota",
    )

    def _worker():
        from unittest.mock import patch

        barrier.wait()
        with patch("AINDY.kernel.syscall_dispatcher._get_rm", return_value=_MockRM()):
            result = SyscallDispatcher().dispatch(
                "sys.v1.memory.read",
                {"query": "quota-test", "user_id": ctx.user_id},
                ctx,
            )
        with result_lock:
            results.append(result)

    threads = [threading.Thread(target=_worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    success_count = sum(1 for result in results if result["status"] == "success")
    error_results = [result for result in results if result["status"] == "error"]

    assert success_count == 1
    assert len(error_results) == 4
    assert all("quota" in (result.get("error") or "").lower() for result in error_results)


@pytest.mark.postgres
def test_execution_unit_status_transitions_are_atomic():
    engine, session_factory = _build_session_factory()
    user_id = _seed_user(session_factory)

    seed_session = session_factory()
    try:
        eu = ExecutionUnitService(seed_session).create(
            eu_type="agent",
            user_id=user_id,
            source_type="test",
            source_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
            status="executing",
            extra={},
        )
        assert eu is not None
        seed_session.commit()
        eu_id = str(eu.id)
    finally:
        seed_session.close()

    barrier = threading.Barrier(5)

    def _worker():
        session = session_factory()
        try:
            barrier.wait()
            ExecutionUnitService(session).update_status(eu_id, "completed")
            session.commit()
        finally:
            session.close()

    threads = [threading.Thread(target=_worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    verification = session_factory()
    try:
        row = verification.query(ExecutionUnit).filter(ExecutionUnit.id == uuid.UUID(eu_id)).one()
    finally:
        verification.close()
        engine.dispose()

    assert row is not None
    assert row.status == "completed"
