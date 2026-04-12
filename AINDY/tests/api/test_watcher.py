"""
test_watcher.py — A.I.N.D.Y. Watcher test suite.

Coverage:
  - classifier: ActivityType mapping for work/comm/distraction/idle/unknown
  - session_tracker: state machine transitions and event emission
  - watcher_router: POST /watcher/signals, GET /watcher/signals (auth, validation, persistence)
  - watcher config: load() and validate()
  - signal_emitter: emit/queue behavior, dry-run mode
"""
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# ── Classifier tests ─────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestClassifier:
    """classify() maps (app_name, window_title) to the correct ActivityType."""

    def setup_method(self):
        from AINDY.watcher.classifier import classify
        from AINDY.watcher.window_detector import WindowInfo
        self.classify = classify
        self.WindowInfo = WindowInfo

    def _w(self, app: str, title: str = ""):
        return self.WindowInfo(app_name=app, window_title=title)

    def test_work_cursor(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("cursor.exe", "main.py"))
        assert r.activity_type == ActivityType.WORK

    def test_work_vscode(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("code.exe", "test.py"))
        assert r.activity_type == ActivityType.WORK

    def test_work_terminal(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("windowsterminal.exe"))
        assert r.activity_type == ActivityType.WORK

    def test_work_python(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("python.exe"))
        assert r.activity_type == ActivityType.WORK

    def test_communication_slack(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("slack.exe"))
        assert r.activity_type == ActivityType.COMMUNICATION

    def test_communication_zoom(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("zoom.exe"))
        assert r.activity_type == ActivityType.COMMUNICATION

    def test_distraction_youtube_process(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("youtube.exe"))
        assert r.activity_type == ActivityType.DISTRACTION

    def test_distraction_browser_youtube_title(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("chrome.exe", "Never Gonna Give You Up - YouTube"))
        assert r.activity_type == ActivityType.DISTRACTION

    def test_distraction_browser_reddit(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("firefox.exe", "r/programming - Reddit"))
        assert r.activity_type == ActivityType.DISTRACTION

    def test_distraction_browser_twitter(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("edge.exe", "Elon Musk on Twitter"))
        assert r.activity_type == ActivityType.DISTRACTION

    def test_browser_non_distraction_title(self):
        """Browser with non-distraction title should NOT be classified as distraction."""
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("chrome.exe", "FastAPI Docs — uvicorn docs"))
        assert r.activity_type != ActivityType.DISTRACTION

    def test_idle_no_window(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(None)
        assert r.activity_type == ActivityType.IDLE
        assert r.confidence == 1.0
        assert r.matched_rule == "no_active_window"

    def test_idle_lockscreen(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("lockapp.exe"))
        assert r.activity_type == ActivityType.IDLE

    def test_unknown_process(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("randombinaryxyz.exe", "Some Random Window"))
        assert r.activity_type == ActivityType.UNKNOWN

    def test_result_has_app_name(self):
        r = self.classify(self._w("cursor.exe", "hello.py"))
        assert "cursor" in r.app_name

    def test_result_has_matched_rule(self):
        r = self.classify(self._w("cursor.exe"))
        assert r.matched_rule != ""

    def test_confidence_range(self):
        from AINDY.watcher.window_detector import WindowInfo
        for app in ["cursor.exe", "slack.exe", "chrome.exe", "unknownthing.exe"]:
            r = self.classify(WindowInfo(app_name=app, window_title=""))
            assert 0.0 <= r.confidence <= 1.0

    def test_distraction_steam(self):
        from AINDY.watcher.classifier import ActivityType
        r = self.classify(self._w("steam.exe", "Steam Store"))
        assert r.activity_type == ActivityType.DISTRACTION


# ---------------------------------------------------------------------------
# ── SessionTracker tests ──────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def _make_result(activity_type, app="cursor.exe", title=""):
    from AINDY.watcher.classifier import ActivityType, ClassificationResult
    return ClassificationResult(
        activity_type=activity_type,
        confidence=0.9,
        matched_rule="test",
        app_name=app,
        window_title=title,
    )


def _ts(offset_seconds: float = 0.0) -> datetime:
    from datetime import timedelta
    return datetime(2026, 3, 24, 9, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=offset_seconds)


class TestSessionTrackerIdle:
    """IDLE state — no events until work confirmed."""

    def test_initial_state_is_idle(self):
        from AINDY.watcher.session_tracker import SessionState, SessionTracker
        from AINDY.watcher.classifier import ActivityType
        t = SessionTracker(confirmation_delay=5.0)
        assert t.state == SessionState.IDLE

    def test_idle_on_non_work_stays_idle(self):
        from AINDY.watcher.session_tracker import SessionState, SessionTracker
        from AINDY.watcher.classifier import ActivityType
        t = SessionTracker(confirmation_delay=5.0)
        events = t.update(_make_result(ActivityType.COMMUNICATION), now=_ts(0))
        assert t.state == SessionState.IDLE
        assert events == []

    def test_work_transitions_to_confirming(self):
        from AINDY.watcher.session_tracker import SessionState, SessionTracker
        from AINDY.watcher.classifier import ActivityType
        t = SessionTracker(confirmation_delay=5.0)
        t.update(_make_result(ActivityType.WORK), now=_ts(0))
        assert t.state == SessionState.CONFIRMING_WORK

    def test_confirming_resets_on_non_work(self):
        from AINDY.watcher.session_tracker import SessionState, SessionTracker
        from AINDY.watcher.classifier import ActivityType
        t = SessionTracker(confirmation_delay=5.0)
        t.update(_make_result(ActivityType.WORK), now=_ts(0))
        t.update(_make_result(ActivityType.DISTRACTION), now=_ts(1))
        assert t.state == SessionState.IDLE


class TestSessionTrackerWorking:
    """WORKING state — session_started emitted, transitions on distraction/idle."""

    def setup_method(self):
        from AINDY.watcher.session_tracker import SessionTracker, SessionState
        from AINDY.watcher.classifier import ActivityType
        self.SessionTracker = SessionTracker
        self.SessionState = SessionState
        self.ActivityType = ActivityType
        self.t = SessionTracker(confirmation_delay=5.0, distraction_timeout=10.0)

    def _confirm_session(self):
        """Drive tracker into WORKING state."""
        self.t.update(_make_result(self.ActivityType.WORK), now=_ts(0))
        events = self.t.update(_make_result(self.ActivityType.WORK), now=_ts(6))
        return events

    def test_session_started_emitted(self):
        events = self._confirm_session()
        signal_types = [e.signal_type for e in events]
        assert "session_started" in signal_types

    def test_session_id_assigned(self):
        self._confirm_session()
        assert self.t.session_id != ""

    def test_state_is_working(self):
        self._confirm_session()
        assert self.t.state == self.SessionState.WORKING

    def test_distraction_transitions_to_distracted(self):
        self._confirm_session()
        # Continuous distraction past timeout
        events = self.t.update(_make_result(self.ActivityType.DISTRACTION), now=_ts(20))
        assert self.t.state == self.SessionState.DISTRACTED
        signal_types = [e.signal_type for e in events]
        assert "distraction_detected" in signal_types

    def test_distraction_before_timeout_stays_working(self):
        self._confirm_session()
        self.t.update(_make_result(self.ActivityType.DISTRACTION), now=_ts(8))
        # 8 - 6 = 2s < 10s timeout → still working
        assert self.t.state == self.SessionState.WORKING

    def test_idle_closes_session(self):
        self._confirm_session()
        events = self.t.update(_make_result(self.ActivityType.IDLE), now=_ts(100))
        assert self.t.state == self.SessionState.IDLE
        signal_types = [e.signal_type for e in events]
        assert "session_ended" in signal_types

    def test_session_ended_has_duration(self):
        self._confirm_session()
        events = self.t.update(_make_result(self.ActivityType.IDLE), now=_ts(100))
        ended = next(e for e in events if e.signal_type == "session_ended")
        assert ended.metadata["duration_seconds"] > 0

    def test_session_ended_has_focus_score(self):
        self._confirm_session()
        events = self.t.update(_make_result(self.ActivityType.IDLE), now=_ts(100))
        ended = next(e for e in events if e.signal_type == "session_ended")
        assert 0.0 <= ended.metadata["focus_score"] <= 1.0


class TestSessionTrackerContextSwitch:
    """context_switch events are emitted on category change within session."""

    def test_context_switch_emitted(self):
        from AINDY.watcher.session_tracker import SessionTracker
        from AINDY.watcher.classifier import ActivityType
        t = SessionTracker(confirmation_delay=5.0, distraction_timeout=999.0)
        # Confirm session
        t.update(_make_result(ActivityType.WORK, app="cursor.exe"), now=_ts(0))
        t.update(_make_result(ActivityType.WORK, app="cursor.exe"), now=_ts(6))
        # Switch to communication
        events = t.update(
            _make_result(ActivityType.COMMUNICATION, app="slack.exe"), now=_ts(7)
        )
        signal_types = [e.signal_type for e in events]
        assert "context_switch" in signal_types

    def test_no_context_switch_same_app(self):
        from AINDY.watcher.session_tracker import SessionTracker
        from AINDY.watcher.classifier import ActivityType
        t = SessionTracker(confirmation_delay=5.0, distraction_timeout=999.0)
        t.update(_make_result(ActivityType.WORK, app="cursor.exe"), now=_ts(0))
        t.update(_make_result(ActivityType.WORK, app="cursor.exe"), now=_ts(6))
        events = t.update(_make_result(ActivityType.WORK, app="cursor.exe"), now=_ts(7))
        signal_types = [e.signal_type for e in events]
        assert "context_switch" not in signal_types


class TestSessionTrackerRecovery:
    """RECOVERING state — focus_achieved emitted after recovery_delay."""

    def test_focus_achieved_after_recovery(self):
        from AINDY.watcher.session_tracker import SessionTracker, SessionState
        from AINDY.watcher.classifier import ActivityType
        t = SessionTracker(confirmation_delay=5.0, distraction_timeout=10.0, recovery_delay=5.0)
        # Confirm session
        t.update(_make_result(ActivityType.WORK), now=_ts(0))
        t.update(_make_result(ActivityType.WORK), now=_ts(6))
        # Trigger distraction
        t.update(_make_result(ActivityType.DISTRACTION), now=_ts(20))
        assert t.state == SessionState.DISTRACTED
        # Start recovery
        t.update(_make_result(ActivityType.WORK), now=_ts(21))
        assert t.state == SessionState.RECOVERING
        # Complete recovery
        events = t.update(_make_result(ActivityType.WORK), now=_ts(27))
        assert t.state == SessionState.WORKING
        signal_types = [e.signal_type for e in events]
        assert "focus_achieved" in signal_types


# ---------------------------------------------------------------------------
# ── WatcherRouter tests (backend API) ─────────────────────────────────────────
# ---------------------------------------------------------------------------

@pytest.fixture
def watcher_mock_db(app):
    """
    Reload-safe mock_db for watcher_router tests.

    Uses sys.modules to get the pre-reload get_db reference from watcher_router
    so importlib.reload(db.database) in test_sprint6_sprint7 does not break
    the DI override.
    """
    import sys
    mod = sys.modules.get("routes.watcher_router")
    if mod is None:
        from AINDY.db.database import get_db as _get_db
        target_get_db = _get_db
    else:
        target_get_db = mod.get_db

    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.filter_by.return_value = db
    db.first.return_value = None
    db.all.return_value = []
    db.add.return_value = None
    db.commit.return_value = None
    db.refresh.return_value = None
    db.rollback.return_value = None
    db.offset.return_value = db
    db.limit.return_value = db
    db.order_by.return_value = db

    app.dependency_overrides[target_get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(target_get_db, None)


_VALID_SIGNAL = {
    "signal_type": "session_started",
    "session_id": "550e8400-e29b-41d4-a716-446655440001",
    "timestamp": "2026-03-24T09:00:00+00:00",
    "app_name": "cursor",
    "window_title": "main.py",
    "activity_type": "work",
    "metadata": {},
}


def _successful_ingest_response(accepted=1, session_ended_count=0, next_action=None):
    return {
        "status": "SUCCESS",
        "result": {
            "accepted": accepted,
            "session_ended_count": session_ended_count,
            "orchestration": {
                "eta_recalculated": session_ended_count > 0,
                "score_orchestrated": session_ended_count > 0,
                "next_action": next_action,
            },
        },
        "events": [],
        "next_action": next_action,
        "trace_id": "trace-watcher-test",
    }


class TestWatcherRouterAuth:
    """API key auth is required for all watcher endpoints."""

    def test_post_signals_no_key_returns_403_or_401(self, client, watcher_mock_db):
        resp = client.post("/watcher/signals", json={"signals": [_VALID_SIGNAL]})
        assert resp.status_code in (401, 403, 422, 503)

    def test_get_signals_no_key_returns_403_or_401(self, client, watcher_mock_db):
        resp = client.get("/watcher/signals")
        assert resp.status_code in (401, 403, 422, 503)

    def test_post_signals_invalid_key_rejected(self, client, watcher_mock_db):
        resp = client.post(
            "/watcher/signals",
            json={"signals": [_VALID_SIGNAL]},
            headers={"X-API-Key": "invalid-key"},
        )
        assert resp.status_code in (401, 403)


class TestWatcherRouterPost:
    """POST /watcher/signals — persistence and validation."""

    def test_post_valid_signal_returns_201(self, client, watcher_mock_db, api_key_headers):
        with patch("routes.watcher_router.execute_intent", return_value=_successful_ingest_response()):
            resp = client.post(
                "/watcher/signals",
                json={"signals": [_VALID_SIGNAL]},
                headers=api_key_headers,
            )
        assert resp.status_code == 201

    def test_post_returns_accepted_count(self, client, watcher_mock_db, api_key_headers):
        with patch("routes.watcher_router.execute_intent", return_value=_successful_ingest_response()):
            resp = client.post(
                "/watcher/signals",
                json={"signals": [_VALID_SIGNAL]},
                headers=api_key_headers,
            )
        body = resp.json()
        assert "accepted" in body
        assert body["accepted"] == 1

    def test_post_multiple_signals(self, client, watcher_mock_db, api_key_headers):
        signals = [dict(_VALID_SIGNAL), dict(_VALID_SIGNAL)]
        signals[1]["signal_type"] = "heartbeat"
        with patch(
            "routes.watcher_router.execute_intent",
            return_value=_successful_ingest_response(accepted=2),
        ):
            resp = client.post(
                "/watcher/signals",
                json={"signals": signals},
                headers=api_key_headers,
            )
        assert resp.status_code == 201
        assert resp.json()["accepted"] == 2

    def test_post_invalid_signal_type_rejected(self, client, watcher_mock_db, api_key_headers):
        bad = dict(_VALID_SIGNAL, signal_type="unknown_type_xyz")
        resp = client.post(
            "/watcher/signals",
            json={"signals": [bad]},
            headers=api_key_headers,
        )
        assert resp.status_code == 422

    def test_post_invalid_activity_type_rejected(self, client, watcher_mock_db, api_key_headers):
        bad = dict(_VALID_SIGNAL, activity_type="flying")
        resp = client.post(
            "/watcher/signals",
            json={"signals": [bad]},
            headers=api_key_headers,
        )
        assert resp.status_code == 422

    def test_post_invalid_timestamp_rejected(self, client, watcher_mock_db, api_key_headers):
        bad = dict(_VALID_SIGNAL, timestamp="not-a-date")
        resp = client.post(
            "/watcher/signals",
            json={"signals": [bad]},
            headers=api_key_headers,
        )
        assert resp.status_code == 422

    def test_post_empty_batch_rejected(self, client, watcher_mock_db, api_key_headers):
        resp = client.post(
            "/watcher/signals",
            json={"signals": []},
            headers=api_key_headers,
        )
        assert resp.status_code == 422

    def test_post_session_ended_triggers_eta(self, client, watcher_mock_db, api_key_headers):
        """session_ended batches surface orchestration metadata in the response."""
        ended = dict(_VALID_SIGNAL, signal_type="session_ended")
        with patch(
            "routes.watcher_router.execute_intent",
            return_value=_successful_ingest_response(
                session_ended_count=1,
                next_action="review_focus_session",
            ),
        ):
            resp = client.post(
                "/watcher/signals",
                json={"signals": [ended]},
                headers=api_key_headers,
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["session_ended_count"] == 1
        assert body["orchestration"]["eta_recalculated"] is True
        assert body["orchestration"]["next_action"] == "review_focus_session"

    def test_post_non_session_ended_does_not_trigger_eta(self, client, watcher_mock_db, api_key_headers):
        with patch(
            "routes.watcher_router.execute_intent",
            return_value=_successful_ingest_response(session_ended_count=0),
        ):
            resp = client.post(
                "/watcher/signals",
                json={"signals": [_VALID_SIGNAL]},  # session_started
                headers=api_key_headers,
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["orchestration"]["eta_recalculated"] is False

    def test_all_valid_signal_types_accepted(self, client, watcher_mock_db, api_key_headers):
        valid_types = [
            "session_started",
            "session_ended",
            "distraction_detected",
            "focus_achieved",
            "context_switch",
            "heartbeat",
        ]
        for st in valid_types:
            sig = dict(_VALID_SIGNAL, signal_type=st)
            with patch("routes.watcher_router.execute_intent", return_value=_successful_ingest_response()):
                resp = client.post(
                    "/watcher/signals",
                    json={"signals": [sig]},
                    headers=api_key_headers,
                )
            assert resp.status_code == 201, f"Failed for signal_type={st!r}: {resp.json()}"

    def test_post_passes_batch_to_flow_engine(self, client, watcher_mock_db, api_key_headers):
        with patch(
            "routes.watcher_router.execute_intent",
            return_value=_successful_ingest_response(),
        ) as mock_execute:
            resp = client.post(
                "/watcher/signals",
                json={"signals": [_VALID_SIGNAL]},
                headers=api_key_headers,
            )
        assert resp.status_code == 201
        kwargs = mock_execute.call_args.kwargs
        assert kwargs["intent_data"]["workflow_type"] == "watcher_ingest"
        assert kwargs["intent_data"]["signals"][0]["signal_type"] == "session_started"

    def test_post_returns_explicit_response_shape(self, client, watcher_mock_db, api_key_headers):
        with patch("routes.watcher_router.execute_intent", return_value=_successful_ingest_response()):
            resp = client.post(
                "/watcher/signals",
                json={"signals": [_VALID_SIGNAL]},
                headers=api_key_headers,
            )
        body = resp.json()
        body.pop("execution_envelope", None)
        assert set(body.keys()) == {"accepted", "session_ended_count", "orchestration"}


class TestWatcherRouterGet:
    """GET /watcher/signals — query endpoint."""

    def test_get_signals_returns_list(self, client, watcher_mock_db, api_key_headers):
        watcher_mock_db.all.return_value = []
        resp = client.get("/watcher/signals", headers=api_key_headers)
        assert resp.status_code == 200
        data = resp.json()
        data.pop("execution_envelope", None)
        payload = data["signals"] if "signals" in data else data.get("results", data)
        assert isinstance(payload, list)

    def test_get_signals_invalid_type_filter_rejected(self, client, watcher_mock_db, api_key_headers):
        resp = client.get(
            "/watcher/signals?signal_type=invalid_xyz",
            headers=api_key_headers,
        )
        assert resp.status_code == 422

    def test_get_signals_valid_type_filter_accepted(self, client, watcher_mock_db, api_key_headers):
        watcher_mock_db.all.return_value = []
        resp = client.get(
            "/watcher/signals?signal_type=session_started",
            headers=api_key_headers,
        )
        assert resp.status_code == 200

    def test_get_signals_user_id_filter_accepted(self, client, watcher_mock_db, api_key_headers):
        user_id = str(uuid4())
        watcher_mock_db.all.return_value = []
        resp = client.get(
            f"/watcher/signals?user_id={user_id}",
            headers=api_key_headers,
        )
        assert resp.status_code == 200

    def test_get_signals_invalid_user_id_filter_rejected(self, client, watcher_mock_db, api_key_headers):
        resp = client.get(
            "/watcher/signals?user_id=not-a-uuid",
            headers=api_key_headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# ── WatcherConfig tests ───────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestWatcherConfig:

    def test_load_defaults(self):
        from AINDY.watcher.config import load
        cfg = load()
        assert cfg.api_url == "http://localhost:8000"
        assert cfg.poll_interval == 5.0
        assert cfg.batch_size == 20

    def test_dry_run_default_false(self):
        from AINDY.watcher.config import load
        cfg = load()
        assert cfg.dry_run is False

    def test_signals_endpoint_built_from_api_url(self):
        from AINDY.watcher.config import load
        cfg = load()
        assert cfg.signals_endpoint.endswith("/watcher/signals")

    def test_validate_missing_api_key_in_live_mode(self):
        from AINDY.watcher.config import WatcherConfig, validate
        cfg = WatcherConfig(
            api_url="http://localhost:8000",
            api_key="",
            signals_endpoint="http://localhost:8000/watcher/signals",
            poll_interval=5.0,
            flush_interval=10.0,
            batch_size=20,
            confirmation_delay=30.0,
            distraction_timeout=60.0,
            recovery_delay=30.0,
            heartbeat_interval=300.0,
            dry_run=False,
            log_level="INFO",
        )
        errors = validate(cfg)
        assert any("AINDY_API_KEY" in e for e in errors)

    def test_validate_dry_run_no_api_key_ok(self):
        from AINDY.watcher.config import WatcherConfig, validate
        cfg = WatcherConfig(
            api_url="http://localhost:8000",
            api_key="",
            signals_endpoint="http://localhost:8000/watcher/signals",
            poll_interval=5.0,
            flush_interval=10.0,
            batch_size=20,
            confirmation_delay=30.0,
            distraction_timeout=60.0,
            recovery_delay=30.0,
            heartbeat_interval=300.0,
            dry_run=True,
            log_level="INFO",
        )
        errors = validate(cfg)
        assert errors == []

    def test_validate_poll_interval_too_short(self):
        from AINDY.watcher.config import WatcherConfig, validate
        cfg = WatcherConfig(
            api_url="http://localhost:8000",
            api_key="key",
            signals_endpoint="http://localhost:8000/watcher/signals",
            poll_interval=0.5,
            flush_interval=10.0,
            batch_size=20,
            confirmation_delay=30.0,
            distraction_timeout=60.0,
            recovery_delay=30.0,
            heartbeat_interval=300.0,
            dry_run=False,
            log_level="INFO",
        )
        errors = validate(cfg)
        assert any("POLL_INTERVAL" in e for e in errors)

    def test_load_env_override(self, monkeypatch):
        monkeypatch.setenv("AINDY_WATCHER_POLL_INTERVAL", "15")
        monkeypatch.setenv("AINDY_WATCHER_DRY_RUN", "true")
        from AINDY.watcher import config
        import importlib
        importlib.reload(config)
        cfg = config.load()
        assert cfg.poll_interval == 15.0
        assert cfg.dry_run is True


# ---------------------------------------------------------------------------
# ── SignalEmitter dry-run tests ───────────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestSignalEmitterDryRun:
    """Dry-run mode logs signals without making HTTP calls."""

    def _make_event(self, signal_type="session_started"):
        from AINDY.watcher.session_tracker import SessionEvent
        return SessionEvent(
            signal_type=signal_type,
            session_id="test-session-id",
            timestamp="2026-03-24T09:00:00+00:00",
            app_name="cursor",
            window_title="test.py",
            activity_type="work",
            metadata={},
        )

    def test_emit_does_not_raise(self):
        from AINDY.watcher.signal_emitter import SignalEmitter
        emitter = SignalEmitter(
            api_url="http://localhost:8000/watcher/signals",
            api_key="test",
            dry_run=True,
        )
        emitter.emit(self._make_event())  # Should not raise

    def test_emit_many_queues_all(self):
        from AINDY.watcher.signal_emitter import SignalEmitter
        emitter = SignalEmitter(
            api_url="http://localhost:8000/watcher/signals",
            api_key="test",
            dry_run=True,
        )
        events = [self._make_event(st) for st in ["session_started", "heartbeat", "session_ended"]]
        emitter.emit_many(events)
        assert len(emitter._queue) == 3

    def test_queue_overflow_drops_oldest(self):
        from AINDY.watcher.signal_emitter import SignalEmitter
        emitter = SignalEmitter(
            api_url="http://localhost:8000/watcher/signals",
            api_key="test",
            dry_run=True,
            max_queue=3,
        )
        for i in range(5):
            e = self._make_event()
            e.session_id = f"session-{i}"
            emitter.emit(e)
        assert len(emitter._queue) == 3
        # Oldest (session-0, session-1) should be dropped
        remaining_ids = [e.session_id for e in emitter._queue]
        assert "session-0" not in remaining_ids
        assert "session-4" in remaining_ids

    def test_dry_run_send_logs_not_http(self):
        from AINDY.watcher.signal_emitter import SignalEmitter
        emitter = SignalEmitter(
            api_url="http://localhost:8000/watcher/signals",
            api_key="test",
            dry_run=True,
        )
        events = [self._make_event()]
        with patch("httpx.Client") as mock_client:
            emitter._send_with_retry(events)
            mock_client.assert_not_called()

    def test_start_stop_lifecycle(self):
        from AINDY.watcher.signal_emitter import SignalEmitter
        emitter = SignalEmitter(
            api_url="http://localhost:8000/watcher/signals",
            api_key="test",
            dry_run=True,
            flush_interval=60.0,  # long interval — won't flush during test
        )
        emitter.start()
        assert emitter._thread is not None
        assert emitter._thread.is_alive()
        emitter.stop(drain_timeout=1.0)


# ---------------------------------------------------------------------------
# ── Window detector — unit contract ──────────────────────────────────────────
# ---------------------------------------------------------------------------

class TestWindowDetector:
    """get_active_window() never raises and returns WindowInfo or None."""

    def test_never_raises(self):
        from AINDY.watcher.window_detector import get_active_window
        # Should not raise regardless of platform
        result = get_active_window()
        # Result is WindowInfo or None
        assert result is None or hasattr(result, "app_name")

    def test_result_app_name_not_empty_when_returned(self):
        from AINDY.watcher.window_detector import get_active_window, WindowInfo
        result = get_active_window()
        if result is not None:
            assert isinstance(result, WindowInfo)
            assert result.app_name != ""

    def test_window_info_dataclass(self):
        from AINDY.watcher.window_detector import WindowInfo
        w = WindowInfo(app_name="cursor.exe", window_title="test.py", pid=1234)
        assert w.app_name == "cursor.exe"
        assert w.window_title == "test.py"
        assert w.pid == 1234

    def test_window_detector_psutil_fallback(self):
        """When platform detectors return None, psutil fallback is used."""
        import platform
        from AINDY.watcher import window_detector
        from AINDY.watcher.window_detector import WindowInfo

        fake_info = WindowInfo(app_name="python.exe", window_title="", pid=999)

        with patch.object(window_detector, "_detect_windows", return_value=None), \
             patch.object(window_detector, "_detect_macos", return_value=None), \
             patch.object(window_detector, "_detect_linux", return_value=None), \
             patch.object(window_detector, "_detect_psutil_fallback", return_value=fake_info):
            result = window_detector.get_active_window()

        assert result is not None
        assert result.app_name == "python.exe"
