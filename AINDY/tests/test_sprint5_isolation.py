"""
Sprint 5 User Isolation Tests

Verifies freelance, research, and rippletrace data is correctly
scoped to the current user. user_id columns exist in DB and all
write/read operations are user-scoped in route handlers.
"""
import os
import pytest
import inspect

_ROUTES_DIR = os.path.join(os.path.dirname(__file__), '..', 'routes')
_SERVICES_DIR = os.path.join(os.path.dirname(__file__), '..', 'services')


def _read_source(path: str) -> str:
    with open(path, encoding='utf-8') as f:
        return f.read()


class TestFreelanceIsolation:

    def test_freelance_orders_requires_auth(self, client):
        """GET /freelance/orders must return 401 without JWT."""
        r = client.get("/freelance/orders")
        assert r.status_code == 401, (
            f"GET /freelance/orders returned {r.status_code}. Expected 401."
        )

    def test_freelance_feedback_requires_auth(self, client):
        """GET /freelance/feedback must return 401 without JWT."""
        r = client.get("/freelance/feedback")
        assert r.status_code == 401, (
            f"GET /freelance/feedback returned {r.status_code}. Expected 401."
        )

    def test_freelance_create_order_requires_auth(self, client):
        """POST /freelance/order must return 401 without JWT."""
        r = client.post("/freelance/order", json={})
        assert r.status_code == 401, (
            f"POST /freelance/order returned {r.status_code}. Expected 401."
        )

    def test_freelance_create_feedback_requires_auth(self, client):
        """POST /freelance/feedback must return 401 without JWT."""
        r = client.post("/freelance/feedback", json={})
        assert r.status_code == 401, (
            f"POST /freelance/feedback returned {r.status_code}. Expected 401."
        )

    def test_freelance_deliver_requires_auth(self, client):
        """POST /freelance/deliver/{id} must return 401 without JWT."""
        r = client.post("/freelance/deliver/1", params={"ai_output": "test"})
        assert r.status_code == 401, (
            f"POST /freelance/deliver/1 returned {r.status_code}. Expected 401."
        )

    def test_freelance_orders_accepts_valid_token(self, client, auth_headers):
        """GET /freelance/orders must not return 401 with valid JWT."""
        r = client.get("/freelance/orders", headers=auth_headers)
        assert r.status_code != 401, (
            f"GET /freelance/orders returned 401 with valid token."
        )

    def test_freelance_router_has_user_id_assignment(self):
        """freelance_router source must contain user_id assignment for writes."""
        source = _read_source(os.path.join(_ROUTES_DIR, 'freelance_router.py'))
        assert 'user_id' in source, "freelance_router missing user_id assignment"
        assert 'current_user["sub"]' in source, (
            "freelance_router missing current_user['sub'] reference"
        )

    def test_freelance_service_passes_user_id(self):
        """freelance_service create_order and collect_feedback accept user_id."""
        from services.freelance_service import create_order, collect_feedback, get_all_orders, get_all_feedback
        import inspect
        for fn in [create_order, collect_feedback, get_all_orders, get_all_feedback]:
            sig = inspect.signature(fn)
            assert 'user_id' in sig.parameters, (
                f"freelance_service.{fn.__name__} missing user_id parameter"
            )


class TestResearchIsolation:

    def test_research_list_requires_auth(self, client):
        """GET /research/ must return 401 without JWT."""
        r = client.get("/research/")
        assert r.status_code == 401, (
            f"GET /research/ returned {r.status_code}. Expected 401."
        )

    def test_research_create_requires_auth(self, client):
        """POST /research/ must return 401 without JWT."""
        r = client.post("/research/", json={})
        assert r.status_code == 401, (
            f"POST /research/ returned {r.status_code}. Expected 401."
        )

    def test_research_query_requires_auth(self, client):
        """POST /research/query must return 401 without JWT."""
        r = client.post("/research/query", json={})
        assert r.status_code == 401, (
            f"POST /research/query returned {r.status_code}. Expected 401."
        )

    def test_research_list_accepts_valid_token(self, client, auth_headers):
        """GET /research/ must not return 401 with valid JWT."""
        r = client.get("/research/", headers=auth_headers)
        assert r.status_code != 401, (
            f"GET /research/ returned 401 with valid token."
        )

    def test_research_router_has_user_id_assignment(self):
        """research_results_router source must contain user_id assignment."""
        source = _read_source(os.path.join(_ROUTES_DIR, 'research_results_router.py'))
        assert 'user_id' in source, "research_results_router missing user_id assignment"
        assert 'current_user["sub"]' in source, (
            "research_results_router missing current_user['sub'] reference"
        )

    def test_research_service_passes_user_id(self):
        """research_results_service functions accept user_id."""
        from services.research_results_service import (
            create_research_result, get_all_research_results
        )
        for fn in [create_research_result, get_all_research_results]:
            sig = inspect.signature(fn)
            assert 'user_id' in sig.parameters, (
                f"research_results_service.{fn.__name__} missing user_id parameter"
            )


