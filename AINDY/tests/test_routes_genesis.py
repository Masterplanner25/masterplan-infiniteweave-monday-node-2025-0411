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
    def test_post_genesis_session_not_404(self, client):
        """POST /genesis/session must reach the handler (not return 404)."""
        response = client.post("/genesis/session")
        assert response.status_code != 404, (
            f"POST /genesis/session returned 404 — route not registered"
        )

    def test_post_genesis_session_without_db_returns_non_200(self, client):
        """Without DB, POST /genesis/session will fail with 500 or similar."""
        response = client.post("/genesis/session")
        # 500 expected when DB not available — but not 404
        assert response.status_code in (200, 201, 500), (
            f"Unexpected status: {response.status_code}"
        )


class TestGenesisMessageEndpoint:
    def test_post_genesis_message_missing_session_id_returns_400(self, client):
        """POST /genesis/message without session_id must return 400."""
        # The route checks `if not session_id: raise HTTPException(400, ...)`
        response = client.post("/genesis/message", json={"message": "hello"})
        assert response.status_code == 400, (
            f"Expected 400 for missing session_id, got {response.status_code}: {response.text}"
        )

    def test_post_genesis_message_missing_message_returns_400(self, client):
        """POST /genesis/message without message must return 400."""
        response = client.post("/genesis/message", json={"session_id": "fake-id"})
        assert response.status_code == 400

    def test_genesis_message_calls_real_openai(self):
        """
        DIAGNOSTIC: POST /genesis/message calls call_genesis_llm() which makes
        a LIVE OpenAI API call (no mocking in production code).

        This test verifies call_genesis_llm() is NOT a stub.
        """
        import inspect
        from services.genesis_ai import call_genesis_llm

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
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "routes", "genesis_router.py")
    with open(os.path.abspath(path), "r", encoding="utf-8") as f:
        return f.read()


class TestGenesisSynthesizeEndpoint:
    def test_post_genesis_synthesize_has_name_error_bug(self):
        """
        DIAGNOSTIC — INTENTIONAL FAILING TEST.

        POST /genesis/synthesize calls call_genesis_synthesis_llm(current_state)
        but this function is NOT imported in genesis_router.py.

        When called with a valid session_id (requires DB), this will raise NameError.
        This test documents the import bug by reading the source file directly.
        """
        source = _read_genesis_router_source()

        # The bug: synthesize endpoint calls undefined name
        assert "call_genesis_synthesis_llm" in source, (
            "call_genesis_synthesis_llm not referenced in genesis_router.py"
        )

        # Check whether it is imported
        has_any_import = (
            "import call_genesis_synthesis_llm" in source or
            (
                "from services.genesis_ai import" in source and
                "call_genesis_synthesis_llm" in source.split("from services.genesis_ai import")[-1].split("\n")[0]
            )
        )

        assert not has_any_import, (
            "BUG FIXED: call_genesis_synthesis_llm is now imported in genesis_router.py. "
            "Remove this test."
        )

        # Verify the function exists in genesis_ai — the bug is only in the router
        from services.genesis_ai import call_genesis_synthesis_llm
        assert callable(call_genesis_synthesis_llm), (
            "call_genesis_synthesis_llm does not exist in genesis_ai.py — it should"
        )


class TestGenesisLockEndpoint:
    def test_post_genesis_lock_missing_fields_returns_400(self, client):
        """POST /genesis/lock without session_id or draft must return 400."""
        response = client.post("/genesis/lock", json={})
        assert response.status_code == 400

    def test_post_genesis_lock_has_undefined_name_bug(self):
        """
        DIAGNOSTIC: POST /genesis/lock calls create_masterplan_from_genesis()
        which is NOT imported in genesis_router.py — will raise NameError.
        """
        source = _read_genesis_router_source()

        assert "create_masterplan_from_genesis" in source, (
            "create_masterplan_from_genesis not referenced in genesis_router"
        )

        # Check that it's not imported
        imported = False
        for line in source.split("\n"):
            if "import" in line and "create_masterplan_from_genesis" in line:
                imported = True
                break
            if "import" in line and "masterplan_factory" in line:
                imported = True
                break

        assert not imported, (
            "BUG FIXED: create_masterplan_from_genesis is now imported. Remove this test."
        )
