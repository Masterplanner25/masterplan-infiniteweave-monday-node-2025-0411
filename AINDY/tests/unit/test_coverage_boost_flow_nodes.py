from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid


def test_masterplan_anchor_node_invalid_date():
    from AINDY.runtime.flow_definitions_extended import masterplan_anchor_node

    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = SimpleNamespace(
        id=1,
        anchor_date=None,
        goal_value=None,
        goal_unit=None,
        goal_description=None,
    )
    db = MagicMock()
    db.query.return_value = query

    result = masterplan_anchor_node(
        {"plan_id": 1, "anchor_date": "not-a-date"},
        {"db": db, "user_id": "user-1"},
    )

    assert result["status"] == "FAILURE"
    assert "HTTP_422" in result["error"]


def test_masterplan_projection_node_eta_failure(monkeypatch):
    from AINDY.runtime.flow_definitions_extended import masterplan_projection_node

    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = SimpleNamespace(id=9)
    db = MagicMock()
    db.query.return_value = query

    monkeypatch.setattr(
        "analytics.eta_service.calculate_eta",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("eta down")),
    )

    result = masterplan_projection_node(
        {"plan_id": 9},
        {"db": db, "user_id": "user-1"},
    )

    assert result["status"] == "FAILURE"
    assert "eta_calculation_failed" in result["error"]


class _ScalarQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def scalar(self):
        return self.value


class _RequestMetricQuery:
    def __init__(self, rows, error_rows):
        self.rows = rows
        self.error_rows = error_rows
        self.filter_calls = 0
        self.error_mode = False

    def filter(self, *args, **kwargs):
        self.filter_calls += 1
        if self.filter_calls >= 4:
            self.error_mode = True
        return self

    def count(self):
        if self.filter_calls == 2:
            return len(self.rows)
        if self.filter_calls >= 3:
            return len(self.error_rows)
        return len(self.rows)

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, _value):
        return self

    def all(self):
        return list(self.error_rows if self.error_mode else self.rows)


class _ListQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, _value):
        return self

    def offset(self, _value):
        return self

    def filter_by(self, **kwargs):
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def update(self, *args, **kwargs):
        return 1


def test_observability_dashboard_node_success():
    from AINDY.db.models.agent_event import AgentEvent
    from AINDY.db.models.flow_run import FlowRun
    from AINDY.db.models.request_metric import RequestMetric
    from AINDY.db.models.system_event import SystemEvent
    from AINDY.db.models.system_health_log import SystemHealthLog
    from AINDY.runtime.flow_definitions_extended import observability_dashboard_node

    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    requests = [
        SimpleNamespace(
            request_id="r1",
            trace_id="t1",
            method="GET",
            path="/x",
            status_code=200,
            duration_ms=10,
            created_at=now,
        )
    ]
    request_errors = [
        SimpleNamespace(
            request_id="r2",
            trace_id="t2",
            method="POST",
            path="/y",
            status_code=500,
            duration_ms=99,
            created_at=now,
        )
    ]
    system_events = [
        SimpleNamespace(type="loop.started", trace_id="trace-loop", timestamp=now, payload={"a": 1}),
        SimpleNamespace(type="execution.started", trace_id="trace-exec", timestamp=now, payload={}),
    ]
    agent_events = [
        SimpleNamespace(
            run_id=uuid.uuid4(),
            event_type="STEP",
            correlation_id="corr-1",
            occurred_at=now,
            payload={"x": 1},
        )
    ]
    health_logs = [
        SimpleNamespace(
            status="healthy",
            timestamp=now,
            components={"db": "ok"},
            api_endpoints={"/health": 200},
            avg_latency_ms=12.5,
        )
    ]
    flows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            trace_id="flow-trace",
            flow_name="other_flow",
            workflow_type="wf",
            status="running",
            current_node="node-a",
            created_at=now,
        )
    ]

    db = MagicMock()

    def query_side_effect(model):
        if model is RequestMetric:
            return _RequestMetricQuery(requests, request_errors)
        if model is AgentEvent:
            return _ListQuery(agent_events)
        if model is SystemEvent:
            return _ListQuery(system_events)
        if model is SystemHealthLog:
            return _ListQuery(health_logs)
        if model is FlowRun:
            return _ListQuery(flows)
        return _ScalarQuery(12.5)

    db.query.side_effect = query_side_effect

    result = observability_dashboard_node(
        {"window_hours": 24},
        {"db": db, "user_id": str(user_id)},
    )

    assert result["status"] == "SUCCESS"
    payload = result["output_patch"]["observability_dashboard_result"]
    assert payload["summary"]["loop_events"] == 1
    assert payload["summary"]["health_status"] == "healthy"
    assert payload["system_events"]["counts"]["loop.started"] == 1
    assert payload["request_metrics"]["recent_errors"][0]["status_code"] == 500


