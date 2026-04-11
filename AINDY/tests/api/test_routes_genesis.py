"""
test_routes_genesis.py
──────────────────────
Genesis route tests.

Routes from routes/genesis_router.py (prefix /genesis):
  POST /genesis/session      — creates a session
  POST /genesis/message      — sends a message, calls call_genesis_llm()
  POST /genesis/synthesize   — BUG: calls call_genesis_synthesis_llm() (not imported)
  POST /genesis/lock         — BUG: calls create_masterplan_from_genesis() (not imported)
  POST /genesis/{plan_id}/activate — BUG: references MasterPlan (not imported)

Known bugs in genesis_router.py:
1. /genesis/synthesize calls call_genesis_synthesis_llm() — NameError (not imported)
2. /genesis/lock calls create_masterplan_from_genesis() and MasterPlan — NameError
3. /genesis/{plan_id}/activate references MasterPlan — NameError
"""
import pytest
import re
from unittest.mock import MagicMock, patch


class TestGenesisRouteRegistration:
    def test_genesis_session_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/genesis/session" in routes, (
            f"/genesis/session not found. Routes: {routes}"
        )

    def test_genesis_message_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/genesis/message" in routes

    def test_genesis_synthesize_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/genesis/synthesize" in routes

    def test_genesis_lock_route_registered(self, app):
        routes = [r.path for r in app.routes]
        assert "/genesis/lock" in routes


class TestGenesisSessionEndpoint:
    def test_post_genesis_session_requires_auth(self, client):
        """POST /genesis/session must return 401 without a valid JWT token."""
        response = client.post("/genesis/session")
        assert response.status_code == 401, (
            f"POST /genesis/session returned {response.status_code} without auth. "
            "Expected 401 — JWT auth is required."
        )

    def test_post_genesis_session_with_auth_not_404(self, client, auth_headers):
        """POST /genesis/session with valid auth must reach the handler (not 404)."""
        response = client.post("/genesis/session", headers=auth_headers)
        assert response.status_code != 404, (
            f"POST /genesis/session returned 404 — route not registered"
        )

    def test_post_genesis_session_with_auth_returns_expected_status(self, client, auth_headers):
        """With valid auth, POST /genesis/session returns 200, 201, or 500 (no DB)."""
        response = client.post("/genesis/session", headers=auth_headers)
        assert response.status_code in (200, 201, 500), (
            f"Unexpected status: {response.status_code}"
        )


