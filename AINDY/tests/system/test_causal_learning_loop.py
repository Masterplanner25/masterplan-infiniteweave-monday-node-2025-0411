from __future__ import annotations

import uuid

from db.models.ripple_edge import RippleEdge
from db.models.system_event import SystemEvent
from db.models.task import Task
from core.execution_signal_helper import queue_system_event
from domain.infinity_loop import run_loop
from memory.memory_persistence import MemoryNodeModel
from memory.memory_scoring_service import get_relevant_memories, score_memory
from domain.rippletrace_service import build_trace_graph
from core.system_event_types import SystemEventTypes


def _stable_score_snapshot() -> dict:
    return {
        "master_score": 58.0,
        "execution_speed": 58.0,
        "decision_efficiency": 58.0,
        "focus_quality": 58.0,
        "ai_productivity_boost": 58.0,
        "masterplan_progress": 58.0,
    }


def _loop_context(memory_signals: list[dict] | None = None) -> dict:
    return {
        "memory_signals": memory_signals or [],
        "system_state": {"health_status": "healthy", "failure_rate": 0.0, "system_load": 0.1},
        "goals": [],
        "social_signals": [],
    }


def _create_ready_task(db_session, test_user, name: str = "Recover execution path") -> Task:
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


def _emit_execution_failure_trace(db_session, test_user, *, task_name: str, trigger_event: str = "task_completed"):
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
            "workflow_type": trigger_event,
        },
        required=True,
    )
    failed_event_id = queue_system_event(
        db=db_session,
        event_type=SystemEventTypes.EXECUTION_FAILED,
        user_id=test_user.id,
        trace_id=trace_id,
        parent_event_id=started_event_id,
        source="flow",
        payload={
            "message": f"{task_name} failed",
            "task_name": task_name,
            "workflow_type": trigger_event,
            "error": "simulated failure",
        },
        required=True,
    )
    return trace_id, started_event_id, failed_event_id