def test_masterplan_activate_node_success(monkeypatch):
    from AINDY.runtime.flow_definitions_extended import masterplan_activate_node

    plan = SimpleNamespace(id=7, user_id="user-1", is_active=False, status="draft", activated_at=None)

    query = MagicMock()
    query.filter.return_value = query
    query.first.return_value = plan
    query.update.return_value = 1

    db = MagicMock()
    db.query.return_value = query

    monkeypatch.setattr(
        "domain.masterplan_execution_service.sync_masterplan_tasks",
        lambda **kwargs: {"generated": 2, "skipped": False},
    )
    monkeypatch.setattr(
        "domain.masterplan_execution_service.get_masterplan_execution_status",
        lambda **kwargs: {"tasks": {"total": 2}},
    )

    result = masterplan_activate_node({"plan_id": 7}, {"db": db, "user_id": "user-1"})

    assert result["status"] == "SUCCESS"
    payload = result["output_patch"]["masterplan_activate_result"]
    assert payload["status"] == "activated"
    assert payload["task_sync"]["generated"] == 2
    assert plan.is_active is True
    assert plan.status == "active"


class _LeaseQuery:
    def __init__(self, row):
        self.row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.row


def test_observability_scheduler_status_node_success(monkeypatch):
    from AINDY.runtime.flow_definitions_extended import observability_scheduler_status_node

    lease = SimpleNamespace(
        owner_id="worker-1",
        acquired_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        heartbeat_at=datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
        expires_at=datetime(2025, 1, 1, 2, tzinfo=timezone.utc),
    )
    db = MagicMock()
    db.query.return_value = _LeaseQuery(lease)

    monkeypatch.setattr(
        "platform_layer.scheduler_service.get_scheduler",
        lambda: SimpleNamespace(running=True),
    )
    monkeypatch.setattr("domain.task_services.is_background_leader", lambda: True)

    result = observability_scheduler_status_node({}, {"db": db, "user_id": "user-1"})

    assert result["status"] == "SUCCESS"
    payload = result["output_patch"]["observability_scheduler_status_result"]
    assert payload["scheduler_running"] is True
    assert payload["is_leader"] is True
    assert payload["lease"]["owner_id"] == "worker-1"


def test_observability_rippletrace_node_empty_trace():
    from AINDY.runtime.flow_definitions_extended import observability_rippletrace_node

    query = MagicMock()
    query.filter.return_value = query
    query.count.return_value = 0

    db = MagicMock()
    db.query.return_value = query

    result = observability_rippletrace_node(
        {"trace_id": "trace-404"},
        {"db": db, "user_id": str(uuid.uuid4())},
    )

    assert result["status"] == "SUCCESS"
    payload = result["output_patch"]["observability_rippletrace_result"]
    assert payload["nodes"] == []
    assert payload["ripple_span"]["depth"] == 0


