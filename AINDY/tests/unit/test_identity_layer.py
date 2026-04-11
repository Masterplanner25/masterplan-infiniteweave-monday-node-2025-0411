from __future__ import annotations

from sqlalchemy import inspect

from AINDY.db.models.user_identity import (
    UserIdentity,
    VALID_DETAIL_PREFERENCES,
    VALID_LEARNING_STYLES,
    VALID_RISK_TOLERANCE,
    VALID_SPEED_VS_QUALITY,
    VALID_TONES,
)
from AINDY.domain.identity_service import IdentityService


class TestUserIdentityModel:
    def test_model_importable(self):
        assert UserIdentity.__tablename__ == "user_identity"

    def test_table_in_db(self, test_engine):
        insp = inspect(test_engine)
        assert "user_identity" in insp.get_table_names()

    def test_valid_constants_defined(self):
        assert "formal" in VALID_TONES
        assert "casual" in VALID_TONES
        assert "conservative" in VALID_RISK_TOLERANCE
        assert "aggressive" in VALID_RISK_TOLERANCE
        assert "speed" in VALID_SPEED_VS_QUALITY
        assert "quality" in VALID_SPEED_VS_QUALITY
        assert "examples" in VALID_LEARNING_STYLES
        assert "step_by_step" in VALID_DETAIL_PREFERENCES


class TestIdentityService:
    def test_service_importable(self):
        assert IdentityService is not None

    def test_get_context_empty_profile(self, db_session, test_user):
        service = IdentityService(db=db_session, user_id=str(test_user.id))

        context = service.get_context_for_prompt()

        assert context == ""

    def test_get_context_with_profile(self, db_session, test_user):
        identity = UserIdentity(
            user_id=test_user.id,
            tone="technical",
            preferred_languages=["python", "rust"],
            risk_tolerance="moderate",
            learning_style="examples",
            detail_preference="step_by_step",
            evolution_log=[],
        )
        db_session.add(identity)
        db_session.commit()

        service = IdentityService(db=db_session, user_id=str(test_user.id))
        context = service.get_context_for_prompt()

        assert "technical" in context
        assert "python" in context
        assert "moderate" in context
        assert "examples" in context

    def test_observe_infers_language(self, db_session, test_user):
        service = IdentityService(db=db_session, user_id=str(test_user.id))

        service.observe(
            event_type="arm_analysis_complete",
            context={"language": "python", "score": 8},
        )

        identity = service.get_or_create()
        assert "python" in (identity.preferred_languages or [])
        assert identity.speed_vs_quality == "quality"

    def test_observe_infers_risk_from_posture(self, db_session, test_user):
        service = IdentityService(db=db_session, user_id=str(test_user.id))

        service.observe(
            event_type="masterplan_locked",
            context={"posture": "aggressive"},
        )

        identity = service.get_or_create()
        assert identity.risk_tolerance == "aggressive"

    def test_evolution_log_records_changes(self, db_session, test_user):
        service = IdentityService(db=db_session, user_id=str(test_user.id))

        result = service.update_explicit(tone="technical")

        identity = service.get_or_create()
        assert result["changes_recorded"] == 1
        assert identity.evolution_log

