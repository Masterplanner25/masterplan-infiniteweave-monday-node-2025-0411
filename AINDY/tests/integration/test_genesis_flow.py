"""
test_genesis_flow.py
────────────────────
Comprehensive Genesis Blocks 4-6 test coverage.

Covers:
  Block 4 — validate_draft_integrity(), AUDIT_SYSTEM_PROMPT, POST /genesis/audit
  Block 5 — factory hardening (synthesis_ready gate, draft_from_session, rollback)
  Block 6 — duplicate route removal, masterplan_router /lock + list shape
"""
import pytest
import json
import inspect
from unittest.mock import MagicMock, patch


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _read_source(relative_path: str) -> str:
    import os
    base = os.path.join(os.path.dirname(__file__), "..")
    full = os.path.abspath(os.path.join(base, relative_path))
    with open(full, "r", encoding="utf-8") as f:
        return f.read()


SAMPLE_DRAFT = {
    "vision_statement": "Build a sustainable consulting practice",
    "time_horizon_years": 3,
    "primary_mechanism": "High-value client retainers",
    "ambition_score": 0.7,
    "core_domains": [{"name": "Consulting", "intent": "Revenue engine"}],
    "phases": [{"name": "Foundation", "description": "Build pipeline", "duration_months": 6}],
    "key_assets": ["Network", "Expertise"],
    "success_criteria": ["$10k MRR within 12 months"],
    "risk_factors": ["Market saturation"],
    "confidence_at_synthesis": 0.75,
    "synthesis_notes": "High confidence on mechanism; time horizon inferred.",
}

SAMPLE_AUDIT_RESULT = {
    "audit_passed": True,
    "findings": [],
    "overall_confidence": 0.82,
    "audit_summary": "Draft is structurally sound with no critical findings.",
}

SAMPLE_AUDIT_RESULT_FAILED = {
    "audit_passed": False,
    "findings": [
        {
            "type": "mechanism_gap",
            "severity": "critical",
            "description": "No clear acquisition channel defined.",
            "recommendation": "Specify at least one inbound or outbound channel.",
        }
    ],
    "overall_confidence": 0.4,
    "audit_summary": "One critical finding requires attention before locking.",
}


# ─── Block 4: validate_draft_integrity ────────────────────────────────────────