def test_register_extended_flows_registers_single_and_multi_node_flows(monkeypatch):
    import AINDY.runtime.flow_definitions_extended as flow_defs

    flow_registry = {}
    registered = {}

    monkeypatch.setattr(flow_defs, "FLOW_REGISTRY", flow_registry)
    monkeypatch.setattr(
        flow_defs,
        "register_flow",
        lambda name, definition: registered.setdefault(name, definition),
    )

    flow_defs.register_extended_flows()

    assert "masterplan_activate" in registered
    assert registered["masterplan_activate"]["start"] == "masterplan_activate_node"
    assert "observability_dashboard" in registered
    assert "watcher_signals_receive" in registered
    assert registered["watcher_signals_receive"]["start"] == "watcher_ingest_validate"
    assert "memory_execute_loop" in registered
    assert "watcher_evaluate_trigger" in registered
    assert registered["watcher_evaluate_trigger"]["start"] == "watcher_evaluate_trigger_node"


def test_misc_extended_flow_nodes_smoke(monkeypatch):
    import AINDY.analytics.arm_metrics_service as arm_metrics_module
    import AINDY.domain.goal_service as goal_service
    import AINDY.domain.search_service as search_service
    import AINDY.modules.deepseek.config_manager_deepseek as config_module
    from AINDY.runtime.flow_definitions_extended import (
        arm_config_get_node,
        arm_config_suggest_node,
        arm_config_update_node,
        arm_metrics_node,
        goals_list_node,
        goals_state_node,
        leadgen_preview_search_node,
    )

    class FakeConfigManager:
        def get_all(self):
            return {"mode": "balanced"}

        def update(self, updates):
            return {"mode": "updated", **updates}

    class FakeMetricsService:
        def __init__(self, db, user_id):
            self.db = db
            self.user_id = user_id

        def get_all_metrics(self, window=30):
            return {
                "decision_efficiency": {"score": 0.8},
                "execution_speed": {"average": 12.5},
                "ai_productivity_boost": {"ratio": 1.4},
                "lost_potential": {"waste_percentage": 3},
                "learning_efficiency": {"trend": "up"},
                "total_sessions": 9,
            }

    class FakeSuggestionEngine:
        def __init__(self, current_config, metrics):
            self.current_config = current_config
            self.metrics = metrics

        def generate_suggestions(self):
            return {"changes": ["raise_parallelism"]}

    monkeypatch.setattr(config_module, "ConfigManager", FakeConfigManager)
    monkeypatch.setattr(arm_metrics_module, "ARMMetricsService", FakeMetricsService)
    monkeypatch.setattr(arm_metrics_module, "ARMConfigSuggestionEngine", FakeSuggestionEngine)
    monkeypatch.setattr(goal_service, "get_active_goals", lambda db, user_id: [{"id": 1}])
    monkeypatch.setattr(goal_service, "get_goal_states", lambda db, user_id: [{"state": "on_track"}])
    monkeypatch.setattr(goal_service, "detect_goal_drift", lambda db, user_id: {"drift": False})
    monkeypatch.setattr(
        search_service,
        "search_leads",
        lambda query, db=None, user_id=None: [{"query": query, "user_id": user_id}],
    )

    context = {"db": MagicMock(), "user_id": "user-1"}

    assert arm_config_get_node({}, context)["output_patch"]["arm_config_get_result"]["mode"] == "balanced"
    assert arm_config_update_node({"updates": {"level": 2}}, context)["output_patch"]["arm_config_update_result"]["config"]["level"] == 2
    assert arm_metrics_node({"window": 7}, context)["output_patch"]["arm_metrics_result"]["total_sessions"] == 9
    suggest_payload = arm_config_suggest_node({}, context)["output_patch"]["arm_config_suggest_result"]
    assert suggest_payload["changes"] == ["raise_parallelism"]
    assert suggest_payload["metrics_snapshot"]["decision_efficiency"] == 0.8
    assert goals_list_node({}, context)["output_patch"]["goals_list_result"] == [{"id": 1}]
    assert goals_state_node({}, context)["output_patch"]["goals_state_result"]["drift"] == {"drift": False}
    assert leadgen_preview_search_node({"query": "agency"}, context)["output_patch"]["leadgen_preview_search_result"][0]["query"] == "agency"


