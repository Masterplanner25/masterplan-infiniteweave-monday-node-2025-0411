from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from AINDY.agents import stuck_run_watchdog


class _DummySession:
    def close(self) -> None:
        return None


def _reset_last_scan_result() -> None:
    stuck_run_watchdog._LAST_SCAN_RESULT.update(
        {
            "last_run_at": None,
            "recovered": 0,
            "dead_lettered": 0,
            "had_error": False,
            "error_message": None,
        }
    )


def test_watchdog_emits_system_event_on_success(monkeypatch):
    _reset_last_scan_result()
    emit_mock = MagicMock()
    monkeypatch.setattr("AINDY.db.database.SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        "AINDY.agents.stuck_run_service.scan_and_recover_stuck_runs",
        lambda *args, **kwargs: {"recovered": 2, "dead_lettered": 0},
    )
    monkeypatch.setattr("AINDY.core.system_event_service.emit_system_event", emit_mock)

    stuck_run_watchdog.watchdog_scan()

    emit_mock.assert_called_once()
    assert emit_mock.call_args.kwargs["event_type"] == "watchdog.scan.completed"
    assert emit_mock.call_args.kwargs["payload"]["recovered"] == 2


def test_watchdog_emits_system_event_on_no_work(monkeypatch):
    _reset_last_scan_result()
    emit_mock = MagicMock()
    monkeypatch.setattr("AINDY.db.database.SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        "AINDY.agents.stuck_run_service.scan_and_recover_stuck_runs",
        lambda *args, **kwargs: {"recovered": 0, "dead_lettered": 0},
    )
    monkeypatch.setattr("AINDY.core.system_event_service.emit_system_event", emit_mock)

    stuck_run_watchdog.watchdog_scan()

    emit_mock.assert_called_once()


def test_watchdog_updates_last_scan_result(monkeypatch):
    _reset_last_scan_result()
    monkeypatch.setattr("AINDY.db.database.SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        "AINDY.agents.stuck_run_service.scan_and_recover_stuck_runs",
        lambda *args, **kwargs: {"recovered": 3, "dead_lettered": 1},
    )
    monkeypatch.setattr("AINDY.core.system_event_service.emit_system_event", MagicMock())

    stuck_run_watchdog.watchdog_scan()

    result = stuck_run_watchdog.get_last_scan_result()
    assert result["recovered"] == 3
    assert result["dead_lettered"] == 1
    assert result["last_run_at"] is not None
    assert result["had_error"] is False


def test_watchdog_records_error_in_last_scan_result(monkeypatch):
    _reset_last_scan_result()
    failure_mock = MagicMock()
    monkeypatch.setattr("AINDY.db.database.SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        "AINDY.agents.stuck_run_service.scan_and_recover_stuck_runs",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db error")),
    )
    monkeypatch.setattr("AINDY.core.observability_events.emit_recovery_failure", failure_mock)

    stuck_run_watchdog.watchdog_scan()

    result = stuck_run_watchdog.get_last_scan_result()
    assert result["had_error"] is True
    assert "db error" in str(result["error_message"])
    failure_mock.assert_called_once()


def test_event_emission_failure_does_not_abort_watchdog(monkeypatch):
    _reset_last_scan_result()
    monkeypatch.setattr("AINDY.db.database.SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        "AINDY.agents.stuck_run_service.scan_and_recover_stuck_runs",
        lambda *args, **kwargs: {"recovered": 1, "dead_lettered": 0},
    )
    monkeypatch.setattr(
        "AINDY.core.system_event_service.emit_system_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("event write failed")),
    )

    stuck_run_watchdog.watchdog_scan()

    result = stuck_run_watchdog.get_last_scan_result()
    assert result["recovered"] == 1
    assert result["had_error"] is False
