"""
Sprint 6 + Sprint 7 Tests

Sprint 6: SQLAlchemy 2.0 — declarative_base import fix
Sprint 7: Memory prompt injection hooks for genesis_ai and leadgen_service
"""
import os
import warnings
import inspect
import pytest
from unittest.mock import MagicMock, patch

_ROUTES_DIR = os.path.join(os.path.dirname(__file__), "..", "routes")


def _read_source(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Sprint 6 — SQLAlchemy 2.0
# ---------------------------------------------------------------------------

class TestSprint6SQLAlchemy:

    def test_no_declarative_base_deprecation(self):
        """SQLAlchemy 2.0 import path — no declarative_base deprecation warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            import importlib
            import db.database
            importlib.reload(db.database)

            declarative_warnings = [
                x for x in w
                if issubclass(x.category, DeprecationWarning)
                and "declarative" in str(x.message).lower()
            ]
            assert len(declarative_warnings) == 0, (
                f"declarative_base deprecation warning still present: "
                f"{declarative_warnings}"
            )

    def test_sqlalchemy_base_importable(self):
        """Base should be importable from db.database."""
        from db.database import Base
        assert Base is not None

    def test_all_models_use_same_base(self):
        """All ORM models should share the same SQLAlchemy metadata registry."""
        from db.models.user import User
        from db.models.masterplan import MasterPlan
        from db.models.task import Task

        # All models sharing the same Base share the same MetaData object
        assert User.metadata is MasterPlan.metadata, (
            "User and MasterPlan do not share the same Base metadata"
        )
        assert User.metadata is Task.metadata, (
            "User and Task do not share the same Base metadata"
        )

    def test_new_import_path_in_source(self):
        """db/database.py must use sqlalchemy.orm import path."""
        import db.database as db_module
        source = inspect.getsource(db_module)
        assert "from sqlalchemy.ext.declarative" not in source, (
            "Old sqlalchemy.ext.declarative import still present in db.database"
        )
        assert "from sqlalchemy.orm import declarative_base" in source, (
            "New sqlalchemy.orm.declarative_base import not found in db.database"
        )


# ---------------------------------------------------------------------------
# Sprint 7 — Genesis Memory Hook
# ---------------------------------------------------------------------------

_DAO_PATH = "db.dao.memory_node_dao.MemoryNodeDAO"


class TestSprint7GenesisMemoryHook:

    def test_call_genesis_llm_accepts_user_id(self):
        """call_genesis_llm must accept user_id param."""
        from services.genesis_ai import call_genesis_llm
        sig = inspect.signature(call_genesis_llm)
        assert "user_id" in sig.parameters, (
            "call_genesis_llm missing user_id parameter"
        )

    def test_call_genesis_llm_accepts_db(self):
        """call_genesis_llm must accept db param."""
        from services.genesis_ai import call_genesis_llm
        sig = inspect.signature(call_genesis_llm)
        assert "db" in sig.parameters, (
            "call_genesis_llm missing db parameter"
        )

    def test_call_genesis_llm_user_id_defaults_none(self):
        """user_id must default to None for backward compatibility."""
        from services.genesis_ai import call_genesis_llm
        sig = inspect.signature(call_genesis_llm)
        assert sig.parameters["user_id"].default is None

    def test_call_genesis_llm_db_defaults_none(self):
        """db must default to None for backward compatibility."""
        from services.genesis_ai import call_genesis_llm
        sig = inspect.signature(call_genesis_llm)
        assert sig.parameters["db"].default is None

    def test_genesis_llm_recalls_before_call(self):
        """Genesis LLM must recall memories before the OpenAI call."""
        from services.genesis_ai import call_genesis_llm
        source = inspect.getsource(call_genesis_llm)
        assert "recall_memories" in source or "recall(" in source, (
            "call_genesis_llm missing memory recall"
        )

    def test_genesis_llm_writes_after_call(self):
        """Genesis LLM must write memory node after successful call."""
        from services.genesis_ai import call_genesis_llm
        source = inspect.getsource(call_genesis_llm)
        assert "MemoryCaptureEngine" in source or "evaluate_and_capture" in source, (
            "call_genesis_llm missing memory write"
        )

    def test_genesis_llm_writes_insight_node(self):
        """Genesis conversation memory node must use node_type='insight'."""
        from services.genesis_ai import call_genesis_llm
        source = inspect.getsource(call_genesis_llm)
        assert "insight" in source, (
            "call_genesis_llm does not write node_type='insight'"
        )

    def test_genesis_llm_memory_failure_does_not_crash(self, mocker):
        """Memory hook failure must not crash the Genesis LLM call."""
        mocker.patch("bridge.recall_memories", side_effect=Exception("memory down"))
        mocker.patch(
            f"{_DAO_PATH}.save",
            side_effect=Exception("db down"),
        )

        # Mock OpenAI call
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"reply": "test", "state_update": {}, "synthesis_ready": false}'
        )
        mocker.patch(
            "openai.resources.chat.completions.Completions.create",
            return_value=mock_response,
        )

        from services.genesis_ai import call_genesis_llm

        try:
            result = call_genesis_llm(
                message="test message",
                current_state={},
                user_id="test-user",
                db=MagicMock(),
            )
            assert result is not None
        except Exception as e:
            if "memory down" in str(e) or "db down" in str(e):
                pytest.fail(f"Memory failure leaked into Genesis LLM: {e}")

    def test_genesis_llm_no_user_id_skips_memory(self, mocker):
        """Without user_id, no memory calls should be made."""
        mock_recall = mocker.patch("bridge.recall_memories")
        mock_save = mocker.patch(f"{_DAO_PATH}.save")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"reply": "ok", "state_update": {}, "synthesis_ready": false}'
        )
        mocker.patch(
            "openai.resources.chat.completions.Completions.create",
            return_value=mock_response,
        )

        from services.genesis_ai import call_genesis_llm

        try:
            call_genesis_llm(message="hello", current_state={})
        except Exception:
            pass  # OpenAI mock path may differ by SDK version

        mock_recall.assert_not_called()
        mock_save.assert_not_called()

    def test_genesis_router_passes_user_id_to_llm(self):
        """genesis_router /message must pass user_id and db to call_genesis_llm."""
        source = _read_source(os.path.join(_ROUTES_DIR, "genesis_router.py"))
        assert "user_id=user_id_str" in source or "user_id=str(" in source, (
            "genesis_router does not pass user_id to call_genesis_llm"
        )
        assert "db=db" in source, (
            "genesis_router does not pass db to call_genesis_llm"
        )


# ---------------------------------------------------------------------------
# Sprint 7 — LeadGen Memory Hook
# ---------------------------------------------------------------------------

class TestSprint7LeadGenMemoryHook:

    def test_run_ai_search_accepts_user_id(self):
        """run_ai_search must accept user_id param."""
        from services.leadgen_service import run_ai_search
        sig = inspect.signature(run_ai_search)
        assert "user_id" in sig.parameters, (
            "run_ai_search missing user_id parameter"
        )

    def test_run_ai_search_accepts_db(self):
        """run_ai_search must accept db param."""
        from services.leadgen_service import run_ai_search
        sig = inspect.signature(run_ai_search)
        assert "db" in sig.parameters, (
            "run_ai_search missing db parameter"
        )

    def test_run_ai_search_user_id_defaults_none(self):
        """user_id must default to None for backward compatibility."""
        from services.leadgen_service import run_ai_search
        sig = inspect.signature(run_ai_search)
        assert sig.parameters["user_id"].default is None

    def test_create_lead_results_accepts_user_id(self):
        """create_lead_results pipeline must accept user_id param."""
        from services.leadgen_service import create_lead_results
        sig = inspect.signature(create_lead_results)
        assert "user_id" in sig.parameters, (
            "create_lead_results missing user_id parameter"
        )

    def test_leadgen_service_recalls_before_search(self):
        """leadgen_service must recall memories before search."""
        from services import leadgen_service
        source = inspect.getsource(leadgen_service)
        assert "recall_memories" in source or "recall(" in source, (
            "leadgen_service missing memory recall"
        )

    def test_leadgen_service_writes_after_search(self):
        """leadgen_service must write memory node after results."""
        from services import leadgen_service
        source = inspect.getsource(leadgen_service)
        assert "MemoryCaptureEngine" in source or "evaluate_and_capture" in source, (
            "leadgen_service missing memory write"
        )

    def test_leadgen_writes_outcome_node(self):
        """LeadGen memory node must use node_type='outcome'."""
        from services.leadgen_service import run_ai_search
        source = inspect.getsource(run_ai_search)
        assert "outcome" in source, (
            "run_ai_search does not write node_type='outcome'"
        )

    def test_leadgen_memory_failure_does_not_crash(self, mocker):
        """Memory hook failure must not crash LeadGen search."""
        mocker.patch("bridge.recall_memories", side_effect=Exception("memory down"))
        mocker.patch(
            f"{_DAO_PATH}.save",
            side_effect=Exception("db down"),
        )

        from services import leadgen_service

        try:
            result = leadgen_service.run_ai_search(
                query="test query",
                user_id="test-user",
                db=MagicMock(),
            )
            # Should return results despite memory failures
            assert result is not None
            assert len(result) > 0
        except Exception as e:
            if "memory down" in str(e) or "db down" in str(e):
                pytest.fail(f"Memory failure leaked into LeadGen: {e}")

    def test_leadgen_no_user_id_skips_memory(self, mocker):
        """Without user_id, no memory calls should be made."""
        mock_recall = mocker.patch("bridge.recall_memories")
        mock_save = mocker.patch(f"{_DAO_PATH}.save")

        from services.leadgen_service import run_ai_search
        run_ai_search(query="test query")

        mock_recall.assert_not_called()
        mock_save.assert_not_called()

    def test_leadgen_router_passes_user_id(self):
        """leadgen_router must pass user_id to create_lead_results."""
        source = _read_source(os.path.join(_ROUTES_DIR, "leadgen_router.py"))
        assert "user_id=" in source, (
            "leadgen_router does not pass user_id to create_lead_results"
        )