def test_query_backed_extended_flow_nodes_smoke(monkeypatch):
    import AINDY.domain.task_services as task_services
    from AINDY.db.models.arm_models import AnalysisResult, CodeGeneration
    from AINDY.db.models.infinity_loop import UserFeedback
    from AINDY.db.models.leadgen_model import LeadGenResult
    from AINDY.db.models.task import Task
    from AINDY.db.models.user_score import ScoreHistory
    from AINDY.runtime.flow_definitions_extended import (
        arm_logs_node,
        leadgen_list_node,
        score_feedback_list_node,
        score_history_node,
        tasks_list_node,
        tasks_recurrence_check_node,
    )

    now = datetime.now(timezone.utc)
    analysis_rows = [
        SimpleNamespace(
            session_id=uuid.uuid4(),
            file_path="C:/tmp/demo.py",
            status="ok",
            execution_seconds=2.0,
            input_tokens=100,
            output_tokens=50,
            task_priority="high",
            result_summary="done",
            created_at=now,
        )
    ]
    generation_rows = [
        SimpleNamespace(
            session_id=uuid.uuid4(),
            language="python",
            generation_type="rewrite",
            execution_seconds=1.5,
            input_tokens=40,
            output_tokens=20,
            created_at=now,
        )
    ]
    history_rows = [SimpleNamespace(master_score=97.5, calculated_at=now)]
    feedback_rows = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    lead_rows = [
        SimpleNamespace(
            company="Acme",
            url="https://acme.test",
            fit_score=0.8,
            intent_score=0.7,
            data_quality_score=0.9,
            overall_score=0.85,
            reasoning="strong fit",
            created_at=now,
        )
    ]
    task_rows = [
        SimpleNamespace(
            id=10,
            name="Ship",
            category="ops",
            priority="high",
            status="pending",
            time_spent=5,
            masterplan_id=2,
            parent_task_id=None,
            depends_on=[{"task_id": 9}],
            dependency_type="hard",
            automation_type="email",
            automation_config={"template": "t"},
        )
    ]

    def query_side_effect(model):
        mapping = {
            AnalysisResult: _ListQuery(analysis_rows),
            CodeGeneration: _ListQuery(generation_rows),
            ScoreHistory: _ListQuery(history_rows),
            UserFeedback: _ListQuery(feedback_rows),
            LeadGenResult: _ListQuery(lead_rows),
            Task: _ListQuery(task_rows),
        }
        return mapping[model]

    db = MagicMock()
    db.query.side_effect = query_side_effect

    started = []

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self.target = target
            self.daemon = daemon

        def start(self):
            started.append((self.target, self.daemon))

    monkeypatch.setattr("threading.Thread", FakeThread)
    monkeypatch.setattr(task_services, "handle_recurrence", lambda: None)

    user_id = str(uuid.uuid4())
    arm_payload = arm_logs_node({"limit": 5}, {"db": db, "user_id": user_id})["output_patch"]["arm_logs_result"]
    assert arm_payload["summary"]["total_tokens_used"] == 210
    assert arm_payload["analyses"][0]["file"] == "demo.py"
    assert score_history_node({}, {"db": db, "user_id": user_id})["output_patch"]["score_history_result"]["history"][0]["master_score"] == 97.5
    assert score_feedback_list_node({}, {"db": db, "user_id": user_id})["output_patch"]["score_feedback_list_result"]["count"] == 2
    assert leadgen_list_node({}, {"db": db, "user_id": user_id})["output_patch"]["leadgen_list_result"][0]["company"] == "Acme"
    assert tasks_list_node({}, {"db": db, "user_id": user_id})["output_patch"]["tasks_list_result"][0]["task_name"] == "Ship"
    assert tasks_recurrence_check_node({}, {"db": db, "user_id": user_id})["status"] == "SUCCESS"
    assert started and started[0][1] is True


