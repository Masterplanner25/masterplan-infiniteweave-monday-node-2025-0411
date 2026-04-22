from __future__ import annotations

import logging


def test_handle_score_updated_accepts_valid_payload(caplog):
    from apps.masterplan.services.goal_service import handle_score_updated

    payload = {
        "user_id": "user-1",
        "score": 82.5,
        "kpi_breakdown": {
            "execution_speed": 80.0,
            "decision_efficiency": 81.0,
        },
        "computed_at": "2026-04-20T12:00:00+00:00",
    }

    with caplog.at_level(logging.DEBUG):
        result = handle_score_updated(payload)

    assert result is None
    assert "observed analytics score update" in caplog.text
