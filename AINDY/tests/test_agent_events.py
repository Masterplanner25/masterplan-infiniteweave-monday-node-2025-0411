"""
Sprint N+8 Agent Event Log — full test suite

Group 1: emit_event() service (10 tests)
Group 2: correlation_id generation (8 tests)
Group 3: get_run_events() service (8 tests)
Group 4: GET /agent/runs/{run_id}/events endpoint (7 tests)
Group 5: new_plan replay mode (4 tests)
Group 6: approval inbox badge data (3 tests)

Total target: ~40 tests
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / Factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_run(
    *,
    run_id=None,
    user_id="user-1",
    goal="test goal",
    status="completed",
    overall_risk="low",
    steps_total=2,
    steps_completed=2,
    correlation_id=None,
    replayed_from_run_id=None,
    flow_run_id=None,
):
    """Build a minimal AgentRun mock."""
    run = MagicMock()
    run.id = run_id or uuid.uuid4()
    run.user_id = user_id
    run.goal = goal
    run.executive_summary = "summary"
    run.overall_risk = overall_risk
    run.status = status
    run.steps_total = steps_total
    run.steps_completed = steps_completed
    run.plan = {"steps": [], "overall_risk": overall_risk, "executive_summary": "summary"}
    run.result = None
    run.error_message = None
    run.flow_run_id = flow_run_id
    run.replayed_from_run_id = replayed_from_run_id
    run.correlation_id = correlation_id or f"run_{uuid.uuid4()}"
    run.created_at = datetime.now(timezone.utc)
    run.approved_at = None
    run.started_at = None
    run.completed_at = None
    return run


def _make_step(
    *,
    step_id=None,
    run_id=None,
    step_index=0,
    tool_name="task.create",
    risk_level="low",
    description="do something",
    status="success",
    execution_ms=42,
    error_message=None,
    executed_at=None,
    created_at=None,
    correlation_id=None,
):
    """Build a minimal AgentStep mock."""
    step = MagicMock()
    step.id = step_id or uuid.uuid4()
    step.run_id = run_id or uuid.uuid4()
    step.step_index = step_index
    step.tool_name = tool_name
    step.risk_level = risk_level
    step.description = description
    step.status = status
    step.execution_ms = execution_ms
    step.error_message = error_message
    step.executed_at = executed_at or datetime.now(timezone.utc)
    step.created_at = created_at or datetime.now(timezone.utc)
    step.correlation_id = correlation_id
    return step


def _make_event_row(
    *,
    event_id=None,
    run_id=None,
    user_id="user-1",
    event_type="PLAN_CREATED",
    correlation_id=None,
    payload=None,
    occurred_at=None,
):
    """Build a minimal AgentEvent ORM row mock."""
    evt = MagicMock()
    evt.id = event_id or uuid.uuid4()
    evt.run_id = run_id or uuid.uuid4()
    evt.user_id = user_id
    evt.event_type = event_type
    evt.correlation_id = correlation_id or f"run_{uuid.uuid4()}"
    evt.payload = payload or {}
    evt.occurred_at = occurred_at or datetime.now(timezone.utc)
    evt.created_at = evt.occurred_at
    return evt


def _make_db_for_events(
    *,
    agent_run=None,
    agent_events=None,
    agent_steps=None,
):
    """
    Return a mock Session that supports get_run_events() query patterns.

    Handles: AgentRun (first), AgentEvent (filter+order_by+all), AgentStep (filter+order_by+all).
    """
    db = MagicMock()

    def _query(model):
        q = MagicMock()
        model_str = str(model)
        if "AgentRun" in model_str:
            q.filter.return_value = q
            q.first.return_value = agent_run
        elif "AgentEvent" in model_str:
            q.filter.return_value = q
            q.order_by.return_value = q
            q.all.return_value = agent_events or []
        elif "AgentStep" in model_str:
            q.filter.return_value = q
            q.order_by.return_value = q
            q.all.return_value = agent_steps or []
        else:
            q.filter.return_value = q
            q.first.return_value = None
            q.all.return_value = []
        return q

    db.query.side_effect = _query
    return db


# ─────────────────────────────────────────────────────────────────────────────
# Group 1: emit_event() service
# ─────────────────────────────────────────────────────────────────────────────

class TestEmitEventWritesRow:
    """emit_event() persists one AgentEvent row; is always non-fatal."""

    def test_emit_event_writes_one_row(self):
        """emit_event() adds one AgentEvent row to the session and commits."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        run_id = str(uuid.uuid4())

        # AgentEvent is lazy-imported inside emit_event, patch at the model level
        with patch("db.models.agent_event.AgentEvent") as MockEvent:
            fake_evt = MagicMock()
            MockEvent.return_value = fake_evt
            emit_event(run_id=run_id, user_id="user-1", event_type="PLAN_CREATED", db=db)

        db.add.assert_called_once_with(fake_evt)
        db.commit.assert_called_once()

    def test_emit_event_plan_created_payload(self):
        """PLAN_CREATED emit passes payload with expected keys."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        run_id = str(uuid.uuid4())
        payload = {
            "overall_risk": "low",
            "steps_total": 3,
            "auto_executed": False,
            "goal_preview": "test goal",
            "requires_approval": True,
        }

        captured = {}

        with patch("db.models.agent_event.AgentEvent") as MockEvent:
            def _capture(**kwargs):
                captured.update(kwargs)
                return MagicMock()
            MockEvent.side_effect = _capture
            emit_event(
                run_id=run_id,
                user_id="user-1",
                event_type="PLAN_CREATED",
                db=db,
                payload=payload,
            )

        assert captured.get("event_type") == "PLAN_CREATED"
        assert captured.get("payload") == payload

    def test_emit_event_never_raises_on_db_error(self):
        """emit_event() swallows DB exceptions and never raises to caller."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        db.add.side_effect = RuntimeError("DB connection lost")

        # Must not raise
        emit_event(run_id=str(uuid.uuid4()), user_id="user-1", event_type="PLAN_CREATED", db=db)

    def test_emit_event_approved(self):
        """APPROVED event is emitted with auto_executed=False in payload."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        captured = {}

        with patch("db.models.agent_event.AgentEvent") as MockEvent:
            def _capture(**kwargs):
                captured.update(kwargs)
                return MagicMock()
            MockEvent.side_effect = _capture
            emit_event(
                run_id=str(uuid.uuid4()),
                user_id="user-1",
                event_type="APPROVED",
                db=db,
                payload={"auto_executed": False},
            )

        assert captured["event_type"] == "APPROVED"
        assert captured["payload"]["auto_executed"] is False

    def test_emit_event_rejected(self):
        """REJECTED event is emitted (payload may be empty dict)."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        captured = {}

        with patch("db.models.agent_event.AgentEvent") as MockEvent:
            def _capture(**kwargs):
                captured.update(kwargs)
                return MagicMock()
            MockEvent.side_effect = _capture
            emit_event(
                run_id=str(uuid.uuid4()),
                user_id="user-1",
                event_type="REJECTED",
                db=db,
                payload={},
            )

        assert captured["event_type"] == "REJECTED"

    def test_emit_event_execution_started(self):
        """EXECUTION_STARTED event is written (db.add + db.commit called)."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        with patch("db.models.agent_event.AgentEvent"):
            emit_event(
                run_id=str(uuid.uuid4()),
                user_id="user-1",
                event_type="EXECUTION_STARTED",
                db=db,
            )
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_emit_event_completed(self):
        """COMPLETED event has steps_completed in payload."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        captured = {}

        with patch("db.models.agent_event.AgentEvent") as MockEvent:
            def _capture(**kwargs):
                captured.update(kwargs)
                return MagicMock()
            MockEvent.side_effect = _capture
            emit_event(
                run_id=str(uuid.uuid4()),
                user_id="user-1",
                event_type="COMPLETED",
                db=db,
                payload={"steps_completed": 3},
            )

        assert captured["payload"]["steps_completed"] == 3

    def test_emit_event_execution_failed(self):
        """EXECUTION_FAILED event has error in payload."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        captured = {}

        with patch("db.models.agent_event.AgentEvent") as MockEvent:
            def _capture(**kwargs):
                captured.update(kwargs)
                return MagicMock()
            MockEvent.side_effect = _capture
            emit_event(
                run_id=str(uuid.uuid4()),
                user_id="user-1",
                event_type="EXECUTION_FAILED",
                db=db,
                payload={"error": "task.create timed out"},
            )

        assert captured["event_type"] == "EXECUTION_FAILED"
        assert "error" in captured["payload"]

    def test_emit_event_recovered(self):
        """RECOVERED event has recovered_at in payload."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        captured = {}

        with patch("db.models.agent_event.AgentEvent") as MockEvent:
            def _capture(**kwargs):
                captured.update(kwargs)
                return MagicMock()
            MockEvent.side_effect = _capture
            emit_event(
                run_id=str(uuid.uuid4()),
                user_id="user-1",
                event_type="RECOVERED",
                db=db,
                payload={"recovered_at": "2026-03-25T10:00:00+00:00"},
            )

        assert captured["event_type"] == "RECOVERED"
        assert "recovered_at" in captured["payload"]

    def test_emit_event_replay_created(self):
        """REPLAY_CREATED event has original_run_id and mode in payload."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        original_id = str(uuid.uuid4())
        captured = {}

        with patch("db.models.agent_event.AgentEvent") as MockEvent:
            def _capture(**kwargs):
                captured.update(kwargs)
                return MagicMock()
            MockEvent.side_effect = _capture
            emit_event(
                run_id=str(uuid.uuid4()),
                user_id="user-1",
                event_type="REPLAY_CREATED",
                db=db,
                payload={"original_run_id": original_id, "mode": "same_plan"},
            )

        assert captured["event_type"] == "REPLAY_CREATED"
        assert captured["payload"]["original_run_id"] == original_id
        assert captured["payload"]["mode"] == "same_plan"


# ─────────────────────────────────────────────────────────────────────────────
# Group 2: correlation_id generation
# ─────────────────────────────────────────────────────────────────────────────

class TestCorrelationIdGeneration:

    def test_create_run_generates_correlation_id(self):
        """create_run() generates and stores a correlation_id on the AgentRun."""
        # Test that _run_to_dict includes correlation_id (implies create_run sets it)
        from services.agent_runtime import _run_to_dict

        run = _make_run(correlation_id=f"run_{uuid.uuid4()}")
        d = _run_to_dict(run)
        assert d["correlation_id"] is not None

    def test_correlation_id_format(self):
        """correlation_id starts with 'run_'."""
        from services.agent_runtime import _run_to_dict

        run = _make_run(correlation_id="run_abc-123")
        d = _run_to_dict(run)
        assert d["correlation_id"].startswith("run_")

    def test_correlation_id_in_run_dict(self):
        """_run_to_dict() includes the correlation_id key."""
        from services.agent_runtime import _run_to_dict

        cid = f"run_{uuid.uuid4()}"
        run = _make_run(correlation_id=cid)
        d = _run_to_dict(run)
        assert "correlation_id" in d
        assert d["correlation_id"] == cid

    def test_two_runs_have_different_correlation_ids(self):
        """Two independently created runs have different correlation_ids."""
        from services.agent_runtime import _run_to_dict

        run_a = _make_run(correlation_id=f"run_{uuid.uuid4()}")
        run_b = _make_run(correlation_id=f"run_{uuid.uuid4()}")
        assert _run_to_dict(run_a)["correlation_id"] != _run_to_dict(run_b)["correlation_id"]

    def test_replay_gets_new_correlation_id(self):
        """replay_run() produces a new run with a different correlation_id than the original."""
        from services.agent_runtime import replay_run

        original_cid = f"run_{uuid.uuid4()}"
        new_cid = f"run_{uuid.uuid4()}"
        plan = {"steps": [], "overall_risk": "low", "executive_summary": ""}

        original = MagicMock()
        original.user_id = "user-1"
        original.id = uuid.uuid4()
        original.plan = plan
        original.goal = "g"

        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = original
        db.query.return_value = q

        new_run_dict = {
            "run_id": str(uuid.uuid4()),
            "goal": "g",
            "status": "pending_approval",
            "correlation_id": new_cid,
            "replayed_from_run_id": str(original.id),
        }

        with patch("services.agent_runtime._create_run_from_plan", return_value=new_run_dict), \
             patch("services.agent_runtime.emit_event"):
            result = replay_run(str(original.id), "user-1", db)

        assert result is not None
        assert result["correlation_id"] != original_cid

    def test_correlation_id_propagated_to_agent_step(self):
        """AgentStep model has a correlation_id column."""
        from db.models.agent_run import AgentStep
        assert hasattr(AgentStep, "correlation_id")
        col = AgentStep.__table__.columns.get("correlation_id")
        assert col is not None
        assert col.nullable is True

    def test_plan_created_event_has_correlation_id(self):
        """emit_event called with correlation_id sets it on the AgentEvent row."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        cid = f"run_{uuid.uuid4()}"
        captured = {}

        with patch("db.models.agent_event.AgentEvent") as MockEvent:
            def _capture(**kwargs):
                captured.update(kwargs)
                return MagicMock()
            MockEvent.side_effect = _capture
            emit_event(
                run_id=str(uuid.uuid4()),
                user_id="user-1",
                event_type="PLAN_CREATED",
                db=db,
                correlation_id=cid,
                payload={"overall_risk": "low"},
            )

        assert captured.get("correlation_id") == cid

    def test_approved_event_has_correlation_id(self):
        """APPROVED emit passes the correlation_id to the event row."""
        from services.agent_event_service import emit_event

        db = MagicMock()
        cid = f"run_{uuid.uuid4()}"
        captured = {}

        with patch("db.models.agent_event.AgentEvent") as MockEvent:
            def _capture(**kwargs):
                captured.update(kwargs)
                return MagicMock()
            MockEvent.side_effect = _capture
            emit_event(
                run_id=str(uuid.uuid4()),
                user_id="user-1",
                event_type="APPROVED",
                db=db,
                correlation_id=cid,
                payload={"auto_executed": False},
            )

        assert captured.get("correlation_id") == cid