def test_score_get_health_and_dashboard_nodes(monkeypatch):
    import AINDY.domain.infinity_loop as infinity_loop
    import AINDY.domain.infinity_orchestrator as infinity_orchestrator
    from AINDY.db.models import PingDB
    from AINDY.db.models.author_model import AuthorDB
    from AINDY.db.models.system_health_log import SystemHealthLog
    from AINDY.db.models.user_score import UserScore
    from AINDY.runtime.flow_definitions_extended import (
        dashboard_overview_node,
        health_dashboard_list_node,
        score_get_node,
    )

    now = datetime.now(timezone.utc)
    user_id = str(uuid.uuid4())

    monkeypatch.setattr(
        infinity_orchestrator,
        "execute",
        lambda **kwargs: {"score": {"user_id": str(kwargs["user_id"]), "master_score": 88.0}},
    )
    monkeypatch.setattr(infinity_loop, "get_latest_adjustment", lambda **kwargs: object())
    monkeypatch.setattr(
        infinity_loop,
        "serialize_adjustment",
        lambda latest: {
            "decision_type": "promote",
            "applied_at": now.isoformat(),
            "adjustment_payload": {
                "loop_context": {"memory": [1, 2], "memory_signals": ["a"]},
            },
        },
    )

    score_row = SimpleNamespace(
        master_score=91.0,
        execution_speed_score=0.7,
        decision_efficiency_score=0.8,
        ai_productivity_boost_score=0.9,
        focus_quality_score=0.6,
        masterplan_progress_score=0.5,
        confidence=0.95,
        data_points_used=12,
        trigger_event="manual",
        calculated_at=now,
    )
    health_rows = [
        SimpleNamespace(
            timestamp=now,
            status="healthy",
            avg_latency_ms=11.2,
            components={"db": "ok"},
            api_endpoints={"/health": 200},
        )
    ]
    author_rows = [SimpleNamespace(id=1, name="Alice", platform="x", last_seen=now, notes="active")]
    ripple_rows = [
        SimpleNamespace(
            ping_type="mention",
            source_platform="x",
            connection_summary="close",
            date_detected=now,
        )
    ]

    db_empty = MagicMock()
    db_empty.query.return_value = _ListQuery([])
    empty_result = score_get_node({}, {"db": db_empty, "user_id": user_id})
    assert empty_result["output_patch"]["score_get_result"]["master_score"] == 88.0

    def query_side_effect(model):
        mapping = {
            UserScore: _ListQuery([score_row]),
            SystemHealthLog: _ListQuery(health_rows),
            AuthorDB: _ListQuery(author_rows),
            PingDB: _ListQuery(ripple_rows),
        }
        return mapping[model]

    db = MagicMock()
    db.query.side_effect = query_side_effect

    score_payload = score_get_node({}, {"db": db, "user_id": user_id})["output_patch"]["score_get_result"]
    assert score_payload["metadata"]["memory_context_count"] == 2
    assert score_payload["latest_adjustment"]["decision_type"] == "promote"

    health_payload = health_dashboard_list_node({}, {"db": db, "user_id": user_id})["output_patch"]["health_dashboard_list_result"]
    assert health_payload["count"] == 1
    overview_payload = dashboard_overview_node({}, {"db": db, "user_id": user_id})["output_patch"]["dashboard_overview_result"]
    assert overview_payload["overview"]["author_count"] == 1


