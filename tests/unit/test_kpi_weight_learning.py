from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from apps.automation.infinity_loop import LoopAdjustment


def _seed_adjustments(
    db_session,
    *,
    user_id,
    count: int,
    decision_type: str,
    prediction_accuracy: int,
):
    now = datetime.now(timezone.utc)
    for idx in range(count):
        db_session.add(
            LoopAdjustment(
                user_id=user_id,
                trigger_event="manual",
                decision_type=decision_type,
                score_snapshot={"master_score": 50.0},
                prediction_accuracy=prediction_accuracy,
                applied_at=now - timedelta(minutes=idx),
                evaluated_at=now - timedelta(minutes=idx),
                adjustment_payload={"next_action": {"type": decision_type}},
            )
        )
    db_session.commit()


def test_get_effective_weights_returns_global_defaults_on_new_user(db_session, test_user):
    from apps.analytics.services.kpi_weight_service import get_effective_weights
    from apps.analytics.user_score import KPI_WEIGHTS

    weights = get_effective_weights(db_session, str(test_user.id))

    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert weights["execution_speed"] == KPI_WEIGHTS["execution_speed"]
    assert weights == KPI_WEIGHTS


def test_adapt_kpi_weights_returns_insufficient_data_with_few_adjustments(db_session, test_user):
    from apps.analytics.services.kpi_weight_service import adapt_kpi_weights
    from apps.analytics.user_score import KPI_WEIGHT_MIN_SAMPLES

    _seed_adjustments(
        db_session,
        user_id=test_user.id,
        count=KPI_WEIGHT_MIN_SAMPLES - 1,
        decision_type="reprioritize_tasks",
        prediction_accuracy=90,
    )

    result = adapt_kpi_weights(db_session, str(test_user.id))

    assert result["status"] == "insufficient_data"


def test_adapt_kpi_weights_nudges_up_on_high_accuracy(db_session, test_user):
    from apps.analytics.services.kpi_weight_service import adapt_kpi_weights, get_or_create_user_weights
    from apps.analytics.user_score import KPI_WEIGHT_MIN_SAMPLES

    _seed_adjustments(
        db_session,
        user_id=test_user.id,
        count=KPI_WEIGHT_MIN_SAMPLES + 1,
        decision_type="reprioritize_tasks",
        prediction_accuracy=90,
    )

    result = adapt_kpi_weights(db_session, str(test_user.id))
    row = get_or_create_user_weights(db_session, str(test_user.id))

    assert result["status"] == "adapted"
    assert row.execution_speed_weight > 0.25


def test_adapt_kpi_weights_nudges_down_on_low_accuracy(db_session, test_user):
    from apps.analytics.services.kpi_weight_service import adapt_kpi_weights, get_or_create_user_weights
    from apps.analytics.user_score import KPI_WEIGHT_MIN_SAMPLES

    _seed_adjustments(
        db_session,
        user_id=test_user.id,
        count=KPI_WEIGHT_MIN_SAMPLES + 1,
        decision_type="reprioritize_tasks",
        prediction_accuracy=20,
    )

    result = adapt_kpi_weights(db_session, str(test_user.id))
    row = get_or_create_user_weights(db_session, str(test_user.id))

    assert result["status"] == "adapted"
    assert row.execution_speed_weight < 0.25


def test_adapted_weights_sum_to_one(db_session, test_user):
    from apps.analytics.services.kpi_weight_service import adapt_kpi_weights
    from apps.analytics.user_score import KPI_WEIGHT_MIN_SAMPLES

    _seed_adjustments(
        db_session,
        user_id=test_user.id,
        count=KPI_WEIGHT_MIN_SAMPLES + 1,
        decision_type="review_plan",
        prediction_accuracy=90,
    )

    result = adapt_kpi_weights(db_session, str(test_user.id))

    assert abs(sum(result["weights"].values()) - 1.0) < 1e-5


def test_weight_bounds_enforced(db_session, test_user):
    from apps.analytics.services.kpi_weight_service import adapt_kpi_weights
    from apps.analytics.user_score import KPI_WEIGHT_MAX, KPI_WEIGHT_MIN, KPI_WEIGHT_MIN_SAMPLES

    _seed_adjustments(
        db_session,
        user_id=test_user.id,
        count=max(KPI_WEIGHT_MIN_SAMPLES + 10, 50),
        decision_type="create_new_task",
        prediction_accuracy=90,
    )

    result = adapt_kpi_weights(db_session, str(test_user.id))

    assert result["status"] == "adapted"
    for value in result["weights"].values():
        assert KPI_WEIGHT_MIN <= value <= KPI_WEIGHT_MAX


