from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.automation.infinity_loop import LoopAdjustment


def _seed_score_history(
    db_session,
    *,
    user_id,
    count: int,
    execution_speed: float = 40.0,
    decision_efficiency: float = 40.0,
    ai_productivity_boost: float = 40.0,
    focus_quality: float = 40.0,
    masterplan_progress: float = 40.0,
):
    from apps.analytics.models import ScoreHistory

    now = datetime.now(timezone.utc)
    for idx in range(count):
        db_session.add(
            ScoreHistory(
                user_id=user_id,
                master_score=50.0,
                execution_speed_score=execution_speed,
                decision_efficiency_score=decision_efficiency,
                ai_productivity_boost_score=ai_productivity_boost,
                focus_quality_score=focus_quality,
                masterplan_progress_score=masterplan_progress,
                trigger_event="manual",
                score_delta=0.0,
                calculated_at=now - timedelta(hours=idx),
            )
        )
    db_session.commit()


def _seed_adjustments(
    db_session,
    *,
    user_id,
    count: int,
    decision_type: str,
    actual_score: int,
    expected_score: int,
):
    now = datetime.now(timezone.utc)
    for idx in range(count):
        db_session.add(
            LoopAdjustment(
                user_id=user_id,
                trigger_event="manual",
                decision_type=decision_type,
                score_snapshot={"master_score": expected_score},
                expected_score=expected_score,
                actual_score=actual_score,
                prediction_accuracy=80,
                applied_at=now - timedelta(minutes=idx),
                evaluated_at=now - timedelta(minutes=idx),
                adjustment_payload={"next_action": {"type": decision_type}},
            )
        )
    db_session.commit()


def test_get_effective_thresholds_returns_hardcoded_defaults_for_new_user(db_session, test_user):
    from apps.analytics.services.policy_adaptation_service import get_effective_thresholds

    result = get_effective_thresholds(db_session, str(test_user.id))

    assert result["kpi_low"]["execution_speed"] == 40.0
    assert result["is_personalized"] is False


def test_adapt_policy_thresholds_returns_insufficient_data_without_history(db_session, test_user):
    from apps.analytics.services.policy_adaptation_service import adapt_policy_thresholds

    result = adapt_policy_thresholds(db_session, str(test_user.id))

    assert result["status"] == "insufficient_data"


def test_adapt_threshold_below_p25_of_score_history(db_session, test_user):
    from apps.analytics.services.policy_adaptation_service import adapt_policy_thresholds

    _seed_score_history(
        db_session,
        user_id=test_user.id,
        count=15,
        execution_speed=30.0,
    )

    result = adapt_policy_thresholds(db_session, str(test_user.id))

    assert result["status"] == "adapted"
    assert result["thresholds"]["execution_speed"] < 40.0


def test_adapted_threshold_bounded_by_floor(db_session, test_user):
    from apps.analytics.services.policy_adaptation_service import (
        THRESHOLD_FLOOR,
        adapt_policy_thresholds,
    )

    _seed_score_history(
        db_session,
        user_id=test_user.id,
        count=15,
        execution_speed=5.0,
    )

    result = adapt_policy_thresholds(db_session, str(test_user.id))

    assert result["thresholds"]["execution_speed"] >= THRESHOLD_FLOOR


def test_adapted_threshold_bounded_by_ceiling(db_session, test_user):
    from apps.analytics.services.policy_adaptation_service import (
        THRESHOLD_CEILING,
        adapt_policy_thresholds,
    )

    _seed_score_history(
        db_session,
        user_id=test_user.id,
        count=15,
        execution_speed=99.0,
    )

    result = adapt_policy_thresholds(db_session, str(test_user.id))

    assert result["thresholds"]["execution_speed"] <= THRESHOLD_CEILING


