from __future__ import annotations

from unittest.mock import sentinel
from uuid import uuid4


def test_get_user_metrics_uses_registered_kpi_snapshot(monkeypatch):
    from AINDY.platform_layer import registry
    from apps.identity.services import identity_boot_service

    user_id = uuid4()
    observed = {}

    def fake_snapshot(*, user_id, db):
        observed["user_id"] = user_id
        observed["db"] = db
        return {
            "master_score": 88.0,
            "execution_speed": 80.0,
            "decision_efficiency": 82.0,
            "ai_productivity_boost": 85.0,
            "focus_quality": 90.0,
            "masterplan_progress": 83.0,
            "confidence": "high",
        }

    monkeypatch.setattr(
        registry,
        "get_job",
        lambda name: fake_snapshot if name == "analytics.kpi_snapshot" else None,
    )

    result = identity_boot_service.get_user_metrics(user_id, sentinel.db)

    assert observed == {"user_id": user_id, "db": sentinel.db}
    assert result == {
        "user_id": str(user_id),
        "score": 88.0,
        "trajectory": "high",
        "master_score": 88.0,
        "kpis": {
            "execution_speed": 80.0,
            "decision_efficiency": 82.0,
            "ai_productivity_boost": 85.0,
            "focus_quality": 90.0,
            "masterplan_progress": 83.0,
        },
        "metadata": {
            "confidence": "high",
            "data_points_used": None,
            "trigger_event": None,
            "calculated_at": None,
        },
    }