class TestGenesisMessageEndpoint:
    def test_post_genesis_message_missing_session_id_returns_400(self, client, auth_headers):
        """POST /genesis/message without session_id must return 400."""
        # The route checks `if not session_id: raise HTTPException(400, ...)`
        response = client.post(
            "/genesis/message",
            json={"message": "hello"},
            headers=auth_headers,
        )
        assert response.status_code == 400, (
            f"Expected 400 for missing session_id, got {response.status_code}: {response.text}"
        )

    def test_post_genesis_message_missing_message_returns_400(self, client, auth_headers):
        """POST /genesis/message without message must return 400."""
        response = client.post(
            "/genesis/message",
            json={"session_id": "fake-id"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_genesis_message_calls_real_openai(self):
        """
        DIAGNOSTIC: POST /genesis/message calls call_genesis_llm() which makes
        a LIVE OpenAI API call (no mocking in production code).

        This test verifies call_genesis_llm() is NOT a stub.
        """
        import inspect
        from AINDY.domain.genesis_ai import call_genesis_llm

        source = inspect.getsource(call_genesis_llm)
        # Confirm it calls the OpenAI client
        assert "client.chat.completions.create" in source, (
            "call_genesis_llm() appears to be a stub — does not call OpenAI"
        )
        # Confirm it is NOT a stub (stubs typically just return a dict immediately)
        assert "return {" not in source[:100], (
            "call_genesis_llm() looks like a stub (returns dict immediately)"
        )


def _read_genesis_router_source():
    """Helper: read the genesis_router.py source as a string."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "routes" / "genesis_router.py"
    return path.read_text(encoding="utf-8")


class TestGenesisSynthesizeEndpoint:
    def test_post_genesis_synthesize_has_name_error_bug(self):
        """
        BUG FIXED: call_genesis_synthesis_llm is now imported in genesis_router.py.

        POST /genesis/synthesize previously called call_genesis_synthesis_llm(current_state)
        without importing it — raising NameError at runtime. Import has been added.
        """
        source = _read_genesis_router_source()

        # The function is referenced in the synthesize endpoint
        assert "call_genesis_synthesis_llm" in source, (
            "call_genesis_synthesis_llm not referenced in genesis_router.py"
        )

        # Check that it IS now imported (fix verified)
        has_any_import = bool(
            re.search(
                r"from\s+services\.genesis_ai\s+import\s*\([\s\S]*call_genesis_synthesis_llm",
                source,
            )
            or re.search(
                r"from\s+services\.genesis_ai\s+import\s+[\s\S]*call_genesis_synthesis_llm",
                source,
            )
        )

        assert has_any_import, (
            "REGRESSION: call_genesis_synthesis_llm is no longer imported in genesis_router.py. "
            "This will cause NameError at runtime on POST /genesis/synthesize."
        )

        # Verify the function exists in genesis_ai
        from AINDY.domain.genesis_ai import call_genesis_synthesis_llm
        assert callable(call_genesis_synthesis_llm), (
            "call_genesis_synthesis_llm does not exist in genesis_ai.py — it should"
        )


class TestGenesisLockEndpoint:
    def test_post_genesis_lock_missing_fields_returns_400(self, client, auth_headers):
        """POST /genesis/lock without session_id or draft must return 400."""
        response = client.post("/genesis/lock", json={}, headers=auth_headers)
        assert response.status_code == 400

    def test_post_genesis_lock_has_undefined_name_bug(self):
        """
        BUG FIXED: create_masterplan_from_genesis is now imported in genesis_router.py.

        POST /genesis/lock previously called create_masterplan_from_genesis() without
        importing it — raising NameError at runtime. Import has been added.
        """
        source = _read_genesis_router_source()

        assert "create_masterplan_from_genesis" in source, (
            "create_masterplan_from_genesis not referenced in genesis_router"
        )

        # Check that it IS now imported (fix verified)
        imported = bool(
            re.search(
                r"from\s+services\.masterplan_factory\s+import\s+create_masterplan_from_genesis",
                source,
            )
        )

        assert imported, (
            "REGRESSION: create_masterplan_from_genesis is no longer imported in genesis_router.py. "
            "This will cause NameError at runtime on POST /genesis/lock."
        )


# ── Block 1: DB + User Isolation ─────────────────────────────────────────────

class TestGenesisBlock1:
    """Block 1: Alembic columns added and model fields present."""

    def test_genesis_session_has_synthesis_ready_column(self):
        """GenesisSessionDB must have synthesis_ready (Boolean) column."""
        from AINDY.db.models import GenesisSessionDB
        col_names = [c.key for c in GenesisSessionDB.__table__.columns]
        assert "synthesis_ready" in col_names, (
            f"synthesis_ready missing from genesis_sessions. Columns: {col_names}"
        )

    def test_genesis_session_has_draft_json_column(self):
        """GenesisSessionDB must have draft_json (JSON) column."""
        from AINDY.db.models import GenesisSessionDB
        col_names = [c.key for c in GenesisSessionDB.__table__.columns]
        assert "draft_json" in col_names, (
            f"draft_json missing from genesis_sessions. Columns: {col_names}"
        )

    def test_genesis_session_has_user_id_column(self):
        """GenesisSessionDB must have user_id (UUID) column."""
        from AINDY.db.models import GenesisSessionDB
        col_names = [c.key for c in GenesisSessionDB.__table__.columns]
        assert "user_id" in col_names, (
            f"user_id missing from genesis_sessions. Columns: {col_names}"
        )

    def test_genesis_session_has_locked_at_column(self):
        """GenesisSessionDB must have locked_at (DateTime) column."""
        from AINDY.db.models import GenesisSessionDB
        col_names = [c.key for c in GenesisSessionDB.__table__.columns]
        assert "locked_at" in col_names, (
            f"locked_at missing from genesis_sessions. Columns: {col_names}"
        )

    def test_master_plan_has_user_id_column(self):
        """MasterPlan must have user_id (String) column."""
        from AINDY.db.models import MasterPlan
        col_names = [c.key for c in MasterPlan.__table__.columns]
        assert "user_id" in col_names, (
            f"user_id missing from master_plans. Columns: {col_names}"
        )

    def test_master_plan_has_status_column(self):
        """MasterPlan must have status (String) column."""
        from AINDY.db.models import MasterPlan
        col_names = [c.key for c in MasterPlan.__table__.columns]
        assert "status" in col_names, (
            f"status missing from master_plans. Columns: {col_names}"
        )

    def test_create_masterplan_from_genesis_accepts_user_id(self):
        """create_masterplan_from_genesis must accept user_id keyword argument."""
        import inspect
        from AINDY.domain.masterplan_factory import create_masterplan_from_genesis
        sig = inspect.signature(create_masterplan_from_genesis)
        assert "user_id" in sig.parameters, (
            "create_masterplan_from_genesis does not accept user_id parameter"
        )

    def test_masterplan_router_registered(self, app):
        """/masterplans routes must be registered."""
        paths = [r.path for r in app.routes]
        assert any("/masterplans" in p for p in paths), (
            f"No /masterplans routes registered. Paths: {paths}"
        )

    def test_masterplan_list_requires_auth(self, client):
        """GET /masterplans/ must return 401 without JWT."""
        response = client.get("/masterplans/")
        assert response.status_code == 401

    def test_masterplan_get_requires_auth(self, client):
        """GET /masterplans/1 must return 401 without JWT."""
        response = client.get("/masterplans/1")
        assert response.status_code == 401


# ── Block 2: Session Polling + Auth ──────────────────────────────────────────

class TestGenesisBlock2:
    """Block 2: GET /genesis/session/{id} and GET /genesis/draft/{id} endpoints."""

    def test_get_genesis_session_route_registered(self, app):
        """GET /genesis/session/{session_id} must be registered."""
        paths = [r.path for r in app.routes]
        assert "/genesis/session/{session_id}" in paths, (
            f"/genesis/session/{{session_id}} not found. Routes: {paths}"
        )

    def test_get_genesis_draft_route_registered(self, app):
        """GET /genesis/draft/{session_id} must be registered."""
        paths = [r.path for r in app.routes]
        assert "/genesis/draft/{session_id}" in paths, (
            f"/genesis/draft/{{session_id}} not found. Routes: {paths}"
        )

    def test_get_genesis_session_requires_auth(self, client):
        """GET /genesis/session/1 must return 401 without JWT."""
        response = client.get("/genesis/session/1")
        assert response.status_code == 401

    def test_get_genesis_draft_requires_auth(self, client):
        """GET /genesis/draft/1 must return 401 without JWT."""
        response = client.get("/genesis/draft/1")
        assert response.status_code == 401

    def test_synthesis_ready_flag_is_one_way(self):
        """
        genesis_message handler must not revert synthesis_ready from True to False.
        Verify by inspecting router source for the one-way guard.
        """
        source = _read_genesis_router_source()
        assert "not session.synthesis_ready" in source or "synthesis_ready and not" in source, (
            "One-way synthesis_ready guard not found in genesis_router.py. "
            "The flag must never revert from True to False."
        )


# ── Block 3: Real Synthesis + Posture ────────────────────────────────────────

class TestGenesisBlock3:
    """Block 3: Real synthesis LLM, synthesis_ready gate, posture detection."""

    def test_call_genesis_synthesis_llm_is_real_not_stub(self):
        """call_genesis_synthesis_llm must make a real OpenAI call, not return a static dict."""
        import inspect
        from AINDY.domain.genesis_ai import call_genesis_synthesis_llm
        source = inspect.getsource(call_genesis_synthesis_llm)
        assert "client.chat.completions.create" in source, (
            "call_genesis_synthesis_llm appears to be a stub — does not call OpenAI"
        )

    def test_synthesize_endpoint_gates_on_synthesis_ready(self):
        """
        POST /genesis/synthesize must reject requests when synthesis_ready is False.
        Verify the gate exists in the router source.
        """
        source = _read_genesis_router_source()
        assert "synthesis_ready" in source and "422" in source, (
            "synthesis_ready gate (422) not found in genesis_router.py synthesize endpoint"
        )

    def test_synthesize_endpoint_requires_auth(self, client):
        """POST /genesis/synthesize must return 401 without JWT."""
        response = client.post("/genesis/synthesize", json={"session_id": 1})
        assert response.status_code == 401

    def test_determine_posture_returns_valid_labels(self):
        """determine_posture must return one of four valid posture labels."""
        from AINDY.analytics.posture import determine_posture
        valid = {"Stable", "Accelerated", "Aggressive", "Reduced"}
        test_cases = [
            {"time_horizon_years": 1, "ambition_score": 0.9},   # → Aggressive
            {"time_horizon_years": 3, "ambition_score": 0.7},   # → Accelerated
            {"time_horizon_years": 10, "ambition_score": 0.2},  # → Reduced
            {"time_horizon_years": 5, "ambition_score": 0.5},   # → Stable
        ]
        for draft in test_cases:
            result = determine_posture(draft)
            assert result in valid, (
                f"determine_posture({draft}) returned '{result}', not in {valid}"
            )

    def test_determine_posture_aggressive_short_high(self):
        """Short horizon + high ambition → Aggressive."""
        from AINDY.analytics.posture import determine_posture
        assert determine_posture({"time_horizon_years": 1, "ambition_score": 0.9}) == "Aggressive"

    def test_determine_posture_reduced_long_low(self):
        """Long horizon + low ambition → Reduced."""
        from AINDY.analytics.posture import determine_posture
        assert determine_posture({"time_horizon_years": 8, "ambition_score": 0.2}) == "Reduced"

    def test_posture_description_exists(self):
        """posture_description() helper must exist and return non-empty strings."""
        from AINDY.analytics.posture import posture_description
        for posture in ("Stable", "Accelerated", "Aggressive", "Reduced"):
            desc = posture_description(posture)
            assert isinstance(desc, str) and len(desc) > 0, (
                f"posture_description('{posture}') returned empty/non-string"
            )

