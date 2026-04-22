from __future__ import annotations

from unittest.mock import MagicMock


def test_calculate_infinity_score_emits_score_updated_event(mocker):
    from AINDY.core.system_event_types import SystemEventTypes
    from apps.analytics.services.infinity_service import calculate_infinity_score, orchestrator_score_context

    for name, value in (
        ("calculate_execution_speed", 75.0),
        ("calculate_decision_efficiency", 65.0),
        ("calculate_ai_productivity_boost", 55.0),
        ("calculate_focus_quality", 45.0),
        ("calculate_masterplan_progress", 35.0),
    ):
        mocker.patch(f"apps.analytics.services.infinity_service.{name}", return_value=(value, 5))

    emit_event = mocker.patch("apps.analytics.services.infinity_service.emit_event")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with orchestrator_score_context():
        result = calculate_infinity_score("test-user", mock_db, trigger_event="manual")

    assert result is not None
    emit_event.assert_called_once()
    event_type, payload = emit_event.call_args.args
    assert event_type == SystemEventTypes.ANALYTICS_SCORE_UPDATED
    assert payload["user_id"] == "test-user"
    assert payload["score"] == result["master_score"]
    assert payload["kpi_breakdown"] == result["kpis"]
    assert payload["computed_at"] == result["metadata"]["calculated_at"]
