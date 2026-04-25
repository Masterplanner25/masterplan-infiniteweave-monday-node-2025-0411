from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from AINDY.db.models.system_event import SystemEvent
from AINDY.platform_layer.event_trace_service import link_events as platform_link_events


def test_rippletrace_link_events_delegates_to_platform():
    from apps.rippletrace.services.rippletrace_service import link_events as rt_link
    from AINDY.platform_layer.event_trace_service import link_events as pt_link

    assert rt_link is pt_link


def test_generate_trace_insights_returns_required_keys(db_session):
    from apps.rippletrace.services.rippletrace_service import generate_trace_insights

    result = generate_trace_insights(db_session, "nonexistent-trace")

    for key in [
        "root_cause",
        "dominant_path",
        "failure_clusters",
        "summary",
        "recommendations",
        "predictions",
        "drop_point_recommendations",
        "ripple_span",
    ]:
        assert key in result, f"Missing key: {key}"
    assert result["predictions"] == []


def test_generate_trace_insights_includes_prediction_when_dp_id_present(
    db_session,
    test_user,
):
    from apps.rippletrace.services.rippletrace_service import generate_trace_insights

    event = SystemEvent(
        id=uuid.uuid4(),
        type="rippletrace.drop_point.finalized",
        user_id=test_user.id,
        trace_id="trace-with-drop-point",
        payload={"drop_point_id": "dp-1"},
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()

    with patch(
        "apps.rippletrace.services.prediction_engine.predict_drop_point",
        return_value={"drop_point_id": "dp-1", "prediction": "likely_to_spike", "confidence": 0.8},
    ), patch(
        "apps.rippletrace.services.recommendation_engine.recommend_for_drop_point",
        return_value={
            "drop_point_id": "dp-1",
            "action": "amplify",
            "priority": "high",
            "recommendations": ["Post follow-up content within 24 hours"],
        },
    ):
        result = generate_trace_insights(db_session, "trace-with-drop-point")

    assert result["predictions"]
    assert "outlook" in result["summary"].lower()
    assert result["drop_point_recommendations"]


def test_extract_drop_point_ids_from_events():
    from apps.rippletrace.services.rippletrace_service import (
        _extract_drop_point_ids_from_events,
    )

    events = [
        {"payload": {"drop_point_id": "dp1"}},
        {"payload": {"drop_point_id": "dp2"}},
        {"payload": {"drop_point_id": "dp1"}},
        {"payload": {}},
    ]

    result = _extract_drop_point_ids_from_events(events)

    assert result == ["dp1", "dp2"]


def test_get_upstream_causes_delegates_to_get_upstream_relationships(
    db_session,
    test_user,
):
    from apps.rippletrace.services.rippletrace_service import get_upstream_causes

    source_event = SystemEvent(
        id=uuid.uuid4(),
        type="execution.started",
        user_id=test_user.id,
        trace_id="trace-upstream",
        payload={},
        timestamp=datetime.now(timezone.utc),
    )
    target_event = SystemEvent(
        id=uuid.uuid4(),
        type="execution.failed",
        user_id=test_user.id,
        trace_id="trace-upstream",
        payload={},
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add_all([source_event, target_event])
    db_session.commit()

    platform_link_events(
        db_session,
        source_event.id,
        target_event.id,
        relationship_type="caused_by",
    )
    db_session.commit()

    result = get_upstream_causes(db_session, target_event.id)

    assert len(result) == 1
    assert result[0]["source"] == str(source_event.id)
    assert result[0]["target"] == str(target_event.id)