def test_adapt_respects_cooldown(db_session, test_user):
    from apps.analytics.services.kpi_weight_service import adapt_kpi_weights
    from apps.analytics.user_score import KPI_WEIGHT_MIN_SAMPLES

    _seed_adjustments(
        db_session,
        user_id=test_user.id,
        count=KPI_WEIGHT_MIN_SAMPLES + 1,
        decision_type="reprioritize_tasks",
        prediction_accuracy=90,
    )

    first = adapt_kpi_weights(db_session, str(test_user.id))
    second = adapt_kpi_weights(db_session, str(test_user.id))

    assert first["status"] == "adapted"
    assert second["status"] == "skipped"
    assert second["reason"] == "cooldown"


def test_calculate_infinity_score_uses_per_user_weights(db_session, mocker):
    from apps.analytics.services.infinity_service import calculate_infinity_score, orchestrator_score_context

    custom_weights = {
        "execution_speed": 0.50,
        "decision_efficiency": 0.20,
        "ai_productivity_boost": 0.10,
        "focus_quality": 0.10,
        "masterplan_progress": 0.10,
    }

    mocker.patch("apps.analytics.services.infinity_service.calculate_execution_speed", return_value=(80.0, 5))
    mocker.patch("apps.analytics.services.infinity_service.calculate_decision_efficiency", return_value=(60.0, 5))
    mocker.patch("apps.analytics.services.infinity_service.calculate_ai_productivity_boost", return_value=(40.0, 5))
    mocker.patch("apps.analytics.services.infinity_service.calculate_focus_quality", return_value=(20.0, 5))
    mocker.patch("apps.analytics.services.infinity_service.calculate_masterplan_progress", return_value=(10.0, 5))
    mocker.patch("apps.analytics.services.kpi_weight_service.get_effective_weights", return_value=custom_weights)

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.add = MagicMock()
    mock_db.flush = MagicMock()

    with orchestrator_score_context():
        result = calculate_infinity_score("test-user", mock_db, trigger_event="manual")

    expected = round(
        80.0 * 0.50 +
        60.0 * 0.20 +
        40.0 * 0.10 +
        20.0 * 0.10 +
        10.0 * 0.10,
        2,
    )
    assert result is not None
    assert result["weights"] == custom_weights
    assert result["master_score"] == expected


def test_kpi_weights_sum_invariant_still_holds():
    from apps.analytics.user_score import KPI_WEIGHTS

    assert abs(sum(KPI_WEIGHTS.values()) - 1.0) < 1e-9


def test_get_kpi_weights_endpoint_returns_200_with_auth(client, auth_headers, mocker):
    from apps.analytics.routes import analytics_router as router_mod

    async def _fake_execute_with_pipeline(*args, **kwargs):
        request = kwargs.get("request")
        if request is not None:
            request.state.execution_context = object()
        return kwargs["handler"](None)

    mocker.patch.object(router_mod, "execute_with_pipeline", side_effect=_fake_execute_with_pipeline)
    mocker.patch(
        "apps.analytics.services.kpi_weight_service.get_effective_weights",
        return_value={
            "execution_speed": 0.25,
            "decision_efficiency": 0.25,
            "ai_productivity_boost": 0.20,
            "focus_quality": 0.15,
            "masterplan_progress": 0.15,
        },
    )
    row = MagicMock()
    row.adapted_count = 0
    row.last_adapted_at = None
    mocker.patch("apps.analytics.services.kpi_weight_service.get_or_create_user_weights", return_value=row)

    response = client.get("/analytics/kpi-weights", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert "weights" in body
    assert body["is_personalized"] is False


def test_post_kpi_weights_adapt_returns_200_with_auth(client, auth_headers, mocker):
    from apps.analytics.routes import analytics_router as router_mod

    async def _fake_execute_with_pipeline(*args, **kwargs):
        request = kwargs.get("request")
        if request is not None:
            request.state.execution_context = object()
        return kwargs["handler"](None)

    mocker.patch.object(router_mod, "execute_with_pipeline", side_effect=_fake_execute_with_pipeline)
    mocker.patch(
        "apps.analytics.services.kpi_weight_service.adapt_kpi_weights",
        return_value={
            "status": "adapted",
            "adapted_count": 1,
            "nudges_applied": 4,
            "weights": {
                "execution_speed": 0.28,
                "decision_efficiency": 0.28,
                "ai_productivity_boost": 0.18,
                "focus_quality": 0.13,
                "masterplan_progress": 0.13,
            },
        },
    )

    response = client.post("/analytics/kpi-weights/adapt", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "adapted"
