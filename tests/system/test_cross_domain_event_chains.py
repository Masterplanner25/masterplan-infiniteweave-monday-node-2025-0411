from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest


def _register_analytics_handlers():
    """Register analytics event handlers as bootstrap would."""
    from AINDY.core.system_event_types import SystemEventTypes
    from AINDY.platform_layer.registry import _event_handlers, register_event_handler
    import apps.analytics.bootstrap as ab

    _event_handlers.pop(SystemEventTypes.MASTERPLAN_GOAL_STATE_CHANGED, None)
    register_event_handler(
        SystemEventTypes.MASTERPLAN_GOAL_STATE_CHANGED,
        ab._handle_goal_state_changed,
    )


def _register_masterplan_handlers():
    """Register masterplan event handlers as bootstrap would."""
    from AINDY.core.system_event_types import SystemEventTypes
    from AINDY.platform_layer.registry import _event_handlers, register_event_handler
    import apps.masterplan.bootstrap as mb

    _event_handlers.pop(SystemEventTypes.ANALYTICS_SCORE_UPDATED, None)
    register_event_handler(
        SystemEventTypes.ANALYTICS_SCORE_UPDATED,
        mb._handle_analytics_score_updated,
    )


@pytest.fixture(autouse=True)
def _cleanup_event_handlers():
    yield
    from AINDY.core.system_event_types import SystemEventTypes
    from AINDY.platform_layer.registry import _event_handlers

    _event_handlers.pop(SystemEventTypes.ANALYTICS_SCORE_UPDATED, None)
    _event_handlers.pop(SystemEventTypes.MASTERPLAN_GOAL_STATE_CHANGED, None)


def test_score_updated_event_reaches_masterplan_goal_handler(db_session, test_user):
    """
    CHAIN A: When analytics emits ANALYTICS_SCORE_UPDATED, masterplan's
    handle_score_updated() must be called with a payload containing user_id and score.
    This verifies the event handler registration and dispatch are wired correctly
    across the analytics→masterplan domain boundary.
    """
    _register_masterplan_handlers()

    from AINDY.core.system_event_types import SystemEventTypes
    from AINDY.platform_layer.registry import emit_event

    payload = {
        "user_id": str(test_user.id),
        "score": 72.5,
        "kpi_breakdown": {
            "execution_speed": 70.0,
            "decision_efficiency": 75.0,
            "ai_productivity_boost": 68.0,
            "focus_quality": 74.0,
            "masterplan_progress": 75.5,
        },
        "computed_at": "2026-01-01T00:00:00+00:00",
    }

    call_log: list[dict] = []

    with patch(
        "apps.masterplan.bootstrap._handle_analytics_score_updated",
        side_effect=lambda ctx: call_log.append(ctx),
    ):
        _register_masterplan_handlers()
        emit_event(SystemEventTypes.ANALYTICS_SCORE_UPDATED, payload)

    assert len(call_log) == 1, (
        f"Expected handle_score_updated to be called once, got {len(call_log)}. "
        "The ANALYTICS_SCORE_UPDATED event handler is not reaching masterplan."
    )
    received = call_log[0]
    assert str(received.get("user_id")) == str(test_user.id), (
        f"user_id mismatch: expected {test_user.id}, got {received.get('user_id')}"
    )
    assert received.get("score") == 72.5