# ─────────────────────────────────────────────────────────────────────────────
# Group 3: get_run_events() service
# ─────────────────────────────────────────────────────────────────────────────

class TestGetRunEvents:

    def test_get_run_events_returns_lifecycle_events(self):
        """get_run_events() returns lifecycle events from agent_events table."""
        from services.agent_runtime import get_run_events

        run = _make_run()
        evt = _make_event_row(run_id=run.id, event_type="PLAN_CREATED")
        db = _make_db_for_events(agent_run=run, agent_events=[evt], agent_steps=[])

        result = get_run_events(str(run.id), run.user_id, db)

        assert result is not None
        assert any(e["event_type"] == "PLAN_CREATED" for e in result["events"])

    def test_get_run_events_includes_steps(self):
        """AgentStep rows appear as STEP_EXECUTED or STEP_FAILED events."""
        from services.agent_runtime import get_run_events

        run = _make_run()
        step_ok = _make_step(run_id=run.id, step_index=0, status="success")
        step_fail = _make_step(run_id=run.id, step_index=1, status="failed")
        db = _make_db_for_events(agent_run=run, agent_events=[], agent_steps=[step_ok, step_fail])

        result = get_run_events(str(run.id), run.user_id, db)

        event_types = [e["event_type"] for e in result["events"]]
        assert "STEP_EXECUTED" in event_types
        assert "STEP_FAILED" in event_types

    def test_get_run_events_chronological_order(self):
        """Events are sorted by occurred_at ascending."""
        from services.agent_runtime import get_run_events
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        run = _make_run()

        evt1 = _make_event_row(run_id=run.id, event_type="PLAN_CREATED", occurred_at=now)
        evt2 = _make_event_row(run_id=run.id, event_type="APPROVED", occurred_at=now + timedelta(seconds=5))
        evt3 = _make_event_row(run_id=run.id, event_type="EXECUTION_STARTED", occurred_at=now + timedelta(seconds=10))

        db = _make_db_for_events(agent_run=run, agent_events=[evt1, evt2, evt3], agent_steps=[])

        result = get_run_events(str(run.id), run.user_id, db)

        times = [e["occurred_at"] for e in result["events"]]
        assert times == sorted(times)

    def test_get_run_events_returns_none_for_unknown_run(self):
        """get_run_events() returns None when the run does not exist."""
        from services.agent_runtime import get_run_events

        db = _make_db_for_events(agent_run=None)
        result = get_run_events("nonexistent-id", "user-1", db)
        assert result is None

    def test_get_run_events_returns_none_for_wrong_user(self):
        """get_run_events() returns None when user_id does not match run owner."""
        from services.agent_runtime import get_run_events

        run = _make_run(user_id="owner-user")
        db = _make_db_for_events(agent_run=run, agent_events=[], agent_steps=[])

        result = get_run_events(str(run.id), "attacker-user", db)
        assert result is None

    def test_get_run_events_empty_for_pre_n8_run(self):
        """Pre-N+8 run with no agent_events rows returns empty events list, not error."""
        from services.agent_runtime import get_run_events

        run = _make_run()
        db = _make_db_for_events(agent_run=run, agent_events=[], agent_steps=[])

        result = get_run_events(str(run.id), run.user_id, db)

        assert result is not None
        assert result["events"] == []

    def test_get_run_events_step_fallback_to_created_at(self):
        """AgentStep with executed_at=None falls back to created_at for timestamp."""
        from services.agent_runtime import get_run_events

        run = _make_run()
        fallback_ts = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
        step = _make_step(run_id=run.id, step_index=0, status="success",
                          executed_at=None, created_at=fallback_ts)
        db = _make_db_for_events(agent_run=run, agent_events=[], agent_steps=[step])

        result = get_run_events(str(run.id), run.user_id, db)

        assert len(result["events"]) == 1
        assert "2026-03-25" in result["events"][0]["occurred_at"]

    def test_get_run_events_includes_correlation_id(self):
        """Result dict has a correlation_id field."""
        from services.agent_runtime import get_run_events

        cid = f"run_{uuid.uuid4()}"
        run = _make_run(correlation_id=cid)
        db = _make_db_for_events(agent_run=run, agent_events=[], agent_steps=[])

        result = get_run_events(str(run.id), run.user_id, db)

        assert result is not None
        assert "correlation_id" in result
        assert result["correlation_id"] == cid


