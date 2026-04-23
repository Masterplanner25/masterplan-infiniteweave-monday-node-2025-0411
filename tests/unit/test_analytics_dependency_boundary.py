from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
TEST_USER_ID_1 = "00000000-0000-0000-0000-000000000001"
TEST_USER_ID_2 = "00000000-0000-0000-0000-000000000002"


def test_analytics_orchestration_files_avoid_direct_cross_domain_imports():
    targets = {
        ROOT / "apps" / "analytics" / "services" / "infinity_orchestrator.py": {
            "apps.identity.services.identity_boot_service",
            "apps.social.services.social_performance_service",
            "apps.tasks.services.task_service",
        },
        ROOT / "apps" / "analytics" / "services" / "infinity_loop.py": {
            "apps.automation.models",
            "apps.tasks.models",
            "apps.tasks.services.task_service",
        },
    }

    violations: list[str] = []
    for path, blocked in targets.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in blocked:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in blocked:
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{alias.name}")

    assert violations == []


def test_orchestrator_execute_preserves_representative_output(monkeypatch):
    from apps.analytics.services import infinity_orchestrator as orchestrator

    captured_events = []
    captured_release = []

    monkeypatch.setattr(orchestrator, "emit_system_event", lambda **kwargs: captured_events.append(kwargs))
    monkeypatch.setattr(orchestrator, "acquire_execution_lease", lambda *args, **kwargs: True)
    monkeypatch.setattr("apps.analytics.services.concurrency.LeaseHeartbeat", type("HB", (), {"__init__": lambda self, *a, **k: None, "start": lambda self: None, "stop": lambda self: None}))
    monkeypatch.setattr("apps.analytics.services.concurrency.release_execution_lease", lambda *args, **kwargs: captured_release.append((args, kwargs)))
    monkeypatch.setattr(orchestrator, "get_recent_memory", lambda *args, **kwargs: [{"id": "m1"}, {"id": "m2"}])
    monkeypatch.setattr(orchestrator, "get_user_metrics", lambda *args, **kwargs: {"velocity": 3})
    monkeypatch.setattr(orchestrator, "get_relevant_memories", lambda *args, **kwargs: [{"type": "success"}])
    monkeypatch.setattr(orchestrator, "compute_current_state", lambda *args, **kwargs: {"health_status": "healthy"})
    monkeypatch.setattr(orchestrator, "get_task_graph_context", lambda *args, **kwargs: {"ready": [{"id": 1}], "blocked": []})
    monkeypatch.setattr(orchestrator, "get_social_performance_signals", lambda *args, **kwargs: [{"type": "success"}])
    monkeypatch.setattr(orchestrator, "get_job", lambda name: (lambda *args, **kwargs: [{"id": "g1", "name": "Goal"}]))
    monkeypatch.setattr(orchestrator, "get_current_trace_id", lambda: "trace-boundary")
    monkeypatch.setattr(orchestrator, "evaluate_pending_adjustment", lambda **kwargs: {"adjustment_id": "prior"})
    monkeypatch.setattr(
        orchestrator,
        "calculate_infinity_score",
        lambda **kwargs: {
            "master_score": 72.0,
            "kpis": {
                "execution_speed": 62.0,
                "decision_efficiency": 63.0,
                "ai_productivity_boost": 64.0,
                "focus_quality": 65.0,
                "masterplan_progress": 66.0,
            },
            "metadata": {"confidence": "high"},
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "run_loop",
        lambda **kwargs: SimpleNamespace(
            id="adj-1",
            trace_id="trace-boundary",
            decision_type="continue_highest_priority_task",
            applied_at=None,
            adjustment_payload={
                "next_action": {"type": "continue_highest_priority_task", "title": "Continue"},
                "memory_summary": {"success_weight": 1.0},
                "memory_adjustment": {"reason": "memory_signals_applied"},
            },
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "serialize_adjustment",
        lambda adjustment: {
            "id": "adj-1",
            "trace_id": "trace-boundary",
            "decision_type": adjustment.decision_type,
            "adjustment_payload": adjustment.adjustment_payload,
        },
    )

    result = orchestrator.execute(user_id=TEST_USER_ID_1, trigger_event="manual", db=object())

    assert result["score"]["metadata"]["memory_context_count"] == 2
    assert result["memory_context_count"] == 2
    assert result["memory_signal_count"] == 1
    assert result["next_action"]["type"] == "continue_highest_priority_task"
    assert result["adjustment"]["id"] == "adj-1"
    assert [event["event_type"] for event in captured_events] == ["loop.started", "loop.decision"]
    assert len(captured_release) == 1


def test_orchestrator_optional_domain_reads_degrade_gracefully(monkeypatch):
    from apps.analytics.services import infinity_orchestrator as orchestrator

    captured = {}

    monkeypatch.setattr(orchestrator, "emit_system_event", lambda **kwargs: None)
    monkeypatch.setattr(orchestrator, "acquire_execution_lease", lambda *args, **kwargs: True)
    monkeypatch.setattr("apps.analytics.services.concurrency.LeaseHeartbeat", type("HB", (), {"__init__": lambda self, *a, **k: None, "start": lambda self: None, "stop": lambda self: None}))
    monkeypatch.setattr("apps.analytics.services.concurrency.release_execution_lease", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator, "get_recent_memory", lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, "get_user_metrics", lambda *args, **kwargs: {})
    monkeypatch.setattr(orchestrator, "get_relevant_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, "compute_current_state", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("state down")))
    monkeypatch.setattr(orchestrator, "get_task_graph_context", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("tasks down")))
    monkeypatch.setattr(orchestrator, "get_social_performance_signals", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("social down")))
    monkeypatch.setattr(orchestrator, "get_job", lambda name: (lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("goals down"))))
    monkeypatch.setattr(
        orchestrator,
        "calculate_infinity_score",
        lambda **kwargs: {
            "master_score": 55.0,
            "kpis": {
                "execution_speed": 55.0,
                "decision_efficiency": 55.0,
                "ai_productivity_boost": 55.0,
                "focus_quality": 55.0,
                "masterplan_progress": 55.0,
            },
            "metadata": {"confidence": "medium"},
        },
    )
    monkeypatch.setattr(orchestrator, "evaluate_pending_adjustment", lambda **kwargs: None)

    def _run_loop(**kwargs):
        captured["loop_context"] = kwargs["loop_context"]
        return SimpleNamespace(
            id="adj-2",
            trace_id="trace-degraded",
            decision_type="review_plan",
            applied_at=None,
            adjustment_payload={"next_action": {"type": "review_plan"}},
        )

    monkeypatch.setattr(orchestrator, "run_loop", _run_loop)
    monkeypatch.setattr(
        orchestrator,
        "serialize_adjustment",
        lambda adjustment: {
            "id": "adj-2",
            "trace_id": adjustment.trace_id,
            "decision_type": adjustment.decision_type,
            "adjustment_payload": adjustment.adjustment_payload,
        },
    )

    result = orchestrator.execute(user_id=TEST_USER_ID_2, trigger_event="scheduled", db=object())

    assert result["adjustment"]["id"] == "adj-2"
    assert result["next_action"]["type"] == "review_plan"
    assert captured["loop_context"]["system_state"] == {}
    assert captured["loop_context"]["goals"] == []
    assert captured["loop_context"]["task_graph"] == {}
    assert captured["loop_context"]["social_signals"] == []
