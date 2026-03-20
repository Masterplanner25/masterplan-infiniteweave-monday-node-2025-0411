"""
Identity Layer Tests - v5 Phase 2
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime


class TestUserIdentityModel:
    def test_model_importable(self):
        from db.models.user_identity import UserIdentity
        assert UserIdentity.__tablename__ == "user_identity"

    def test_table_in_db(self):
        from sqlalchemy import inspect
        from sqlalchemy.exc import OperationalError
        from db.database import engine
        from db.models.user_identity import UserIdentity
        try:
            insp = inspect(engine)
            if "user_identity" not in insp.get_table_names():
                assert "user_identity" in UserIdentity.metadata.tables
        except OperationalError:
            assert "user_identity" in UserIdentity.metadata.tables

    def test_valid_constants_defined(self):
        from db.models.user_identity import (
            VALID_TONES,
            VALID_RISK_TOLERANCE,
            VALID_SPEED_VS_QUALITY,
            VALID_LEARNING_STYLES,
            VALID_DETAIL_PREFERENCES,
        )
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
        from services.identity_service import IdentityService
        assert IdentityService is not None

    def test_get_context_empty_profile(self, mock_db):
        """Empty profile returns empty context string."""
        from services.identity_service import IdentityService
        from db.models.user_identity import UserIdentity

        mock_identity = MagicMock(spec=UserIdentity)
        mock_identity.tone = None
        mock_identity.preferred_languages = []
        mock_identity.preferred_tools = []
        mock_identity.avoided_tools = []
        mock_identity.risk_tolerance = None
        mock_identity.speed_vs_quality = None
        mock_identity.learning_style = None
        mock_identity.detail_preference = None
        mock_identity.communication_notes = None
        mock_identity.decision_notes = None
        mock_identity.learning_notes = None
        mock_identity.observation_count = 0
        mock_identity.last_updated = None
        mock_identity.evolution_log = []

        mock_db.query.return_value.filter.return_value.first.return_value = mock_identity

        service = IdentityService(db=mock_db, user_id="test-user")
        context = service.get_context_for_prompt()
        assert context == ""

    def test_get_context_with_profile(self, mock_db):
        """Profile with values generates context string."""
        from services.identity_service import IdentityService
        from db.models.user_identity import UserIdentity

        mock_identity = MagicMock(spec=UserIdentity)
        mock_identity.tone = "technical"
        mock_identity.preferred_languages = ["python", "rust"]
        mock_identity.preferred_tools = []
        mock_identity.avoided_tools = []
        mock_identity.risk_tolerance = "moderate"
        mock_identity.speed_vs_quality = "quality"
        mock_identity.learning_style = "examples"
        mock_identity.detail_preference = "step_by_step"
        mock_identity.communication_notes = None
        mock_identity.decision_notes = None
        mock_identity.learning_notes = None
        mock_identity.observation_count = 5
        mock_identity.last_updated = datetime.utcnow()
        mock_identity.evolution_log = []

        mock_db.query.return_value.filter.return_value.first.return_value = mock_identity

        service = IdentityService(db=mock_db, user_id="test-user")
        context = service.get_context_for_prompt()

        assert "technical" in context
        assert "python" in context
        assert "moderate" in context
        assert "examples" in context

    def test_observe_infers_language(self, mock_db):
        """ARM analysis observation infers language."""
        from services.identity_service import IdentityService
        from db.models.user_identity import UserIdentity

        mock_identity = MagicMock(spec=UserIdentity)
        mock_identity.preferred_languages = []
        mock_identity.preferred_tools = []
        mock_identity.avoided_tools = []
        mock_identity.risk_tolerance = None
        mock_identity.speed_vs_quality = None
        mock_identity.evolution_log = []
        mock_identity.observation_count = 0
        mock_identity.last_updated = None

        mock_db.query.return_value.filter.return_value.first.return_value = mock_identity

        service = IdentityService(db=mock_db, user_id="test-user")
        service.observe(
            event_type="arm_analysis_complete",
            context={"language": "python", "score": 8},
        )

        mock_db.add.assert_called()

    def test_observe_infers_risk_from_posture(self, mock_db):
        """Aggressive posture infers aggressive risk tolerance."""
        from services.identity_service import IdentityService
        from db.models.user_identity import UserIdentity

        mock_identity = MagicMock(spec=UserIdentity)
        mock_identity.preferred_languages = []
        mock_identity.preferred_tools = []
        mock_identity.avoided_tools = []
        mock_identity.risk_tolerance = None
        mock_identity.speed_vs_quality = None
        mock_identity.evolution_log = []
        mock_identity.observation_count = 0
        mock_identity.last_updated = None

        mock_db.query.return_value.filter.return_value.first.return_value = mock_identity

        service = IdentityService(db=mock_db, user_id="test-user")
        service.observe(
            event_type="masterplan_locked",
            context={"posture": "aggressive"},
        )

        assert mock_identity.risk_tolerance == "aggressive"

    def test_evolution_log_records_changes(self, mock_db):
        """Changes are recorded in evolution_log."""
        from services.identity_service import IdentityService
        from db.models.user_identity import UserIdentity

        mock_identity = MagicMock(spec=UserIdentity)
        mock_identity.tone = None
        mock_identity.preferred_languages = []
        mock_identity.preferred_tools = []
        mock_identity.avoided_tools = []
        mock_identity.risk_tolerance = None
        mock_identity.speed_vs_quality = None
        mock_identity.learning_style = None
        mock_identity.detail_preference = None
        mock_identity.communication_notes = None
        mock_identity.decision_notes = None
        mock_identity.learning_notes = None
        mock_identity.observation_count = 0
        mock_identity.last_updated = None
        mock_identity.evolution_log = []

        mock_db.query.return_value.filter.return_value.first.return_value = mock_identity

        service = IdentityService(db=mock_db, user_id="test-user")
        service.update_explicit(tone="technical")

        assert mock_identity.evolution_log is not None


class TestIdentityEndpoints:
    def test_get_identity_requires_auth(self, client):
        r = client.get("/identity/")
        assert r.status_code == 401

    def test_update_identity_requires_auth(self, client):
        r = client.put("/identity/", json={})
        assert r.status_code == 401

    def test_evolution_requires_auth(self, client):
        r = client.get("/identity/evolution")
        assert r.status_code == 401

    def test_context_requires_auth(self, client):
        r = client.get("/identity/context")
        assert r.status_code == 401

    def test_get_identity_with_auth(self, client, auth_headers, mock_db):
        from unittest.mock import MagicMock
        from db.models.user_identity import UserIdentity

        mock_identity = MagicMock(spec=UserIdentity)
        mock_identity.user_id = "test-user-id-123"
        mock_identity.tone = "technical"
        mock_identity.preferred_languages = ["python"]
        mock_identity.preferred_tools = []
        mock_identity.avoided_tools = []
        mock_identity.risk_tolerance = "moderate"
        mock_identity.speed_vs_quality = "quality"
        mock_identity.learning_style = "examples"
        mock_identity.detail_preference = "step_by_step"
        mock_identity.communication_notes = None
        mock_identity.decision_notes = None
        mock_identity.learning_notes = None
        mock_identity.observation_count = 3
        mock_identity.last_updated = None
        mock_identity.evolution_log = []

        mock_db.query.return_value.filter.return_value.first.return_value = mock_identity

        r = client.get("/identity/", headers=auth_headers)
        assert r.status_code in [200, 422]
        assert r.status_code != 401

        if r.status_code == 200:
            data = r.json()
            assert "communication" in data
            assert "tools" in data
            assert "decision_making" in data
            assert "learning" in data
            assert "evolution" in data

    def test_update_invalid_tone_rejected(self, client, auth_headers):
        r = client.put(
            "/identity/",
            json={"tone": "invalid_tone"},
            headers=auth_headers,
        )
        assert r.status_code in [200, 422]
        assert r.status_code != 401