def test_analytics_and_watcher_nodes_smoke():
    from AINDY.db.models import MasterPlan
    from AINDY.db.models.metrics_models import CanonicalMetricDB
    from AINDY.db.models.watcher_signal import WatcherSignal
    from AINDY.runtime.flow_definitions_extended import (
        analytics_masterplan_get_node,
        analytics_masterplan_summary_node,
        watcher_signals_list_node,
    )

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    plan = SimpleNamespace(id=5, user_id=user_id)
    metric_rows = [
        SimpleNamespace(
            period_type="week",
            period_start=now,
            period_end=now,
            passive_visibility=100,
            active_discovery=20,
            unique_reach=50,
            interaction_volume=10,
            deep_attention_units=5,
            intent_signals=4,
            conversion_events=2,
            growth_velocity=3,
        )
    ]
    watcher_rows = [
        SimpleNamespace(
            id=1,
            signal_type="focus",
            session_id="sess-1",
            app_name="Editor",
            window_title="main.py",
            activity_type="coding",
            signal_timestamp=now,
            received_at=now,
            duration_seconds=30,
            focus_score=0.9,
            signal_metadata={"lang": "py"},
        )
    ]

    def query_side_effect(model):
        mapping = {
            MasterPlan: _ListQuery([plan]),
            CanonicalMetricDB: _ListQuery(metric_rows),
            WatcherSignal: _ListQuery(watcher_rows),
        }
        return mapping[model]

    db = MagicMock()
    db.query.side_effect = query_side_effect

    get_payload = analytics_masterplan_get_node(
        {"masterplan_id": 5, "period_type": "week", "platform": "linkedin", "scope_type": "account"},
        {"db": db, "user_id": user_id},
    )["output_patch"]["analytics_masterplan_get_result"]
    assert len(get_payload) == 1

    summary_payload = analytics_masterplan_summary_node(
        {"masterplan_id": 5, "group_by": "period"},
        {"db": db, "user_id": user_id},
    )["output_patch"]["analytics_masterplan_summary_result"]
    assert summary_payload["grouped"][0]["rates"]["interaction_rate"] == 0.1

    watcher_payload = watcher_signals_list_node(
        {"session_id": "sess-1", "signal_type": "focus", "limit": 10},
        {"db": db, "user_id": user_id},
    )["output_patch"]["watcher_signals_list_result"]
    assert watcher_payload[0]["metadata"]["lang"] == "py"


def test_flow_run_nodes_smoke(monkeypatch):
    import AINDY.runtime.flow_engine as flow_engine
    from AINDY.db.models.flow_run import FlowHistory, FlowRun
    from AINDY.runtime.flow_definitions_extended import (
        flow_registry_get_node,
        flow_run_get_node,
        flow_run_history_node,
        flow_run_resume_node,
        flow_runs_list_node,
    )

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(
        id="run-1",
        flow_name="demo_flow",
        workflow_type="demo",
        status="waiting",
        trace_id="trace-1",
        current_node="node-a",
        waiting_for="approval",
        state={"x": 1},
        error_message=None,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )
    history_rows = [
        SimpleNamespace(
            id=1,
            node_name="node-a",
            status="SUCCESS",
            execution_time_ms=12,
            output_patch={"x": 1},
            error_message=None,
            created_at=now,
        )
    ]

    def query_side_effect(model):
        mapping = {
            FlowRun: _ListQuery([run]),
            FlowHistory: _ListQuery(history_rows),
        }
        return mapping[model]

    db = MagicMock()
    db.query.side_effect = query_side_effect
    monkeypatch.setattr(flow_engine, "route_event", lambda **kwargs: [{"accepted": True}])

    list_payload = flow_runs_list_node({}, {"db": db, "user_id": user_id})["output_patch"]["flow_runs_list_result"]
    assert list_payload["count"] == 1

    get_payload = flow_run_get_node({"run_id": "run-1"}, {"db": db, "user_id": user_id})["output_patch"]["flow_run_get_result"]
    assert get_payload["waiting_for"] == "approval"

    history_payload = flow_run_history_node({"run_id": "run-1"}, {"db": db, "user_id": user_id})["output_patch"]["flow_run_history_result"]
    assert history_payload["node_count"] == 1

    resume_payload = flow_run_resume_node(
        {"run_id": "run-1", "event_type": "approval", "payload": {"ok": True}},
        {"db": db, "user_id": user_id},
    )["output_patch"]["flow_run_resume_result"]
    assert resume_payload["resumed"] is True

    registry_payload = flow_registry_get_node({}, {"db": db, "user_id": user_id})["output_patch"]["flow_registry_get_result"]
    assert "flows" in registry_payload
    assert registry_payload["node_count"] >= 1