class TestValidateDraftIntegrity:
    """Unit tests for the validate_draft_integrity() service function."""

    def test_function_exists_in_genesis_ai(self):
        from services.genesis_ai import validate_draft_integrity
        assert callable(validate_draft_integrity)

    def test_audit_system_prompt_exists(self):
        from services.genesis_ai import AUDIT_SYSTEM_PROMPT
        assert isinstance(AUDIT_SYSTEM_PROMPT, str) and len(AUDIT_SYSTEM_PROMPT) > 50

    def test_audit_system_prompt_contains_required_fields(self):
        from services.genesis_ai import AUDIT_SYSTEM_PROMPT
        for field in ("audit_passed", "findings", "overall_confidence", "audit_summary"):
            assert field in AUDIT_SYSTEM_PROMPT, (
                f"AUDIT_SYSTEM_PROMPT missing required field: {field}"
            )

    def test_audit_system_prompt_contains_severity_levels(self):
        from services.genesis_ai import AUDIT_SYSTEM_PROMPT
        for level in ("critical", "warning", "advisory"):
            assert level in AUDIT_SYSTEM_PROMPT, (
                f"AUDIT_SYSTEM_PROMPT missing severity level: {level}"
            )

    def test_audit_system_prompt_contains_finding_types(self):
        from services.genesis_ai import AUDIT_SYSTEM_PROMPT
        for ftype in ("mechanism_gap", "contradiction", "timeline_risk", "asset_gap", "confidence_concern"):
            assert ftype in AUDIT_SYSTEM_PROMPT, (
                f"AUDIT_SYSTEM_PROMPT missing finding type: {ftype}"
            )

    def test_validate_draft_integrity_calls_openai(self):
        source = _read_source("services/genesis_ai.py")
        func_start = source.index("def validate_draft_integrity(")
        func_body = source[func_start:]
        assert "client.chat.completions.create" in func_body, (
            "validate_draft_integrity() does not call OpenAI"
        )

    def test_validate_draft_integrity_uses_gpt4o(self):
        source = _read_source("services/genesis_ai.py")
        func_start = source.index("def validate_draft_integrity(")
        func_body = source[func_start:]
        assert "gpt-4o" in func_body, (
            "validate_draft_integrity() should use gpt-4o model"
        )

    def test_validate_draft_integrity_has_retry_logic(self):
        source = _read_source("services/genesis_ai.py")
        func_start = source.index("def validate_draft_integrity(")
        func_body = source[func_start:]
        assert "retry" in func_body.lower() or "attempt" in func_body.lower(), (
            "validate_draft_integrity() should have retry logic"
        )

    def test_validate_draft_integrity_has_failsafe(self):
        """If OpenAI fails, function must return a valid fallback dict."""
        from services.genesis_ai import validate_draft_integrity
        with patch("services.genesis_ai.client") as mock_client:
            mock_client.chat.completions.create.side_effect = Exception("Network error")
            result = validate_draft_integrity(SAMPLE_DRAFT)
        assert isinstance(result, dict), "Fail-safe must return a dict"
        assert "audit_passed" in result
        assert "findings" in result
        assert "overall_confidence" in result
        assert "audit_summary" in result

    def test_validate_draft_integrity_failsafe_audit_passed_false(self):
        """Fail-safe result must have audit_passed=False."""
        from services.genesis_ai import validate_draft_integrity
        with patch("services.genesis_ai.client") as mock_client:
            mock_client.chat.completions.create.side_effect = Exception("fail")
            result = validate_draft_integrity(SAMPLE_DRAFT)
        assert result["audit_passed"] is False

    def test_validate_draft_integrity_happy_path(self):
        """With a valid OpenAI response, function returns parsed JSON."""
        from services.genesis_ai import validate_draft_integrity
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(SAMPLE_AUDIT_RESULT)
        with patch("services.genesis_ai.client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_response
            result = validate_draft_integrity(SAMPLE_DRAFT)
        assert result["audit_passed"] is True
        assert result["overall_confidence"] == 0.82
        assert result["findings"] == []

    def test_validate_draft_integrity_failed_audit(self):
        """Function correctly returns a failed audit with critical findings."""
        from services.genesis_ai import validate_draft_integrity
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(SAMPLE_AUDIT_RESULT_FAILED)
        with patch("services.genesis_ai.client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_response
            result = validate_draft_integrity(SAMPLE_DRAFT)
        assert result["audit_passed"] is False
        assert len(result["findings"]) == 1
        assert result["findings"][0]["severity"] == "critical"

    def test_validate_draft_integrity_uses_json_object_format(self):
        """Must use response_format json_object to ensure valid JSON output."""
        source = _read_source("services/genesis_ai.py")
        func_start = source.index("def validate_draft_integrity(")
        func_body = source[func_start:]
        assert "json_object" in func_body, (
            "validate_draft_integrity() should use response_format json_object"
        )

    def test_genesis_ai_exports_validate_draft_integrity(self):
        """validate_draft_integrity must be importable from services.genesis_ai."""
        try:
            from services.genesis_ai import validate_draft_integrity
        except ImportError:
            pytest.fail("validate_draft_integrity not importable from services.genesis_ai")


# ─── Block 4: POST /genesis/audit route ───────────────────────────────────────

class TestGenesisAuditRoute:
    """Integration tests for POST /genesis/audit."""

    def test_audit_route_registered(self, app):
        paths = [r.path for r in app.routes]
        assert "/genesis/audit" in paths, (
            f"/genesis/audit not registered. Routes: {paths}"
        )

    def test_audit_requires_auth(self, client):
        """POST /genesis/audit must return 401 without JWT."""
        response = client.post("/genesis/audit", json={"session_id": 1})
        assert response.status_code == 401

    def test_audit_not_404_with_auth(self, client, auth_headers):
        """POST /genesis/audit with auth must not return 404."""
        response = client.post("/genesis/audit", json={"session_id": 1}, headers=auth_headers)
        assert response.status_code != 404, (
            f"POST /genesis/audit returned 404 — route not registered"
        )

    def test_audit_missing_draft_returns_non_401(self, client, auth_headers):
        """POST /genesis/audit with auth must reach the handler (not 401/404)."""
        # Mock DB returns MagicMock objects (truthy), so route handler is reached.
        # With no real DB, the result may be 200 (fail-safe), 422, or 500.
        response = client.post("/genesis/audit", json={"session_id": 9999}, headers=auth_headers)
        assert response.status_code != 401, "Should not return 401 with valid auth"
        assert response.status_code != 404, "Route must be registered"

    def test_audit_router_imports_validate_draft_integrity(self):
        """genesis_router.py must import validate_draft_integrity."""
        source = _read_source("routes/genesis_router.py")
        assert "validate_draft_integrity" in source, (
            "validate_draft_integrity not found in genesis_router.py"
        )
        assert "from services.genesis_ai import" in source
        import_line = [
            line for line in source.split("\n")
            if "from services.genesis_ai import" in line
        ]
        assert any("validate_draft_integrity" in line for line in import_line), (
            "validate_draft_integrity not imported from services.genesis_ai in genesis_router.py"
        )

    def test_audit_uses_session_draft_json(self):
        """genesis_router audit endpoint must use session.draft_json, not caller-provided draft."""
        source = _read_source("routes/genesis_router.py")
        audit_start = source.index("def audit_genesis_draft(")
        audit_body = source[audit_start:audit_start + 600]
        assert "draft_json" in audit_body, (
            "audit endpoint should use session.draft_json"
        )

    def test_audit_endpoint_returns_422_when_no_draft(self):
        """Audit endpoint logic should raise 422 when draft_json is None/missing."""
        source = _read_source("routes/genesis_router.py")
        audit_start = source.index("def audit_genesis_draft(")
        audit_body = source[audit_start:audit_start + 600]
        assert "422" in audit_body, (
            "audit endpoint should raise 422 when no draft_json available"
        )


# ─── Block 5: masterplan_factory hardening ────────────────────────────────────

class TestMasterplanFactoryHardening:
    """Tests for the hardened create_masterplan_from_genesis() function."""

    def test_factory_accepts_user_id(self):
        from services.masterplan_factory import create_masterplan_from_genesis
        sig = inspect.signature(create_masterplan_from_genesis)
        assert "user_id" in sig.parameters

    def test_factory_raises_on_missing_session(self, mock_db):
        from services.masterplan_factory import create_masterplan_from_genesis
        mock_db.first.return_value = None
        with pytest.raises(Exception, match="not found"):
            create_masterplan_from_genesis(999, {}, mock_db, user_id="u1")

    def test_factory_raises_on_already_locked(self, mock_db):
        from services.masterplan_factory import create_masterplan_from_genesis
        mock_session = MagicMock()
        mock_session.status = "locked"
        mock_session.synthesis_ready = True
        mock_db.first.return_value = mock_session
        with pytest.raises(Exception, match="already locked"):
            create_masterplan_from_genesis(1, {}, mock_db, user_id="u1")

    def test_factory_raises_if_not_synthesis_ready(self, mock_db):
        """Factory must gate on synthesis_ready — raise if False."""
        from services.masterplan_factory import create_masterplan_from_genesis
        mock_session = MagicMock()
        mock_session.status = "active"
        mock_session.synthesis_ready = False
        mock_db.first.return_value = mock_session
        with pytest.raises((Exception, ValueError)) as exc_info:
            create_masterplan_from_genesis(1, SAMPLE_DRAFT, mock_db, user_id="u1")
        assert "synthesis" in str(exc_info.value).lower() or "ready" in str(exc_info.value).lower(), (
            "Factory should raise meaningful error when synthesis_ready is False"
        )

    def test_factory_synthesis_ready_gate_in_source(self):
        """Source code must contain synthesis_ready check."""
        source = _read_source("services/masterplan_factory.py")
        assert "synthesis_ready" in source, (
            "create_masterplan_from_genesis() should check synthesis_ready"
        )

    def test_factory_uses_session_draft_json_when_available(self):
        """Factory should prefer session.draft_json over caller-supplied draft."""
        source = _read_source("services/masterplan_factory.py")
        assert "draft_json" in source, (
            "Factory should use session.draft_json"
        )
        assert "draft_to_use" in source or "session.draft_json or draft" in source, (
            "Factory should load draft from session when available"
        )

    def test_factory_has_rollback_on_exception(self):
        """Factory must call db.rollback() on exception."""
        source = _read_source("services/masterplan_factory.py")
        assert "db.rollback()" in source, (
            "Factory must call db.rollback() in exception handler"
        )

    def test_factory_rollback_called_on_db_failure(self, mock_db):
        """db.rollback() must be called when db.commit() raises."""
        from services.masterplan_factory import create_masterplan_from_genesis
        mock_session = MagicMock()
        mock_session.status = "active"
        mock_session.synthesis_ready = True
        mock_session.draft_json = SAMPLE_DRAFT
        mock_db.filter_by.return_value.first.return_value = mock_session
        mock_db.filter.return_value.order_by.return_value.all.return_value = []
        mock_db.first.return_value = mock_session
        mock_db.commit.side_effect = Exception("DB commit failed")

        with pytest.raises(Exception):
            create_masterplan_from_genesis(1, SAMPLE_DRAFT, mock_db, user_id="u1")

        mock_db.rollback.assert_called_once()

    def test_factory_returns_masterplan_object(self, mock_db):
        """Factory must return a MasterPlan instance on success."""
        from services.masterplan_factory import create_masterplan_from_genesis
        from db.models import MasterPlan

        mock_session = MagicMock()
        mock_session.status = "active"
        mock_session.synthesis_ready = True
        mock_session.draft_json = SAMPLE_DRAFT
        mock_session.id = 1

        mock_db.filter_by.return_value.first.return_value = mock_session
        mock_db.filter.return_value.order_by.return_value.all.return_value = []

        result = create_masterplan_from_genesis(1, SAMPLE_DRAFT, mock_db, user_id="u1")

        assert mock_db.add.call_count >= 1
        assert mock_db.commit.call_count >= 1
        assert isinstance(result, MasterPlan)

    def test_factory_sets_posture_from_draft(self, mock_db):
        """Factory must set posture based on draft ambition/horizon."""
        from services.masterplan_factory import create_masterplan_from_genesis

        mock_session = MagicMock()
        mock_session.status = "active"
        mock_session.synthesis_ready = True
        mock_session.draft_json = {"time_horizon_years": 1, "ambition_score": 0.9}
        mock_session.id = 1

        mock_db.filter_by.return_value.first.return_value = mock_session
        mock_db.filter.return_value.order_by.return_value.all.return_value = []

        result = create_masterplan_from_genesis(1, {}, mock_db, user_id="u1")
        assert result.posture == "Aggressive"


# ─── Block 5: masterplan_router /lock + list shape ────────────────────────────

class TestMasterplanRouterLock:
    """Tests for POST /masterplans/lock endpoint and updated list response."""

    def test_masterplan_lock_route_registered(self, app):
        paths = [r.path for r in app.routes]
        assert "/masterplans/lock" in paths, (
            f"/masterplans/lock not registered. Routes: {paths}"
        )

    def test_masterplan_lock_requires_auth(self, client):
        response = client.post("/masterplans/lock", json={"session_id": 1})
        assert response.status_code == 401

    def test_masterplan_lock_not_404_with_auth(self, client, auth_headers):
        response = client.post("/masterplans/lock", json={"session_id": 1}, headers=auth_headers)
        assert response.status_code != 404

    def test_masterplan_lock_missing_session_id_returns_400(self, client, auth_headers):
        response = client.post("/masterplans/lock", json={}, headers=auth_headers)
        assert response.status_code == 400

    def test_masterplan_lock_imports_factory(self):
        source = _read_source("routes/masterplan_router.py")
        assert "create_masterplan_from_genesis" in source, (
            "masterplan_router.py must import create_masterplan_from_genesis"
        )

    def test_masterplan_lock_imports_posture_description(self):
        source = _read_source("routes/masterplan_router.py")
        assert "posture_description" in source, (
            "masterplan_router.py must import posture_description"
        )

    def test_masterplan_lock_response_includes_posture_description(self):
        source = _read_source("routes/masterplan_router.py")
        lock_start = source.index("def lock_from_genesis(")
        lock_body = source[lock_start:lock_start + 1200]
        assert "posture_description" in lock_body, (
            "lock_from_genesis() should include posture_description in response"
        )

    def test_masterplan_lock_handles_value_error_as_422(self):
        """ValueError from factory (synthesis_ready gate) must map to 422."""
        source = _read_source("routes/masterplan_router.py")
        lock_start = source.index("def lock_from_genesis(")
        lock_body = source[lock_start:lock_start + 800]
        assert "ValueError" in lock_body and "422" in lock_body, (
            "lock_from_genesis() should catch ValueError and return 422"
        )


class TestMasterplanListResponseShape:
    """Tests for updated list_masterplans() response shape."""

    def test_list_masterplans_returns_plans_key(self):
        """GET /masterplans/ must return {'plans': [...]} not a plain list."""
        source = _read_source("routes/masterplan_router.py")
        list_start = source.index("def list_masterplans(")
        list_body = source[list_start:list_start + 600]
        assert '"plans"' in list_body or "'plans'" in list_body, (
            "list_masterplans() should return {\"plans\": [...]}"
        )

    def test_list_masterplans_requires_auth(self, client):
        response = client.get("/masterplans/")
        assert response.status_code == 401

    def test_list_masterplans_with_auth_not_404(self, client, auth_headers):
        response = client.get("/masterplans/", headers=auth_headers)
        assert response.status_code != 404

    def test_list_masterplans_returns_dict_not_list(self, client, auth_headers):
        """Response must be a JSON object, not a plain array."""
        response = client.get("/masterplans/", headers=auth_headers)
        # 200 or 500 (no DB) — either way, if 200 the body must be an object
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict), (
                f"list_masterplans returned a list instead of dict: {data}"
            )
            assert "plans" in data


# ─── Block 6: Duplicate route removal ────────────────────────────────────────

class TestDuplicateRouteRemoval:
    """Verify the duplicate POST /create_masterplan was removed from main_router.py."""

    def test_only_one_create_masterplan_handler(self):
        """main_router.py must have exactly one POST /create_masterplan handler."""
        source = _read_source("routes/main_router.py")
        # Count how many async def create_masterplan functions exist
        count = source.count("async def create_masterplan(")
        assert count == 1, (
            f"Expected 1 create_masterplan handler in main_router.py, found {count}. "
            "The duplicate using MasterPlanCreate must be removed."
        )

    def test_masterplan_create_schema_uses_masterplan_input(self):
        """The remaining create_masterplan handler must use MasterPlanInput."""
        source = _read_source("routes/main_router.py")
        handler_start = source.index("async def create_masterplan(")
        handler_sig = source[handler_start:handler_start + 150]
        assert "MasterPlanInput" in handler_sig, (
            "Remaining create_masterplan handler should use MasterPlanInput schema"
        )

    def test_masterplan_create_schema_does_not_use_masterplan_create(self):
        """MasterPlanCreate schema must not appear in the create_masterplan signature."""
        source = _read_source("routes/main_router.py")
        handler_start = source.index("async def create_masterplan(")
        handler_sig = source[handler_start:handler_start + 150]
        assert "MasterPlanCreate" not in handler_sig, (
            "MasterPlanCreate is from the deleted duplicate — remove it from handler"
        )

    def test_no_duplicate_route_paths(self, app):
        """Each HTTP method + path combination must be unique in the app."""
        from collections import Counter
        route_keys = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in (route.methods or []):
                    route_keys.append(f"{method}:{route.path}")
        duplicates = [k for k, v in Counter(route_keys).items() if v > 1]
        assert not duplicates, (
            f"Duplicate routes found in app: {duplicates}"
        )


# ─── Block 4+5: Synthesis prompt schema ──────────────────────────────────────

class TestSynthesisPromptSchema:
    """Verify SYNTHESIS_SYSTEM_PROMPT includes synthesis_notes field."""

    def test_synthesis_prompt_schema_complete(self):
        from services.genesis_ai import SYNTHESIS_SYSTEM_PROMPT
        required = [
            "vision_statement", "time_horizon_years", "primary_mechanism",
            "ambition_score", "core_domains", "phases", "key_assets",
            "success_criteria", "risk_factors", "confidence_at_synthesis",
            "synthesis_notes",
        ]
        for field in required:
            assert field in SYNTHESIS_SYSTEM_PROMPT, (
                f"SYNTHESIS_SYSTEM_PROMPT missing field: {field}"
            )

    def test_synthesis_notes_rule_in_prompt(self):
        from services.genesis_ai import SYNTHESIS_SYSTEM_PROMPT
        assert "synthesis_notes" in SYNTHESIS_SYSTEM_PROMPT
        # Confirm there's a rule describing it
        assert "inferred" in SYNTHESIS_SYSTEM_PROMPT or "confident" in SYNTHESIS_SYSTEM_PROMPT


# ─── Block 5: posture_description helper ──────────────────────────────────────

class TestPostureDescriptionHelper:
    """Tests for posture_description() from services.posture."""

    def test_posture_description_returns_string_for_all_postures(self):
        from services.posture import posture_description
        for posture in ("Stable", "Accelerated", "Aggressive", "Reduced"):
            desc = posture_description(posture)
            assert isinstance(desc, str) and len(desc) > 0

    def test_posture_description_stable(self):
        from services.posture import posture_description
        desc = posture_description("Stable")
        assert "stable" in desc.lower() or "balanced" in desc.lower() or "steady" in desc.lower()

    def test_posture_description_aggressive(self):
        from services.posture import posture_description
        desc = posture_description("Aggressive")
        assert len(desc) > 0

    def test_posture_description_unknown(self):
        from services.posture import posture_description
        desc = posture_description("Unknown")
        assert isinstance(desc, str)


# ─── Integration: Full genesis flow routes registered ────────────────────────

class TestGenesisFlowRouteRegistration:
    """Verify all genesis flow routes are registered in the app."""

    def test_all_genesis_routes_present(self, app):
        paths = [r.path for r in app.routes]
        expected = [
            "/genesis/session",
            "/genesis/message",
            "/genesis/synthesize",
            "/genesis/audit",
            "/genesis/lock",
            "/genesis/session/{session_id}",
            "/genesis/draft/{session_id}",
        ]
        for path in expected:
            assert path in paths, f"Missing route: {path}. Routes: {paths}"

    def test_all_masterplan_routes_present(self, app):
        paths = [r.path for r in app.routes]
        expected = [
            "/masterplans/",
            "/masterplans/{plan_id}",
            "/masterplans/lock",
            "/masterplans/{plan_id}/activate",
        ]
        for path in expected:
            assert path in paths, f"Missing route: {path}. Routes: {paths}"
