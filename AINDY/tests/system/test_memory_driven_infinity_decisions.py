from __future__ import annotations

import uuid

from AINDY.core.execution_signal_helper import queue_system_event
from AINDY.core.system_event_types import SystemEventTypes
from AINDY.db.models.system_event import SystemEvent
from AINDY.db.models.task import Task
from AINDY.domain.infinity_orchestrator import execute
from AINDY.domain.rippletrace_service import build_trace_graph
from AINDY.memory.memory_persistence import MemoryNodeModel


def _stable_score() -> dict:
    return {
        "master_score": 62.0,
        "kpis": {
            "execution_speed": 62.0,
            "decision_efficiency": 61.0,
            "ai_productivity_boost": 63.0,
            "focus_quality": 60.0,
            "masterplan_progress": 64.0,
        },
        "metadata": {"confidence": "medium"},
    }


def _create_ready_task(db_session, test_user, name: str) -> Task:
    task = Task(
        name=name,
        category="system",
        priority="high",
        status="pending",
        depends_on=[],
        dependency_type="hard",
        user_id=test_user.id,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def _emit_trace(db_session, test_user, *, task_name: str, final_event_type: str) -> tuple[str, uuid.UUID]:
    trace_id = str(uuid.uuid4())
    started_event_id = queue_system_event(
        db=db_session,
        event_type=SystemEventTypes.EXECUTION_STARTED,
        user_id=test_user.id,
        trace_id=trace_id,
        source="flow",
        payload={
            "message": f"Started {task_name}",
            "task_name": task_name,
            "workflow_type": "task_completed",
        },
        required=True,
    )
    final_event_id = queue_system_event(
        db=db_session,
        event_type=final_event_type,
        user_id=test_user.id,
        trace_id=trace_id,
        parent_event_id=started_event_id,
        source="flow",
        payload={
            "message": f"{task_name} finished with {final_event_type}",
            "task_name": task_name,
            "workflow_type": "task_completed",
        },
        required=True,
    )
    return trace_id, final_event_id


def _prime_memory_weight(db_session, source_event_id: uuid.UUID, *, expected_type: str, impact_score: float, usage_count: int):
    memory_node = (
        db_session.query(MemoryNodeModel)
        .filter(MemoryNodeModel.source_event_id == source_event_id)
        .order_by(MemoryNodeModel.created_at.desc())
        .first()
    )
    assert memory_node is not None
    assert memory_node.memory_type == expected_type
    memory_node.impact_score = impact_score
    memory_node.usage_count = usage_count
    db_session.add(memory_node)
    db_session.commit()
    db_session.refresh(memory_node)
    return memory_node


def _patch_orchestrator_dependencies(monkeypatch, task_name: str):
    monkeypatch.setattr("AINDY.domain.infinity_orchestrator.get_recent_memory", lambda *args, **kwargs: [])
    monkeypatch.setattr("AINDY.domain.infinity_orchestrator.get_user_metrics", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        "AINDY.domain.infinity_orchestrator.compute_current_state",
        lambda db: {"health_status": "healthy", "failure_rate": 0.0, "system_load": 0.1},
    )
    monkeypatch.setattr("AINDY.domain.infinity_orchestrator.rank_goals", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "AINDY.domain.infinity_orchestrator.get_task_graph_context",
        lambda db, user_id: {"ready": [{"task_name": task_name}], "blocked": [], "critical_path": []},
    )
    monkeypatch.setattr("AINDY.domain.infinity_orchestrator.get_social_performance_signals", lambda *args, **kwargs: [])
    monkeypatch.setattr("AINDY.domain.infinity_orchestrator.calculate_infinity_score", lambda **kwargs: _stable_score())
    monkeypatch.setattr("AINDY.domain.infinity_orchestrator.get_current_trace_id", lambda: "trace-memory-driven")


def test_failure_memory_changes_orchestrator_decision(db_session, test_user, monkeypatch):
    task = _create_ready_task(db_session, test_user, "Recover failed deployment")
    trace_id, failed_event_id = _emit_trace(
        db_session,
        test_user,
        task_name=task.name,
        final_event_type=SystemEventTypes.EXECUTION_FAILED,
    )
    memory_node = _prime_memory_weight(
        db_session,
        failed_event_id,
        expected_type="failure",
        impact_score=10.0,
        usage_count=6,
    )
    graph = build_trace_graph(db_session, trace_id)
    assert any(node["id"] == str(memory_node.id) and node["node_kind"] == "memory_node" for node in graph["nodes"])
    assert any(
        edge["target"] == str(memory_node.id) and edge["relationship_type"] == "stored_as_memory"
        for edge in graph["edges"]
    )

    _patch_orchestrator_dependencies(monkeypatch, task.name)

    result = execute(test_user.id, "task_completed", db_session)

    assert result["next_action"]["type"] == "review_plan"
    assert result["memory_signal_count"] >= 1
    assert result["memory_influence"]["memory_adjustment"]["reason"] == "high_impact_failures_detected"

    decision_event = (
        db_session.query(SystemEvent)
        .filter(SystemEvent.type == "loop.decision", SystemEvent.trace_id == "trace-memory-driven")
        .order_by(SystemEvent.timestamp.desc())
        .first()
    )
    assert decision_event is not None
    assert (decision_event.payload or {}).get("next_action", {}).get("type") == "review_plan"


def test_success_memory_boosts_orchestrator_path(db_session, test_user, monkeypatch):
    task = _create_ready_task(db_session, test_user, "Continue successful outbound flow")
    _, completed_event_id = _emit_trace(
        db_session,
        test_user,
        task_name=task.name,
        final_event_type=SystemEventTypes.EXECUTION_COMPLETED,
    )
    _prime_memory_weight(
        db_session,
        completed_event_id,
        expected_type="outcome",
        impact_score=8.0,
        usage_count=5,
    )

    _patch_orchestrator_dependencies(monkeypatch, task.name)

    result = execute(test_user.id, "task_completed", db_session)

    assert result["next_action"]["type"] == "continue_highest_priority_task"
    assert result["memory_signal_count"] >= 1
    assert result["memory_influence"]["memory_adjustment"]["reason"] == "successful_trajectory_detected"
    assert result["memory_influence"]["memory_adjustment"]["top_success"] is not None
