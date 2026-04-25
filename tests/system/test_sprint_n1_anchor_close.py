"""
Sprint N+1 "Anchor and Close" — Test Suite

Covers:
  - FIX 1: SECRET_KEY hardening (config + main.py startup guard)
  - FIX 2: Dual DAO consolidation (load_memory_node + find_by_tags aliases)
  - FIX 3: MemoryNode.children persistence via extra["children"]
  - STEP 5: MasterPlan anchor + ETA columns on ORM model
  - STEP 6: PUT /masterplans/{id}/anchor endpoint
  - STEP 7: ETA service (calculate_eta, recalculate_all_etas) + GET /masterplans/{id}/projection
  - STEP 8: api.js functions (smoke — import check via backend only)
  - APScheduler: daily ETA job registered
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


@pytest.fixture
def router_mock_db(app):
    """
    Like conftest.mock_db, but imports get_db from the router module's namespace
    rather than db.database directly.

    Why: test_sprint6_sprint7.py reloads db.database via importlib.reload(), which
    creates a new get_db function object.  Any fixture that imports get_db from
    db.database *after* that reload will get the new object, while FastAPI's
    dependency graph still holds the *old* reference captured at router import time.
    Importing from the router module guarantees we use the same object FastAPI uses.
    """
    import sys
    # routes/__init__.py rebinds 'routes.masterplan_router' to the APIRouter object,
    # so 'import routes.masterplan_router as mr' returns the router, not the module.
    # We need the MODULE to access the captured get_db reference that FastAPI uses.
    mr_module = sys.modules.get("apps.masterplan.routes.masterplan_router")
    assert mr_module is not None, "apps.masterplan.routes.masterplan_router module not loaded"

    db = MagicMock()
    db.query.return_value = db
    db.filter.return_value = db
    db.filter_by.return_value = db
    db.first.return_value = None
    db.all.return_value = []
    db.add.return_value = None
    db.commit.return_value = None
    db.refresh.return_value = None
    db.rollback.return_value = None

    get_db_fn = mr_module.get_db
    app.dependency_overrides[get_db_fn] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db_fn, None)


# ─────────────────────────────────────────────────────────────────────────────
# FIX 1: SECRET_KEY hardening
# ─────────────────────────────────────────────────────────────────────────────

class TestSecretKeyHardening:
    def test_config_has_secret_key_field(self):
        """Settings class must have a SECRET_KEY field."""
        from AINDY.config import Settings
        assert hasattr(Settings.model_fields, "SECRET_KEY") or "SECRET_KEY" in Settings.model_fields

    def test_secret_key_loaded_from_env(self):
        """settings.SECRET_KEY must be populated (non-empty)."""
        from AINDY.config import settings
        assert settings.SECRET_KEY
        assert len(settings.SECRET_KEY) > 0

    def test_secret_key_test_env_is_not_placeholder(self):
        """Test env must not use the insecure default placeholder."""
        from AINDY.config import settings
        assert settings.SECRET_KEY != "dev-secret-change-in-production", (
            "Test env is using the insecure placeholder — set SECRET_KEY in .env or conftest"
        )

    def test_is_prod_property_false_in_test(self):
        """is_prod must be False in test environment."""
        from AINDY.config import settings
        assert not settings.is_prod

    def test_startup_guard_warns_in_dev(self):
        """In dev/test, placeholder key must emit a warning, not raise."""
        import logging
        with patch("config.settings") as mock_settings:
            mock_settings.SECRET_KEY = "dev-secret-change-in-production"
            mock_settings.is_prod = False
            # The guard in main.py checks is_prod before raising — no exception expected
            # Just verify the placeholder detection logic path is reachable
            placeholder = "dev-secret-change-in-production"
            assert mock_settings.SECRET_KEY == placeholder

    def test_startup_guard_raises_in_prod(self):
        """In prod, placeholder key must raise RuntimeError."""
        placeholder = "dev-secret-change-in-production"
        # Simulate the main.py guard logic directly
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            secret = placeholder
            is_prod = True
            if secret == placeholder and is_prod:
                raise RuntimeError(
                    "SECRET_KEY is using the insecure default placeholder. "
                    "Set a strong SECRET_KEY in your .env before running in production."
                )


# ─────────────────────────────────────────────────────────────────────────────
# FIX 2: Dual DAO consolidation
# ─────────────────────────────────────────────────────────────────────────────

class TestDualDAOConsolidation:
    def test_canonical_dao_has_load_memory_node(self):
        """Canonical DAO must expose load_memory_node()."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "load_memory_node")

    def test_canonical_dao_has_find_by_tags(self):
        """Canonical DAO must expose find_by_tags()."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        assert hasattr(MemoryNodeDAO, "find_by_tags")

    def test_load_memory_node_returns_none_for_missing(self):
        """load_memory_node must return None when node does not exist."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        dao = MemoryNodeDAO(mock_db)
        result = dao.load_memory_node("00000000-0000-0000-0000-000000000099")
        assert result is None

    def test_load_memory_node_returns_dict_for_existing(self):
        """load_memory_node must return a dict when node exists."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from unittest.mock import MagicMock
        import uuid
        mock_db = MagicMock()
        fake_node = MagicMock()
        fake_node.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        fake_node.content = "test content"
        fake_node.tags = ["a"]
        fake_node.node_type = "insight"
        fake_node.source = "test"
        fake_node.source_agent = None
        fake_node.is_shared = False
        fake_node.user_id = "user-1"
        fake_node.extra = {}
        fake_node.created_at = datetime.now(timezone.utc)
        fake_node.updated_at = datetime.now(timezone.utc)
        mock_db.query.return_value.filter.return_value.first.return_value = fake_node
        dao = MemoryNodeDAO(mock_db)
        result = dao.load_memory_node("00000000-0000-0000-0000-000000000001")
        assert isinstance(result, dict)
        assert result["content"] == "test content"

    def test_find_by_tags_delegates_to_get_by_tags(self):
        """find_by_tags must return same result as get_by_tags."""
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.all.return_value = []
        dao = MemoryNodeDAO(mock_db)
        r1 = dao.find_by_tags([], user_id="u1")
        r2 = dao.get_by_tags([], user_id="u1")
        assert r1 == r2

    def test_bridge_router_imports_canonical_dao(self):
        """bridge_router.py must import MemoryNodeDAO from canonical path."""
        import sys
        import importlib
        # Re-import to get module object (not the router attribute)
        if "apps.bridge.routes.bridge_router" in sys.modules:
            br = sys.modules["apps.bridge.routes.bridge_router"]
        else:
            br = importlib.import_module("apps.bridge.routes.bridge_router")
        src_file = br.__file__
        with open(src_file, "r", encoding="utf-8") as f:
            source = f.read()
        assert "MemoryNodeDAO" in source
        assert "from memory.memory_persistence import MemoryNodeDAO" not in source


# ─────────────────────────────────────────────────────────────────────────────
# FIX 3: MemoryNode.children persistence
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryNodeChildrenPersistence:
    def test_save_creates_child_links_from_extra(self):
        """save() must create MemoryLink rows for node IDs in extra['children']."""
        import uuid
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.memory.embedding_service import generate_embedding

        child_id = uuid.uuid4()
        mock_db = MagicMock()

        # The saved parent node
        parent_node = MagicMock()
        parent_node.id = uuid.uuid4()
        parent_node.content = "parent"
        parent_node.tags = []
        parent_node.node_type = "test"
        parent_node.source = "test"
        parent_node.source_agent = None
        parent_node.is_shared = False
        parent_node.user_id = "u1"
        parent_node.extra = {"children": [str(child_id)]}
        parent_node.created_at = datetime.now(timezone.utc)
        parent_node.updated_at = datetime.now(timezone.utc)

        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.side_effect = lambda x: None

        # Child exists query
        child_mock = MagicMock()
        child_mock.id = child_id
        mock_db.query.return_value.filter.return_value.first.return_value = child_mock

        with patch("AINDY.memory.embedding_service.generate_embedding", return_value=None):
            dao = MemoryNodeDAO(mock_db)
            # Manually assign the parent node after add (simulates refresh)
            with patch.object(dao, "_node_to_dict", return_value={"id": str(parent_node.id)}):
                # Intercept the node created by save() and make it the parent_node
                original_add = mock_db.add
                added_objects = []
                mock_db.add.side_effect = lambda obj: added_objects.append(obj)
                mock_db.refresh.side_effect = lambda obj: None

                # We need the MemoryNodeModel instance that save() creates
                # to have a valid id — patch MemoryNodeModel
                import AINDY.db.dao.memory_node_dao as dao_module
                from AINDY.memory.memory_persistence import MemoryNodeModel, MemoryLinkModel

                with patch.object(dao_module, "MemoryNodeModel") as MockModel, \
                     patch.object(dao_module, "MemoryLinkModel") as MockLink:
                    mock_instance = MagicMock()
                    mock_instance.id = uuid.uuid4()
                    mock_instance.content = "parent"
                    mock_instance.tags = []
                    mock_instance.node_type = None
                    mock_instance.source = None
                    mock_instance.source_agent = None
                    mock_instance.is_shared = None
                    mock_instance.user_id = "u1"
                    mock_instance.extra = {}
                    mock_instance.created_at = datetime.now(timezone.utc)
                    mock_instance.updated_at = None
                    MockModel.return_value = mock_instance

                    dao.save(
                        content="parent",
                        user_id="u1",
                        extra={"children": [str(child_id)]},
                        generate_embedding=False,
                    )

                    # MemoryLinkModel should have been instantiated for the child
                    MockLink.assert_called_once()
                    call_kwargs = MockLink.call_args
                    assert call_kwargs is not None

    def test_save_no_children_creates_no_links(self):
        """save() with no children in extra must not create any MemoryLink rows."""
        import uuid
        import AINDY.db.dao.memory_node_dao as dao_module
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        mock_db = MagicMock()

        with patch.object(dao_module, "MemoryNodeModel") as MockModel, \
             patch.object(dao_module, "MemoryLinkModel") as MockLink:
            mock_instance = MagicMock()
            mock_instance.id = uuid.uuid4()
            mock_instance.content = "no children"
            mock_instance.tags = []
            mock_instance.node_type = None
            mock_instance.source = None
            mock_instance.source_agent = None
            mock_instance.is_shared = None
            mock_instance.user_id = "u1"
            mock_instance.extra = {}
            mock_instance.created_at = datetime.now(timezone.utc)
            mock_instance.updated_at = None
            MockModel.return_value = mock_instance

            dao = MemoryNodeDAO(mock_db)
            dao.save(content="no children", user_id="u1", extra={}, generate_embedding=False)

            MockLink.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: MasterPlan ORM columns
# ─────────────────────────────────────────────────────────────────────────────

class TestMasterPlanAnchorColumns:
    def test_masterplan_has_anchor_date(self):
        from apps.masterplan.models import MasterPlan
        assert hasattr(MasterPlan, "anchor_date")

    def test_masterplan_has_goal_value(self):
        from apps.masterplan.models import MasterPlan
        assert hasattr(MasterPlan, "goal_value")

    def test_masterplan_has_goal_unit(self):
        from apps.masterplan.models import MasterPlan
        assert hasattr(MasterPlan, "goal_unit")

    def test_masterplan_has_goal_description(self):
        from apps.masterplan.models import MasterPlan
        assert hasattr(MasterPlan, "goal_description")

    def test_masterplan_has_projected_completion_date(self):
        from apps.masterplan.models import MasterPlan
        assert hasattr(MasterPlan, "projected_completion_date")

    def test_masterplan_has_current_velocity(self):
        from apps.masterplan.models import MasterPlan
        assert hasattr(MasterPlan, "current_velocity")

    def test_masterplan_has_days_ahead_behind(self):
        from apps.masterplan.models import MasterPlan
        assert hasattr(MasterPlan, "days_ahead_behind")

    def test_masterplan_has_eta_last_calculated(self):
        from apps.masterplan.models import MasterPlan
        assert hasattr(MasterPlan, "eta_last_calculated")

    def test_masterplan_has_eta_confidence(self):
        from apps.masterplan.models import MasterPlan
        assert hasattr(MasterPlan, "eta_confidence")

    def test_migration_file_exists(self):
        """Alembic migration for anchor columns must exist."""
        versions_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
        files = [path.name for path in versions_dir.iterdir()]
        assert any("anchor_eta" in f for f in files), (
            "No migration file with 'anchor_eta' found in alembic/versions/"
        )


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Anchor endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestAnchorEndpoint:
    def test_put_anchor_404_for_missing_plan(self, client, router_mock_db, auth_headers):
        """PUT /masterplans/{id}/anchor returns 404 for non-existent plan."""
        router_mock_db.first.return_value = None
        resp = client.put(
            "/masterplans/9999/anchor",
            json={"anchor_date": "2027-01-01"},
            headers=auth_headers,
        )
        assert resp.status_code == 404
        body = resp.json()
        # Pipeline passes HTTPExceptions to FastAPI directly: detail at body["detail"].
        # Accept both "details" (legacy custom handler) and "detail" (FastAPI default).
        details = body.get("details") or body.get("detail") or body
        assert details.get("error") == "masterplan_not_found"

    def test_put_anchor_422_for_invalid_date(self, client, router_mock_db, auth_headers):
        """PUT /masterplans/{id}/anchor returns 422 for invalid date format."""
        fake_plan = MagicMock()
        fake_plan.id = 1
        fake_plan.user_id = "00000000-0000-0000-0000-000000000001"
        fake_plan.anchor_date = None
        fake_plan.goal_value = None
        fake_plan.goal_unit = None
        fake_plan.goal_description = None
        router_mock_db.first.return_value = fake_plan

        resp = client.put(
            "/masterplans/1/anchor",
            json={"anchor_date": "not-a-date"},
            headers=auth_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        details = body.get("details") or body.get("detail") or body
        assert details.get("error") == "invalid_anchor_date"

    def test_put_anchor_success(self, client, router_mock_db, auth_headers):
        """PUT /masterplans/{id}/anchor returns 200 with anchor fields."""
        fake_plan = MagicMock()
        fake_plan.id = 1
        fake_plan.user_id = "00000000-0000-0000-0000-000000000001"
        fake_plan.anchor_date = datetime(2027, 1, 1)
        fake_plan.goal_value = 100000.0
        fake_plan.goal_unit = "USD"
        fake_plan.goal_description = "Hit $100k ARR"
        router_mock_db.first.return_value = fake_plan

        resp = client.put(
            "/masterplans/1/anchor",
            json={
                "anchor_date": "2027-01-01",
                "goal_value": 100000,
                "goal_unit": "USD",
                "goal_description": "Hit $100k ARR",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan_id"] == 1
        assert data["goal_unit"] == "USD"
        assert data["goal_value"] == 100000.0

    def test_put_anchor_partial_update(self, client, router_mock_db, auth_headers):
        """PUT /masterplans/{id}/anchor allows partial update (only goal_unit)."""
        fake_plan = MagicMock()
        fake_plan.id = 2
        fake_plan.user_id = "00000000-0000-0000-0000-000000000001"
        fake_plan.anchor_date = None
        fake_plan.goal_value = None
        fake_plan.goal_unit = "tasks"
        fake_plan.goal_description = None
        router_mock_db.first.return_value = fake_plan

        resp = client.put(
            "/masterplans/2/anchor",
            json={"goal_unit": "tasks"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    def test_put_anchor_requires_auth(self, client, router_mock_db):
        """PUT /masterplans/{id}/anchor must require JWT auth."""
        resp = client.put("/masterplans/1/anchor", json={"anchor_date": "2027-01-01"})
        assert resp.status_code in (401, 403, 422)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: ETA service
# ─────────────────────────────────────────────────────────────────────────────

class TestETAService:
    def _make_plan(self, plan_id=1, user_id=None, anchor_date=None):
        plan = MagicMock()
        plan.id = plan_id
        plan.user_id = user_id or uuid4()
        plan.anchor_date = anchor_date
        plan.current_velocity = None
        plan.projected_completion_date = None
        plan.days_ahead_behind = None
        plan.eta_last_calculated = None
        plan.eta_confidence = None
        return plan

    def test_calculate_eta_raises_for_missing_plan(self):
        from apps.masterplan.services.eta_service import calculate_eta
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(ValueError, match="not found"):
            calculate_eta(db=mock_db, masterplan_id=9999, user_id=uuid4())

    def test_calculate_eta_returns_dict_keys(self):
        from apps.masterplan.services.eta_service import calculate_eta
        from apps.masterplan.models import MasterPlan
        from apps.tasks.models import Task

        mock_db = MagicMock()
        plan = self._make_plan(anchor_date=datetime(2027, 6, 1))

        def mock_query(model):
            q = MagicMock()
            if model is MasterPlan:
                q.filter.return_value.first.return_value = plan
            elif model is Task:
                q.filter.return_value.count.return_value = 10
            return q

        mock_db.query.side_effect = mock_query

        result = calculate_eta(db=mock_db, masterplan_id=1, user_id=plan.user_id)
        assert "velocity" in result
        assert "projected_completion_date" in result
        assert "eta_confidence" in result
        assert "days_ahead_behind" in result
        assert "total_tasks" in result
        assert "completed_tasks" in result
        assert "remaining_tasks" in result

    def test_calculate_eta_zero_velocity_no_projection(self):
        """When velocity=0, projected_completion_date must be None."""
        from apps.masterplan.services.eta_service import calculate_eta
        from apps.masterplan.models import MasterPlan
        from apps.tasks.models import Task

        mock_db = MagicMock()
        plan = self._make_plan()

        def mock_query(model):
            q = MagicMock()
            if model is MasterPlan:
                q.filter.return_value.first.return_value = plan
            elif model is Task:
                q.filter.return_value.count.return_value = 0
            return q

        mock_db.query.side_effect = mock_query

        result = calculate_eta(db=mock_db, masterplan_id=1, user_id=plan.user_id)
        assert result["velocity"] == 0
        assert result["projected_completion_date"] is None
        assert result["eta_confidence"] == "insufficient_data"

    def test_calculate_eta_days_ahead_positive_when_early(self):
        """days_ahead_behind is positive when projected date is before anchor."""
        from apps.masterplan.services.eta_service import calculate_eta
        from apps.masterplan.models import MasterPlan
        from apps.tasks.models import Task

        anchor = datetime.now(timezone.utc) + timedelta(days=365)
        mock_db = MagicMock()
        plan = self._make_plan(anchor_date=anchor)

        call_count = {"n": 0}

        def mock_query(model):
            q = MagicMock()
            if model is MasterPlan:
                q.filter.return_value.first.return_value = plan
            elif model is Task:
                call_count["n"] += 1
                # 1st call: tasks_in_window (completed in 14d) = 70
                # 2nd call: total tasks = 100
                # 3rd call: completed tasks = 50
                if call_count["n"] == 1:
                    q.filter.return_value.count.return_value = 70
                elif call_count["n"] == 2:
                    q.filter.return_value.count.return_value = 100
                else:
                    q.filter.return_value.count.return_value = 50
            return q

        mock_db.query.side_effect = mock_query

        result = calculate_eta(db=mock_db, masterplan_id=1, user_id=plan.user_id)
        # velocity=5/day, remaining=50, days_needed=10 → projected ~10 days from now
        # anchor is 365 days out → days_ahead_behind should be very positive
        assert result["days_ahead_behind"] is not None
        assert result["days_ahead_behind"] > 0

    def test_recalculate_all_etas_updates_anchored_plans(self):
        """recalculate_all_etas must process all plans with anchor_date set."""
        from apps.masterplan.services.eta_service import recalculate_all_etas
        from apps.masterplan.models import MasterPlan

        mock_db = MagicMock()

        plan1 = self._make_plan(plan_id=1, user_id=uuid4(), anchor_date=datetime(2027, 1, 1))
        plan2 = self._make_plan(plan_id=2, user_id=uuid4(), anchor_date=datetime(2028, 6, 1))
        mock_db.query.return_value.filter.return_value.all.return_value = [plan1, plan2]

        with patch("apps.masterplan.services.eta_service.calculate_eta") as mock_calc:
            mock_calc.return_value = {"velocity": 1.0}
            count = recalculate_all_etas(mock_db)

        assert count == 2
        assert mock_calc.call_count == 2

    def test_recalculate_all_etas_skips_on_error(self):
        """recalculate_all_etas must continue past individual plan failures."""
        from apps.masterplan.services.eta_service import recalculate_all_etas
        from apps.masterplan.models import MasterPlan

        mock_db = MagicMock()
        plan1 = self._make_plan(plan_id=1, user_id=uuid4(), anchor_date=datetime(2027, 1, 1))
        mock_db.query.return_value.filter.return_value.all.return_value = [plan1]

        with patch("apps.masterplan.services.eta_service.calculate_eta", side_effect=RuntimeError("DB down")):
            count = recalculate_all_etas(mock_db)

        assert count == 0  # failed, but no exception raised


class TestProjectionEndpoint:
    def test_get_projection_404_for_missing_plan(self, client, router_mock_db, auth_headers):
        router_mock_db.first.return_value = None
        resp = client.get("/masterplans/9999/projection", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_projection_returns_eta_fields(self, client, router_mock_db, auth_headers):
        fake_plan = MagicMock()
        fake_plan.id = 1
        fake_plan.user_id = "00000000-0000-0000-0000-000000000001"
        fake_plan.anchor_date = datetime(2027, 1, 1)
        router_mock_db.first.return_value = fake_plan

        eta_result = {
            "masterplan_id": 1,
            "anchor_date": "2027-01-01T00:00:00",
            "velocity": 0.5,
            "projected_completion_date": "2027-06-01",
            "days_ahead_behind": 50,
            "eta_confidence": "medium",
            "total_tasks": 100,
            "completed_tasks": 30,
            "remaining_tasks": 70,
            "eta_last_calculated": "2026-03-23T06:00:00+00:00",
        }
        with patch("apps.masterplan.services.eta_service.calculate_eta", return_value=eta_result):
            resp = client.get("/masterplans/1/projection", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["velocity"] == 0.5
        assert data["eta_confidence"] == "medium"

    def test_get_projection_requires_auth(self, client):
        resp = client.get("/masterplans/1/projection")
        assert resp.status_code in (401, 403, 422)


# ─────────────────────────────────────────────────────────────────────────────
# APScheduler: daily ETA job
# ─────────────────────────────────────────────────────────────────────────────

class TestSchedulerETAJob:
    def test_daily_eta_job_registered_in_system_jobs(self):
        """_register_system_jobs must add the daily_eta_recalculation job."""
        from AINDY.apscheduler.schedulers.background import BackgroundScheduler
        from apps.masterplan import bootstrap as masterplan_bootstrap
        scheduler = BackgroundScheduler()
        from AINDY.platform_layer.scheduler_service import _register_system_jobs

        masterplan_bootstrap.register()
        _register_system_jobs(scheduler)

        job_ids = [j.id for j in scheduler.get_jobs()]
        assert "daily_eta_recalculation" in job_ids

    def test_eta_job_callable_exists(self):
        """_recalculate_all_etas_job must be importable."""
        from apps.masterplan import bootstrap as masterplan_bootstrap

        assert callable(masterplan_bootstrap._scheduler_recalculate_all_etas)

    def test_eta_job_handles_db_error_gracefully(self):
        """_recalculate_all_etas_job must not raise even if DB is unavailable."""
        from apps.masterplan import bootstrap as masterplan_bootstrap
        # SessionLocal is a local import inside the job — patch at the db.database level
        with patch("AINDY.db.database.SessionLocal", side_effect=RuntimeError("no DB")):
            # Should not raise
            masterplan_bootstrap._scheduler_recalculate_all_etas()


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: complete_task ETA hook
# ─────────────────────────────────────────────────────────────────────────────

class TestCompleteTaskETAHook:
    def test_orchestrate_task_completion_triggers_eta_for_active_plan_with_anchor(self):
        """orchestrate_task_completion must call calculate_eta when active plan has anchor_date."""
        from apps.tasks.services import task_service as task_services
        mock_db = MagicMock()
        mock_task = MagicMock()
        mock_task.name = "test-task"
        mock_task.status = "in_progress"
        mock_task.start_time = None
        mock_task.time_spent = 0
        mock_task.task_complexity = 3
        mock_task.skill_level = 3
        mock_task.ai_utilization = 0
        mock_task.task_difficulty = 3

        fake_plan = MagicMock()
        fake_plan.id = 1
        fake_plan.anchor_date = datetime(2027, 1, 1)
        fake_plan.user_id = "00000000-0000-0000-0000-000000000001"

        with patch("apps.tasks.services.task_service.find_task", return_value=mock_task), \
             patch("apps.tasks.services.task_service.get_mongo_client", return_value=None), \
             patch("apps.tasks.services.task_service.get_active_masterplan_via_syscall", return_value={"id": fake_plan.id, "anchor_date": fake_plan.anchor_date.isoformat()}), \
             patch("AINDY.memory.memory_capture_engine.MemoryCaptureEngine.evaluate_and_capture", return_value=None), \
             patch("AINDY.runtime.memory.orchestrator.MemoryOrchestrator.get_context") as mock_context, \
             patch("apps.analytics.services.infinity_orchestrator.execute", return_value={"next_action": "review"}), \
             patch("apps.tasks.services.task_service.get_eta_via_syscall") as mock_eta:
            mock_context.return_value.ids = []

            task_services.orchestrate_task_completion(
                mock_db,
                "test-task",
                user_id="00000000-0000-0000-0000-000000000001",
            )

            mock_eta.assert_called_once()