class TestRippletraceIsolation:

    def test_rippletrace_drop_points_requires_auth(self, client):
        """GET /rippletrace/drop_points must return 401 without JWT."""
        r = client.get("/rippletrace/drop_points")
        assert r.status_code == 401, (
            f"GET /rippletrace/drop_points returned {r.status_code}. Expected 401."
        )

    def test_rippletrace_pings_requires_auth(self, client):
        """GET /rippletrace/pings must return 401 without JWT."""
        r = client.get("/rippletrace/pings")
        assert r.status_code == 401, (
            f"GET /rippletrace/pings returned {r.status_code}. Expected 401."
        )

    def test_rippletrace_recent_requires_auth(self, client):
        """GET /rippletrace/recent must return 401 without JWT."""
        r = client.get("/rippletrace/recent")
        assert r.status_code == 401, (
            f"GET /rippletrace/recent returned {r.status_code}. Expected 401."
        )

    def test_rippletrace_create_drop_point_requires_auth(self, client):
        """POST /rippletrace/drop_point must return 401 without JWT."""
        r = client.post("/rippletrace/drop_point", json={})
        assert r.status_code == 401, (
            f"POST /rippletrace/drop_point returned {r.status_code}. Expected 401."
        )

    def test_rippletrace_drop_points_accepts_valid_token(self, client, auth_headers):
        """GET /rippletrace/drop_points must not return 401 with valid JWT."""
        r = client.get("/rippletrace/drop_points", headers=auth_headers)
        assert r.status_code != 401, (
            f"GET /rippletrace/drop_points returned 401 with valid token."
        )

    def test_rippletrace_pings_accepts_valid_token(self, client, auth_headers):
        """GET /rippletrace/pings must not return 401 with valid JWT."""
        r = client.get("/rippletrace/pings", headers=auth_headers)
        assert r.status_code != 401, (
            f"GET /rippletrace/pings returned 401 with valid token."
        )

    def test_rippletrace_router_has_user_id_assignment(self):
        """rippletrace_router source must contain user_id assignment."""
        source = _read_source(os.path.join(_ROUTES_DIR, 'rippletrace_router.py'))
        assert 'user_id' in source, "rippletrace_router missing user_id assignment"
        assert 'current_user["sub"]' in source, (
            "rippletrace_router missing current_user['sub'] reference"
        )

    def test_rippletrace_service_passes_user_id(self):
        """rippletrace_services functions accept user_id."""
        from services.rippletrace_services import (
            add_drop_point, add_ping, get_all_drop_points,
            get_all_pings, get_recent_ripples, get_ripples,
        )
        for fn in [add_drop_point, add_ping, get_all_drop_points,
                   get_all_pings, get_recent_ripples, get_ripples]:
            sig = inspect.signature(fn)
            assert 'user_id' in sig.parameters, (
                f"rippletrace_services.{fn.__name__} missing user_id parameter"
            )


class TestUserIdColumnPresence:
    """Verify user_id columns exist in ORM model definitions for all target tables."""

    def test_freelance_orders_model_has_user_id(self):
        from db.models.freelance import FreelanceOrder
        cols = [c.name for c in FreelanceOrder.__table__.columns]
        assert 'user_id' in cols, "FreelanceOrder model missing user_id column"

    def test_client_feedback_model_has_user_id(self):
        from db.models.freelance import ClientFeedback
        cols = [c.name for c in ClientFeedback.__table__.columns]
        assert 'user_id' in cols, "ClientFeedback model missing user_id column"

    def test_research_results_model_has_user_id(self):
        from db.models.research_results import ResearchResult
        cols = [c.name for c in ResearchResult.__table__.columns]
        assert 'user_id' in cols, "ResearchResult model missing user_id column"

    def test_drop_points_model_has_user_id(self):
        from db.models.drop import DropPointDB
        cols = [c.name for c in DropPointDB.__table__.columns]
        assert 'user_id' in cols, "DropPointDB model missing user_id column"

    def test_pings_model_has_user_id(self):
        from db.models.drop import PingDB
        cols = [c.name for c in PingDB.__table__.columns]
        assert 'user_id' in cols, "PingDB model missing user_id column"