def test_goal_state_event_reaches_analytics_orchestrator(db_session, test_user):
    """
    CHAIN B: When masterplan emits MASTERPLAN_GOAL_STATE_CHANGED, analytics'
    handle_goal_state_changed() must be invoked with the correct payload.
    This verifies the masterplan→analytics boundary is wired via the event registry.
    """
    _register_analytics_handlers()

    from AINDY.core.system_event_types import SystemEventTypes
    from AINDY.platform_layer.registry import emit_event

    payload = {
        "user_id": str(test_user.id),
        "goal_id": "test-goal-001",
        "new_state": "in_progress",
        "db": db_session,
    }

    call_log: list[dict] = []

    with patch(
        "apps.analytics.services.orchestration.infinity_orchestrator.handle_goal_state_changed",
        side_effect=lambda p: call_log.append(p),
    ):
        _register_analytics_handlers()
        emit_event(SystemEventTypes.MASTERPLAN_GOAL_STATE_CHANGED, payload)

    assert len(call_log) == 1, (
        f"Expected handle_goal_state_changed to be called once, got {len(call_log)}. "
        "The MASTERPLAN_GOAL_STATE_CHANGED event handler is not reaching analytics."
    )
    assert str(call_log[0].get("user_id")) == str(test_user.id)


def test_bidirectional_event_registration_no_cross_fire(db_session, test_user):
    """
    CHAIN A+B: Register both directions simultaneously. Emitting one event must
    not trigger the handler for the other. The registry must not cross-wire
    ANALYTICS_SCORE_UPDATED and MASTERPLAN_GOAL_STATE_CHANGED.
    """
    _register_analytics_handlers()
    _register_masterplan_handlers()

    from AINDY.core.system_event_types import SystemEventTypes
    from AINDY.platform_layer.registry import emit_event

    analytics_calls: list[dict] = []
    masterplan_calls: list[dict] = []

    with patch(
        "apps.analytics.bootstrap._handle_goal_state_changed",
        side_effect=lambda ctx: analytics_calls.append(ctx),
    ), patch(
        "apps.masterplan.bootstrap._handle_analytics_score_updated",
        side_effect=lambda ctx: masterplan_calls.append(ctx),
    ):
        _register_analytics_handlers()
        _register_masterplan_handlers()

        emit_event(
            SystemEventTypes.MASTERPLAN_GOAL_STATE_CHANGED,
            {"user_id": str(test_user.id), "goal_id": "g-001", "db": db_session},
        )

    assert len(analytics_calls) == 1, "Goal state event must reach analytics handler"
    assert len(masterplan_calls) == 0, (
        "Goal state event must NOT trigger the analytics score handler — "
        "event types are being cross-wired."
    )


def test_update_goal_progress_emits_goal_state_changed(db_session, test_user):
    """
    Verifies that the masterplan service layer emits MASTERPLAN_GOAL_STATE_CHANGED
    when update_goal_progress() is called. This tests that the emit call in
    goal_service.py actually fires, not just that the handler is registered.
    """
    from AINDY.core.system_event_types import SystemEventTypes
    from AINDY.platform_layer.registry import emit_event as real_emit_event
    from apps.masterplan.models import Goal

    goal_id = uuid.uuid4()
    goal = Goal(
        id=goal_id,
        user_id=test_user.id,
        name="Test goal for event chain",
        status="active",
        goal_type="strategic",
        priority=0.5,
        success_metric={},
    )
    db_session.add(goal)
    db_session.commit()

    emitted_events: list[dict] = []

    def _capture_emit(event_type, payload=None):
        emitted_events.append({"event_type": event_type, "payload": payload})
        return real_emit_event(event_type, payload)

    with patch(
        "apps.masterplan.services.goal_service.emit_event",
        side_effect=_capture_emit,
    ):
        from apps.masterplan.services.goal_service import update_goal_progress

        update_goal_progress(
            db=db_session,
            goal_id=goal_id,
            user_id=str(test_user.id),
            result={"progress_delta": 1.0},
        )

    goal_state_events = [
        event
        for event in emitted_events
        if event["event_type"] == SystemEventTypes.MASTERPLAN_GOAL_STATE_CHANGED
    ]
    assert len(goal_state_events) >= 1, (
        "update_goal_progress must emit MASTERPLAN_GOAL_STATE_CHANGED. "
        f"Emitted events: {[event['event_type'] for event in emitted_events]}"
    )
    payload = goal_state_events[0]["payload"] or {}
    assert str(payload.get("user_id")) == str(test_user.id)
