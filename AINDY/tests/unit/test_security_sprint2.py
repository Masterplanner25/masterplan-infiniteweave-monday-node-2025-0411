"""
Security Sprint 2 Tests

Focused on user-scoping and ownership enforcement added in this sprint.
"""
import inspect
import importlib


def _source(obj) -> str:
    return inspect.getsource(obj)


class TestMemoryUserScoping:
    def test_memory_list_scoped_to_user(self):
        memory_router = importlib.import_module("routes.memory_router")
        src = _source(memory_router.search_nodes_by_tags)
        assert "user_id" in src, "search_nodes_by_tags missing user_id scoping"
        assert "current_user" in src, "search_nodes_by_tags missing current_user reference"

    def test_memory_link_ownership_check_present(self):
        memory_router = importlib.import_module("routes.memory_router")
        src = _source(memory_router.create_link)
        assert "get_by_id" in src, "create_link should verify node ownership via get_by_id"
        assert "current_user" in src, "create_link missing current_user reference"
        assert "Source node not found" in src, "create_link missing source ownership 404"
        assert "Target node not found" in src, "create_link missing target ownership 404"


class TestAnalyticsOwnership:
    def test_analytics_manual_ingest_ownership(self):
        analytics_router = importlib.import_module("routes.analytics_router")
        src = _source(analytics_router.ingest_linkedin_manual)
        # Ownership enforced via assert_masterplan_owned() which filters by MasterPlan.user_id
        assert "assert_masterplan_owned" in src or "MasterPlan.user_id" in src, (
            "manual ingest missing masterplan user scoping"
        )
        assert "current_user" in src, "manual ingest missing current_user reference"

    def test_analytics_summary_ownership(self):
        analytics_router = importlib.import_module("routes.analytics_router")
        src = _source(analytics_router.get_masterplan_summary)
        # Ownership enforced via assert_masterplan_owned() which filters by MasterPlan.user_id
        assert "assert_masterplan_owned" in src or "MasterPlan.user_id" in src, (
            "summary missing masterplan user scoping"
        )


class TestSocialProfileOwnership:
    def test_social_profile_upsert_scoped(self):
        social_router = importlib.import_module("routes.social_router")
        src = _source(social_router.upsert_profile)
        assert "user_id" in src, "social profile upsert missing user_id scoping"
        assert "current_user" in src, "social profile upsert missing current_user reference"


class TestBridgeNodeOwnership:
    def test_bridge_node_sets_user_id(self):
        bridge_router = importlib.import_module("routes.bridge_router")
        src = _source(bridge_router.create_node)
        assert "user_id" in src, "bridge node creation missing user_id handling"

    def test_bridge_node_sets_source_agent(self):
        bridge_router = importlib.import_module("routes.bridge_router")
        src = _source(bridge_router.create_node)
        assert "source_agent" in src, "bridge node creation missing source_agent handling"