class TestCausalLearningLoop:
    def test_event_trace_memory_scoring_and_decision_adjustment(self, db_session, test_user):
        task = _create_ready_task(db_session, test_user)
        trace_id, started_event_id, failed_event_id = _emit_execution_failure_trace(
            db_session,
            test_user,
            task_name=task.name,
        )

        persisted_failure = (
            db_session.query(SystemEvent)
            .filter(SystemEvent.id == failed_event_id)
            .first()
        )
        assert persisted_failure is not None
        assert persisted_failure.trace_id == trace_id

        graph = build_trace_graph(db_session, trace_id)
        assert any(node["id"] == str(failed_event_id) for node in graph["nodes"])
        assert any(
            edge["source"] == str(started_event_id)
            and edge["target"] == str(failed_event_id)
            and edge["relationship_type"] == "caused_by"
            for edge in graph["edges"]
        )

        memory_node = (
            db_session.query(MemoryNodeModel)
            .filter(MemoryNodeModel.source_event_id == failed_event_id)
            .order_by(MemoryNodeModel.created_at.desc())
            .first()
        )
        assert memory_node is not None
        assert memory_node.content
        assert memory_node.tags
        assert memory_node.impact_score > 0
        assert memory_node.memory_type == "failure"
        memory_node.impact_score = 10.0
        memory_node.usage_count = 6
        db_session.add(memory_node)
        db_session.commit()
        db_session.refresh(memory_node)

        stored_edge = (
            db_session.query(RippleEdge)
            .filter(
                RippleEdge.source_event_id == failed_event_id,
                RippleEdge.target_memory_node_id == memory_node.id,
                RippleEdge.relationship_type == "stored_as_memory",
            )
            .first()
        )
        assert stored_edge is not None
        assert any(
            node["id"] == str(memory_node.id) and node["node_kind"] == "memory_node"
            for node in graph["nodes"]
        )

        relevant_memories = get_relevant_memories(
            {
                "user_id": test_user.id,
                "trigger_event": "task_completed",
                "current_state": "causal_learning_test",
                "goal": task.name,
                "constraints": [],
            },
            db=db_session,
        )
        assert relevant_memories

        scored_memory = next(item for item in relevant_memories if item["id"] == str(memory_node.id))
        assert scored_memory["weighted_score"] > 0
        assert score_memory(scored_memory) > 0
        assert scored_memory["type"] == "failure"

        baseline = run_loop(
            user_id=str(test_user.id),
            trigger_event="manual",
            db=db_session,
            score_snapshot=_stable_score_snapshot(),
            loop_context=_loop_context([]),
        )
        assert baseline is not None
        assert baseline.decision_type == "continue_highest_priority_task"

        influenced = run_loop(
            user_id=str(test_user.id),
            trigger_event="task_completed",
            db=db_session,
            score_snapshot=_stable_score_snapshot(),
            loop_context=_loop_context(relevant_memories),
        )
        assert influenced is not None
        assert influenced.decision_type == "review_plan"
        assert influenced.adjustment_payload["memory_adjustment"]["reason"] == "high_impact_failures_detected"
        assert influenced.adjustment_payload["next_action"]["type"] == "review_plan"

    def test_empty_trace_and_missing_memory_are_safe(self, db_session, test_user):
        empty_graph = build_trace_graph(db_session, str(uuid.uuid4()))
        assert empty_graph == {"nodes": [], "edges": []}

        memories = get_relevant_memories(
            {
                "user_id": test_user.id,
                "trigger_event": "manual",
                "current_state": "empty_trace_test",
                "goal": "No prior memories",
                "constraints": [],
            },
            db=db_session,
        )
        assert memories == []

        _create_ready_task(db_session, test_user, name="Cold start task")
        adjustment = run_loop(
            user_id=str(test_user.id),
            trigger_event="manual",
            db=db_session,
            score_snapshot=_stable_score_snapshot(),
            loop_context=_loop_context([]),
        )
        assert adjustment is not None
        assert adjustment.decision_type == "continue_highest_priority_task"

    def test_competing_memories_prefer_failure_patterns(self, db_session, test_user):
        task = _create_ready_task(db_session, test_user, name="Competing memory task")

        success_trace = str(uuid.uuid4())
        success_started = queue_system_event(
            db=db_session,
            event_type=SystemEventTypes.EXECUTION_STARTED,
            user_id=test_user.id,
            trace_id=success_trace,
            source="flow",
            payload={"message": "success path started", "task_name": task.name, "workflow_type": "task_completed"},
            required=True,
        )
        queue_system_event(
            db=db_session,
            event_type=SystemEventTypes.EXECUTION_COMPLETED,
            user_id=test_user.id,
            trace_id=success_trace,
            parent_event_id=success_started,
            source="flow",
            payload={"message": "success path completed", "task_name": task.name, "workflow_type": "task_completed"},
            required=True,
        )

        _, _, failed_event_id = _emit_execution_failure_trace(db_session, test_user, task_name=task.name)

        success_memory = (
            db_session.query(MemoryNodeModel)
            .filter(MemoryNodeModel.root_event_id.isnot(None), MemoryNodeModel.memory_type == "outcome")
            .order_by(MemoryNodeModel.created_at.asc())
            .first()
        )
        failure_memory = (
            db_session.query(MemoryNodeModel)
            .filter(MemoryNodeModel.source_event_id == failed_event_id)
            .order_by(MemoryNodeModel.created_at.desc())
            .first()
        )
        assert success_memory is not None
        assert failure_memory is not None
        success_memory.impact_score = 1.0
        success_memory.usage_count = 1
        failure_memory.impact_score = 10.0
        failure_memory.usage_count = 8
        db_session.add(success_memory)
        db_session.add(failure_memory)
        db_session.commit()

        relevant_memories = get_relevant_memories(
            {
                "user_id": test_user.id,
                "trigger_event": "task_completed",
                "current_state": "competing_memories_test",
                "goal": task.name,
                "constraints": [],
            },
            db=db_session,
        )
        assert len(relevant_memories) >= 2
        assert any(item["type"] == "success" for item in relevant_memories)
        assert any(item["type"] == "failure" for item in relevant_memories)
        assert relevant_memories[0]["type"] == "failure"

        adjustment = run_loop(
            user_id=str(test_user.id),
            trigger_event="task_completed",
            db=db_session,
            score_snapshot=_stable_score_snapshot(),
            loop_context=_loop_context(relevant_memories),
        )
        assert adjustment is not None
        assert adjustment.decision_type == "review_plan"
        assert adjustment.adjustment_payload["memory_summary"]["failure_weight"] >= (
            adjustment.adjustment_payload["memory_summary"]["success_weight"]
        )

