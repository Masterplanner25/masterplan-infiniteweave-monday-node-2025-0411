from __future__ import annotations

import os
import threading
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from AINDY.db.models.flow_run import FlowHistory, FlowRun
from AINDY.db.models.system_state_snapshot import SystemStateSnapshot
from AINDY.memory.memory_persistence import MemoryNodeModel
from AINDY.db.models import AgentRun, AgentStep
from apps.arm.models import AnalysisResult, CodeGeneration
from tests.unit.test_postgres_isolation import _build_session_factory, _seed_user


pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.getenv("DATABASE_URL", "").startswith("postgresql"),
        reason="postgres-only test module",
    ),
]


@pytest.mark.postgres
def test_code_generation_analysis_id_set_null_on_parent_delete():
    """
    CodeGeneration.analysis_id uses ondelete="SET NULL".
    PostgreSQL must preserve the child row and null the FK when the parent
    row is deleted.
    """
    engine, session_factory = _build_session_factory()
    user_id = uuid.UUID(_seed_user(session_factory))

    session = session_factory()
    try:
        analysis = AnalysisResult(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            user_id=user_id,
            analysis_type="analyze",
            status="success",
        )
        session.add(analysis)
        session.flush()

        generation = CodeGeneration(
            id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            user_id=user_id,
            analysis_id=analysis.id,
            generation_type="generate",
        )
        session.add(generation)
        session.commit()
        generation_id = generation.id
        analysis_id = analysis.id

        session.execute(
            text("DELETE FROM analysis_results WHERE id = :analysis_id"),
            {"analysis_id": analysis_id},
        )
        session.commit()

        session.expire_all()
        row = session.get(CodeGeneration, generation_id)
        assert row is not None, "CodeGeneration row must remain after parent delete"
        assert row.analysis_id is None, (
            f"Expected analysis_id=NULL after deleting {analysis_id}, got {row.analysis_id!r}."
        )
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgres
def test_agent_step_rows_cascade_delete_with_agent_run():
    """
    AgentStep.run_id uses ondelete="CASCADE".
    PostgreSQL must remove child steps when the parent AgentRun is deleted.
    """
    engine, session_factory = _build_session_factory()
    user_id = uuid.UUID(_seed_user(session_factory))

    session = session_factory()
    try:
        run = AgentRun(
            id=uuid.uuid4(),
            user_id=user_id,
            goal="cascade test",
            status="completed",
            overall_risk="low",
            steps_total=2,
        )
        session.add(run)
        session.flush()

        session.add_all(
            [
                AgentStep(
                    id=uuid.uuid4(),
                    run_id=run.id,
                    step_index=0,
                    tool_name="task.create",
                    risk_level="low",
                    status="success",
                ),
                AgentStep(
                    id=uuid.uuid4(),
                    run_id=run.id,
                    step_index=1,
                    tool_name="task.complete",
                    risk_level="low",
                    status="success",
                ),
            ]
        )
        session.commit()

        session.execute(text("DELETE FROM agent_runs WHERE id = :run_id"), {"run_id": run.id})
        session.commit()

        remaining = session.query(AgentStep).filter(AgentStep.run_id == run.id).count()
        assert remaining == 0, f"Expected 0 AgentStep rows after cascade delete, found {remaining}."
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgres
def test_flow_history_rows_cascade_delete_with_flow_run():
    """
    FlowHistory.flow_run_id uses ondelete="CASCADE".
    PostgreSQL must remove flow-history rows when the parent FlowRun is deleted.
    """
    engine, session_factory = _build_session_factory()

    session = session_factory()
    try:
        flow_run = FlowRun(
            id=str(uuid.uuid4()),
            flow_name="cascade_flow",
            workflow_type="test",
            status="completed",
            state={"step": 1},
        )
        session.add(flow_run)
        session.flush()

        session.add_all(
            [
                FlowHistory(
                    id=str(uuid.uuid4()),
                    flow_run_id=flow_run.id,
                    node_name="start",
                    status="completed",
                    input_state={"a": 1},
                    output_patch={"ok": True},
                ),
                FlowHistory(
                    id=str(uuid.uuid4()),
                    flow_run_id=flow_run.id,
                    node_name="finish",
                    status="completed",
                    input_state={"b": 2},
                    output_patch={"done": True},
                ),
            ]
        )
        session.commit()

        session.execute(text("DELETE FROM flow_runs WHERE id = :run_id"), {"run_id": flow_run.id})
        session.commit()

        remaining = session.query(FlowHistory).filter(FlowHistory.flow_run_id == flow_run.id).count()
        assert remaining == 0, f"Expected 0 FlowHistory rows after cascade delete, found {remaining}."
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgres
def test_agent_run_plan_jsonb_round_trips_and_supports_arrow_query():
    """
    AgentRun.plan is JSONB on PostgreSQL.
    Nested dict data must round-trip correctly and JSON path extraction must work.
    """
    engine, session_factory = _build_session_factory()
    user_id = uuid.UUID(_seed_user(session_factory))

    session = session_factory()
    try:
        plan = {
            "overall_risk": "low",
            "steps": [{"tool": "task.create", "risk_level": "low"}],
            "executive_summary": "Create a task",
        }
        run = AgentRun(
            id=uuid.uuid4(),
            user_id=user_id,
            goal="jsonb plan test",
            plan=plan,
            status="completed",
            overall_risk="low",
            steps_total=1,
        )
        session.add(run)
        session.commit()
        session.expire_all()

        retrieved = session.get(AgentRun, run.id)
        assert retrieved.plan["overall_risk"] == "low"
        assert retrieved.plan["steps"][0]["tool"] == "task.create"

        rows = session.execute(
            text("SELECT id FROM agent_runs WHERE plan->>'overall_risk' = 'low'")
        ).fetchall()
        assert any(str(row[0]) == str(run.id) for row in rows), "Expected JSONB arrow query to match the row."
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgres
def test_agent_run_result_jsonb_supports_containment_query():
    """
    AgentRun.result is JSONB on PostgreSQL.
    Containment queries using @> must work against nested objects.
    """
    engine, session_factory = _build_session_factory()
    user_id = uuid.UUID(_seed_user(session_factory))

    session = session_factory()
    try:
        run = AgentRun(
            id=uuid.uuid4(),
            user_id=user_id,
            goal="jsonb result test",
            status="completed",
            overall_risk="low",
            steps_total=1,
            result={"summary": {"created": 2, "errors": 0}, "ok": True},
        )
        session.add(run)
        session.commit()
        session.expire_all()

        retrieved = session.get(AgentRun, run.id)
        assert retrieved.result["summary"]["created"] == 2
        assert retrieved.result["ok"] is True

        rows = session.execute(
            text(
                "SELECT id FROM agent_runs "
                "WHERE result @> '{\"summary\": {\"created\": 2}}'::jsonb"
            )
        ).fetchall()
        assert any(str(row[0]) == str(run.id) for row in rows), "Expected JSONB containment query to match the row."
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgres
def test_memory_node_tags_jsonb_supports_array_containment_query():
    """
    MemoryNodeModel.tags is JSONB on PostgreSQL.
    Array containment queries must work against stored tag lists.
    """
    engine, session_factory = _build_session_factory()
    user_id = uuid.UUID(_seed_user(session_factory))

    session = session_factory()
    try:
        node = MemoryNodeModel(
            id=uuid.uuid4(),
            user_id=user_id,
            content="postgres tag test",
            node_type="insight",
            memory_type="insight",
            tags=["priority:high", "channel:email"],
            extra={"source": "test"},
            path="/tests/postgres-tags",
        )
        session.add(node)
        session.commit()
        session.expire_all()

        retrieved = session.get(MemoryNodeModel, node.id)
        assert retrieved.tags == ["priority:high", "channel:email"]

        rows = session.execute(
            text("SELECT id FROM memory_nodes WHERE tags @> '[\"priority:high\"]'::jsonb")
        ).fetchall()
        assert any(str(row[0]) == str(node.id) for row in rows), "Expected JSONB array containment to match the node."
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgres
def test_system_state_snapshot_jsonb_lists_round_trip_and_query():
    """
    SystemStateSnapshot JSONB list fields must round-trip and support
    containment queries on PostgreSQL.
    """
    engine, session_factory = _build_session_factory()

    session = session_factory()
    try:
        snapshot = SystemStateSnapshot(
            active_runs=2,
            failure_rate=0.1,
            avg_execution_time=250.0,
            recent_event_count=5,
            system_load=0.3,
            dominant_event_types=["agent.completed", "task.created"],
            health_status="healthy",
            repeated_failures=0,
            spike_detected=0,
            unusual_patterns=["none"],
        )
        session.add(snapshot)
        session.commit()
        session.expire_all()

        retrieved = session.get(SystemStateSnapshot, snapshot.id)
        assert retrieved.dominant_event_types == ["agent.completed", "task.created"]
        assert retrieved.unusual_patterns == ["none"]

        rows = session.execute(
            text(
                "SELECT id FROM system_state_snapshots "
                "WHERE dominant_event_types @> '[\"agent.completed\"]'::jsonb"
            )
        ).fetchall()
        assert any(int(row[0]) == snapshot.id for row in rows), "Expected JSONB list containment query to match snapshot."
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgres
def test_agent_run_uuid_primary_key_round_trips_as_uuid():
    """
    AgentRun.id is a native PostgreSQL UUID.
    The ORM must return uuid.UUID objects, not strings.
    """
    engine, session_factory = _build_session_factory()
    user_id = uuid.UUID(_seed_user(session_factory))
    run_id = uuid.uuid4()

    session = session_factory()
    try:
        session.add(
            AgentRun(
                id=run_id,
                user_id=user_id,
                goal="uuid round trip",
                status="completed",
                overall_risk="low",
                steps_total=0,
            )
        )
        session.commit()
        session.expire_all()

        row = session.get(AgentRun, run_id)
        assert isinstance(row.id, uuid.UUID), f"Expected AgentRun.id to be uuid.UUID, got {type(row.id)!r}."
        assert row.id == run_id
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgres
def test_agent_step_uuid_foreign_key_join_resolves_correctly():
    """
    Native UUID PK/FK columns must join cleanly on PostgreSQL.
    A UUID type mismatch would break this lookup.
    """
    engine, session_factory = _build_session_factory()
    user_id = uuid.UUID(_seed_user(session_factory))

    session = session_factory()
    try:
        run = AgentRun(
            id=uuid.uuid4(),
            user_id=user_id,
            goal="uuid fk join",
            status="completed",
            overall_risk="low",
            steps_total=1,
        )
        session.add(run)
        session.flush()

        step = AgentStep(
            id=uuid.uuid4(),
            run_id=run.id,
            step_index=0,
            tool_name="task.create",
            risk_level="low",
            status="success",
        )
        session.add(step)
        session.commit()
        session.expire_all()

        rows = (
            session.query(AgentStep)
            .join(AgentRun, AgentStep.run_id == AgentRun.id)
            .filter(AgentRun.id == run.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].id == step.id
        assert isinstance(rows[0].run_id, uuid.UUID)
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgres
def test_memory_node_uuid_primary_key_lookup_preserves_uuid_type():
    """
    MemoryNodeModel.id is a native PostgreSQL UUID.
    Lookups must preserve UUID typing and equality semantics.
    """
    engine, session_factory = _build_session_factory()
    user_id = uuid.UUID(_seed_user(session_factory))
    node_id = uuid.uuid4()

    session = session_factory()
    try:
        session.add(
            MemoryNodeModel(
                id=node_id,
                user_id=user_id,
                content="uuid memory node",
                node_type="insight",
                memory_type="insight",
                tags=["uuid"],
                extra={"kind": "uuid-test"},
                path="/tests/uuid-node",
            )
        )
        session.commit()
        session.expire_all()

        row = session.get(MemoryNodeModel, node_id)
        assert isinstance(row.id, uuid.UUID), f"Expected MemoryNodeModel.id to be uuid.UUID, got {type(row.id)!r}."
        assert row.id == node_id
    finally:
        session.close()
        engine.dispose()


@pytest.mark.postgres
def test_flow_run_status_update_isolation_under_concurrent_writes():
    """
    Concurrent updates to the same FlowRun row must commit a valid final state
    under PostgreSQL MVCC without corruption or partial writes.
    """
    engine, session_factory = _build_session_factory()
    run_id = str(uuid.uuid4())

    seed = session_factory()
    try:
        seed.add(
            FlowRun(
                id=run_id,
                flow_name="concurrent_flow",
                workflow_type="test",
                status="running",
                state={"step": 0},
            )
        )
        seed.commit()
    finally:
        seed.close()

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def _updater(new_status: str) -> None:
        session = session_factory()
        try:
            barrier.wait()
            row = session.get(FlowRun, run_id)
            row.status = new_status
            session.commit()
            with lock:
                results.append(new_status)
        except Exception as exc:
            with lock:
                results.append(f"error:{exc}")
        finally:
            session.close()

    threads = [
        threading.Thread(target=_updater, args=("completed",)),
        threading.Thread(target=_updater, args=("failed",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    verify = session_factory()
    try:
        final = verify.get(FlowRun, run_id)
        assert final.status in {"completed", "failed"}, f"Unexpected final FlowRun status: {final.status!r}"
        assert len([value for value in results if not value.startswith("error:")]) >= 1
    finally:
        verify.close()
        engine.dispose()


@pytest.mark.postgres
def test_memory_node_primary_key_uniqueness_enforced_concurrently():
    """
    Concurrent inserts using the same MemoryNodeModel UUID must result in
    exactly one committed row on PostgreSQL.
    """
    engine, session_factory = _build_session_factory()
    user_id = uuid.UUID(_seed_user(session_factory))
    node_id = uuid.uuid4()

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def _insert() -> None:
        session = session_factory()
        try:
            barrier.wait()
            session.add(
                MemoryNodeModel(
                    id=node_id,
                    user_id=user_id,
                    content="concurrent insert",
                    node_type="insight",
                    memory_type="insight",
                    tags=["concurrent"],
                    extra={"test": True},
                    path=f"/tests/{node_id}",
                )
            )
            session.commit()
            with lock:
                results.append("success")
        except IntegrityError:
            session.rollback()
            with lock:
                results.append("integrity_error")
        except Exception as exc:
            with lock:
                results.append(f"error:{exc}")
        finally:
            session.close()

    threads = [threading.Thread(target=_insert) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    verify = session_factory()
    try:
        count = verify.query(MemoryNodeModel).filter(MemoryNodeModel.id == node_id).count()
        assert results.count("success") == 1, f"Expected exactly one successful insert, got {results!r}."
        assert "integrity_error" in results, f"Expected one integrity_error result, got {results!r}."
        assert count == 1, f"Expected exactly one persisted row for {node_id}, found {count}."
    finally:
        verify.close()
        engine.dispose()