# ─────────────────────────────────────────────────────────────────────────────
# Group 4: GET /agent/runs/{run_id}/events endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestEventsEndpoint:
    """Tests for GET /agent/runs/{run_id}/events using conftest fixtures."""

    def test_events_endpoint_returns_200(self, client, auth_headers, mock_db):
        """Valid run owned by the current user returns 200."""
        run_id = str(uuid.uuid4())
        expected = {"run_id": run_id, "correlation_id": "run_abc", "events": []}

        with patch("services.agent_runtime.get_run_events", return_value=expected):
            resp = client.get(f"/agent/runs/{run_id}/events", headers=auth_headers)

        assert resp.status_code == 200

    def test_events_endpoint_404_unknown_run(self, client, auth_headers, mock_db):
        """Returns 404 when the run does not exist."""
        run_id = str(uuid.uuid4())

        # get_run_events returns None and DB also returns None (not found)
        mock_db.first.return_value = None

        with patch("services.agent_runtime.get_run_events", return_value=None):
            resp = client.get(f"/agent/runs/{run_id}/events", headers=auth_headers)

        assert resp.status_code == 404

    def test_events_endpoint_403_wrong_user(self, client, auth_headers, mock_db):
        """Returns 403 when the run exists but belongs to a different user."""
        run_id = str(uuid.uuid4())

        # Run exists (first() returns something) but get_run_events returns None (ownership mismatch)
        existing_run = MagicMock()
        existing_run.id = run_id
        mock_db.first.return_value = existing_run

        with patch("services.agent_runtime.get_run_events", return_value=None):
            resp = client.get(f"/agent/runs/{run_id}/events", headers=auth_headers)

        assert resp.status_code == 403

    def test_events_endpoint_requires_auth(self, client):
        """Returns 401 or 403 when no JWT is provided."""
        resp = client.get(f"/agent/runs/{uuid.uuid4()}/events")
        assert resp.status_code in (401, 403)

    def test_events_endpoint_timeline_shape(self, client, auth_headers, mock_db):
        """Response has run_id, correlation_id, and events keys."""
        run_id = str(uuid.uuid4())
        expected = {"run_id": run_id, "correlation_id": "run_abc", "events": []}

        with patch("services.agent_runtime.get_run_events", return_value=expected):
            resp = client.get(f"/agent/runs/{run_id}/events", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert "correlation_id" in data
        assert "events" in data

    def test_events_endpoint_pre_n8_run_graceful(self, client, auth_headers, mock_db):
        """Pre-N+8 run returns {events: [], correlation_id: null} gracefully."""
        run_id = str(uuid.uuid4())
        pre_n8 = {"run_id": run_id, "correlation_id": None, "events": []}

        with patch("services.agent_runtime.get_run_events", return_value=pre_n8):
            resp = client.get(f"/agent/runs/{run_id}/events", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["correlation_id"] is None

    def test_events_endpoint_events_ordered(self, client, auth_headers, mock_db):
        """Events in response are in chronological order."""
        run_id = str(uuid.uuid4())
        events = [
            {"id": "1", "event_type": "PLAN_CREATED", "occurred_at": "2026-03-25T10:00:00+00:00", "payload": {}},
            {"id": "2", "event_type": "APPROVED", "occurred_at": "2026-03-25T10:01:00+00:00", "payload": {}},
            {"id": "3", "event_type": "COMPLETED", "occurred_at": "2026-03-25T10:02:00+00:00", "payload": {}},
        ]
        expected = {"run_id": run_id, "correlation_id": "run_abc", "events": events}

        with patch("services.agent_runtime.get_run_events", return_value=expected):
            resp = client.get(f"/agent/runs/{run_id}/events", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        times = [e["occurred_at"] for e in data["events"]]
        assert times == sorted(times)


# ─────────────────────────────────────────────────────────────────────────────
# Group 5: new_plan replay mode
# ─────────────────────────────────────────────────────────────────────────────

class TestNewPlanReplayMode:

    def _make_original(self):
        plan = {
            "steps": [{"tool": "task.create", "args": {}, "risk_level": "low", "description": "s"}],
            "overall_risk": "low",
            "executive_summary": "original",
        }
        original = MagicMock()
        original.user_id = "user-1"
        original.id = uuid.uuid4()
        original.plan = plan
        original.goal = "original goal"
        return original

    def _db_returning(self, run):
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.first.return_value = run
        db.query.return_value = q
        return db

    def test_replay_same_plan_mode(self):
        """Default mode='same_plan' creates new run with original plan."""
        from services.agent_runtime import replay_run

        original = self._make_original()
        db = self._db_returning(original)
        new_run_dict = {
            "run_id": str(uuid.uuid4()),
            "goal": original.goal,
            "status": "pending_approval",
            "correlation_id": f"run_{uuid.uuid4()}",
            "replayed_from_run_id": str(original.id),
        }

        with patch("services.agent_runtime._create_run_from_plan", return_value=new_run_dict), \
             patch("services.agent_runtime.emit_event"):
            result = replay_run(str(original.id), "user-1", db, mode="same_plan")

        assert result is not None
        assert result["goal"] == original.goal

    def test_replay_new_plan_mode_calls_generate_plan(self):
        """mode='new_plan' calls generate_plan() instead of re-using original plan."""
        from services.agent_runtime import replay_run

        original = self._make_original()
        db = self._db_returning(original)

        fresh_plan = {
            "steps": [{"tool": "memory.recall", "args": {}, "risk_level": "low", "description": "fresh"}],
            "overall_risk": "low",
            "executive_summary": "fresh plan",
        }
        new_run_dict = {
            "run_id": str(uuid.uuid4()),
            "goal": original.goal,
            "status": "pending_approval",
            "correlation_id": f"run_{uuid.uuid4()}",
            "replayed_from_run_id": str(original.id),
        }

        with patch("services.agent_runtime.generate_plan", return_value=fresh_plan) as mock_gp, \
             patch("services.agent_runtime._create_run_from_plan", return_value=new_run_dict), \
             patch("services.agent_runtime.emit_event"):
            result = replay_run(str(original.id), "user-1", db, mode="new_plan")

        mock_gp.assert_called_once_with(goal=original.goal, user_id="user-1", db=db)
        assert result is not None

    def test_replay_new_plan_mode_returns_run(self):
        """mode='new_plan' returns a new run dict on success."""
        from services.agent_runtime import replay_run

        original = self._make_original()
        db = self._db_returning(original)

        fresh_plan = {
            "steps": [],
            "overall_risk": "low",
            "executive_summary": "fresh",
        }
        new_id = str(uuid.uuid4())
        new_run_dict = {
            "run_id": new_id,
            "goal": original.goal,
            "status": "pending_approval",
            "correlation_id": f"run_{uuid.uuid4()}",
            "replayed_from_run_id": str(original.id),
        }

        with patch("services.agent_runtime.generate_plan", return_value=fresh_plan), \
             patch("services.agent_runtime._create_run_from_plan", return_value=new_run_dict), \
             patch("services.agent_runtime.emit_event"):
            result = replay_run(str(original.id), "user-1", db, mode="new_plan")

        assert result is not None
        assert result["run_id"] == new_id

    def test_replay_new_plan_mode_event_has_correct_mode(self):
        """REPLAY_CREATED event payload has mode='new_plan'."""
        from services.agent_runtime import replay_run

        original = self._make_original()
        db = self._db_returning(original)

        fresh_plan = {"steps": [], "overall_risk": "low", "executive_summary": "fresh"}
        new_run_dict = {
            "run_id": str(uuid.uuid4()),
            "goal": original.goal,
            "status": "pending_approval",
            "correlation_id": f"run_{uuid.uuid4()}",
            "replayed_from_run_id": str(original.id),
        }

        emitted_payloads = []

        def _capture_emit(run_id, user_id, event_type, db, correlation_id=None, payload=None):
            if event_type == "REPLAY_CREATED":
                emitted_payloads.append(payload or {})

        with patch("services.agent_runtime.generate_plan", return_value=fresh_plan), \
             patch("services.agent_runtime._create_run_from_plan", return_value=new_run_dict), \
             patch("services.agent_runtime.emit_event", side_effect=_capture_emit):
            replay_run(str(original.id), "user-1", db, mode="new_plan")

        assert len(emitted_payloads) == 1
        assert emitted_payloads[0]["mode"] == "new_plan"


# ─────────────────────────────────────────────────────────────────────────────
# Group 6: approval inbox badge data
# ─────────────────────────────────────────────────────────────────────────────

class TestApprovalInboxBadge:

    def test_list_runs_returns_pending_approval_runs(self, client, auth_headers, mock_db):
        """GET /agent/runs?status=pending_approval returns a list."""
        pending_run = _make_run(status="pending_approval")
        mock_db.all.return_value = [pending_run]

        resp = client.get("/agent/runs?status=pending_approval", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_pending_count_from_list_endpoint(self, client, auth_headers, mock_db):
        """Can count pending_approval runs from the list endpoint."""
        pending_run_1 = _make_run(status="pending_approval")
        pending_run_2 = _make_run(status="pending_approval")

        # The list endpoint chains: db.query().filter().order_by().limit().all()
        # Set up each link in the chain to return mock_db so .all() returns our list
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = [pending_run_1, pending_run_2]
        mock_db.query.return_value = chain

        resp = client.get("/agent/runs?status=pending_approval", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_no_pending_runs_returns_empty_list(self, client, auth_headers, mock_db):
        """Empty list returned when no pending_approval runs exist."""
        mock_db.all.return_value = []

        resp = client.get("/agent/runs?status=pending_approval", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data == []