def test_offset_adaptation_from_loop_adjustments(db_session, test_user):
    from apps.analytics.services.policy_adaptation_service import adapt_policy_thresholds

    _seed_score_history(db_session, user_id=test_user.id, count=15, execution_speed=45.0)
    _seed_adjustments(
        db_session,
        user_id=test_user.id,
        count=7,
        decision_type="reprioritize_tasks",
        actual_score=60,
        expected_score=55,
    )

    result = adapt_policy_thresholds(db_session, str(test_user.id))

    assert result["status"] == "adapted"
    assert result["offsets"]["reprioritize_tasks"] > 1.5


def test_adapt_respects_cooldown(db_session, test_user):
    from apps.analytics.services.policy_adaptation_service import adapt_policy_thresholds

    _seed_score_history(db_session, user_id=test_user.id, count=15, execution_speed=45.0)
    _seed_adjustments(
        db_session,
        user_id=test_user.id,
        count=7,
        decision_type="review_plan",
        actual_score=58,
        expected_score=55,
    )

    first = adapt_policy_thresholds(db_session, str(test_user.id))
    second = adapt_policy_thresholds(db_session, str(test_user.id))

    assert first["status"] == "adapted"
    assert second["status"] == "skipped"
    assert second["reason"] == "cooldown"


def test_decide_uses_adaptive_threshold():
    from apps.analytics.services.infinity_loop import _decide

    result_type, _ = _decide(
        {
            "execution_speed": 25.0,
            "decision_efficiency": 70.0,
            "focus_quality": 70.0,
            "ai_productivity_boost": 70.0,
            "masterplan_progress": 70.0,
        },
        kpi_low={
            "execution_speed": 20.0,
            "decision_efficiency": 40.0,
            "ai_productivity_boost": 40.0,
            "focus_quality": 40.0,
            "masterplan_progress": 40.0,
        },
    )

    assert result_type == "continue_highest_priority_task"


def test_existing_hardcoded_threshold_still_works_without_adaptation():
    from apps.analytics.services.infinity_loop import _decide

    result_type, _ = _decide(
        {
            "execution_speed": 35.0,
            "decision_efficiency": 70.0,
            "focus_quality": 70.0,
            "ai_productivity_boost": 70.0,
            "masterplan_progress": 70.0,
        },
    )

    assert result_type == "reprioritize_tasks"


def test_get_policy_thresholds_endpoint_returns_200_with_auth(client, auth_headers, mocker):
    from apps.analytics.routes import analytics_router as router_mod

    async def _fake_execute_with_pipeline(*args, **kwargs):
        return kwargs["handler"](None)

    mocker.patch.object(router_mod, "execute_with_pipeline", side_effect=_fake_execute_with_pipeline)
    mocker.patch(
        "apps.analytics.services.policy_adaptation_service.get_effective_thresholds",
        return_value={
            "kpi_low": {
                "execution_speed": 32.0,
                "decision_efficiency": 40.0,
                "ai_productivity_boost": 40.0,
                "focus_quality": 40.0,
                "masterplan_progress": 40.0,
            },
            "offsets": {
                "continue_highest_priority_task": 3.0,
                "create_new_task": 2.0,
                "reprioritize_tasks": 2.5,
                "review_plan": 1.0,
            },
            "is_personalized": True,
        },
    )
    row = type("ThresholdRow", (), {"adapted_count": 1, "last_adapted_at": None})()
    mocker.patch("apps.analytics.services.policy_adaptation_service.get_or_create_thresholds", return_value=row)

    response = client.get("/analytics/policy-thresholds", headers=auth_headers)

    assert response.status_code == 200
    assert "kpi_low" in response.json()


def test_post_policy_thresholds_adapt_returns_200_with_auth(client, auth_headers, mocker):
    from apps.analytics.routes import analytics_router as router_mod

    async def _fake_execute_with_pipeline(*args, **kwargs):
        return kwargs["handler"](None)

    mocker.patch.object(router_mod, "execute_with_pipeline", side_effect=_fake_execute_with_pipeline)
    mocker.patch(
        "apps.analytics.services.policy_adaptation_service.adapt_policy_thresholds",
        return_value={"status": "adapted", "adapted_count": 1, "thresholds": {}, "offsets": {}},
    )

    response = client.post("/analytics/policy-thresholds/adapt", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "adapted"
