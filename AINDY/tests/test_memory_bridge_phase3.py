"""
test_memory_bridge_phase3.py

Tests for Memory Bridge Phase 3: memory write/recall hooks wired into
ARM analysis, ARM code generation, Task completion, and Genesis lock/activate.

All DB and OpenAI calls are mocked. Tests verify:
- Hook fires on success
- Hook is silenced on failure (fire-and-forget)
- recall_memories() returns [] gracefully when DB is unavailable
- node_type assignments are correct
"""
import pytest
from unittest.mock import MagicMock, patch, call

# MemoryNodeDAO lives here — all lazy imports inside bridge/arm/task/genesis
# ultimately resolve to this module for the class definition.
_DAO_PATH = "db.dao.memory_node_dao.MemoryNodeDAO"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_EMBEDDING = [1.0] + [0.0] * 1535

MOCK_NODE_DICT = {
    "id": "test-uuid-1234",
    "content": "test content",
    "tags": ["arm", "analysis"],
    "node_type": "outcome",
    "source": "arm_analysis",
    "user_id": "user-42",
    "extra": {},
    "created_at": "2026-03-18T00:00:00",
    "updated_at": "2026-03-18T00:00:00",
}

MOCK_RECALL_RESULTS = [
    {
        "id": "prior-uuid",
        "content": "ARM analysis of app.py: Good structure",
        "node_type": "outcome",
        "tags": ["arm", "analysis"],
        "resonance_score": 0.85,
    }
]


# ---------------------------------------------------------------------------
# TestRecallMemoriesBridge
# ---------------------------------------------------------------------------

class TestRecallMemoriesBridge:
    """Tests for bridge.recall_memories()"""

    def test_recall_no_db_returns_empty_list(self):
        from bridge import recall_memories
        result = recall_memories(query="test", db=None)
        assert result == []

    def test_recall_delegates_to_dao(self):
        mock_db = MagicMock()
        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.recall.return_value = MOCK_RECALL_RESULTS
            MockDAO.return_value = mock_dao_instance

            from bridge import recall_memories
            result = recall_memories(
                query="test query",
                tags=["arm"],
                limit=3,
                user_id="user-42",
                db=mock_db,
            )

        assert result == MOCK_RECALL_RESULTS
        mock_dao_instance.recall.assert_called_once_with(
            query="test query",
            tags=["arm"],
            limit=3,
            user_id="user-42",
            node_type=None,
        )

    def test_recall_returns_empty_list_on_dao_failure(self):
        mock_db = MagicMock()
        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.recall.side_effect = Exception("DB down")
            MockDAO.return_value = mock_dao_instance

            from bridge import recall_memories
            result = recall_memories(query="test", db=mock_db)

        assert result == []

    def test_recall_with_node_type_filter(self):
        mock_db = MagicMock()
        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.recall.return_value = []
            MockDAO.return_value = mock_dao_instance

            from bridge import recall_memories
            recall_memories(query="decision", node_type="decision", db=mock_db)

        mock_dao_instance.recall.assert_called_once_with(
            query="decision",
            tags=None,
            limit=5,
            user_id=None,
            node_type="decision",
        )


# ---------------------------------------------------------------------------
# TestCreateMemoryNodeBridge
# ---------------------------------------------------------------------------

class TestCreateMemoryNodeBridge:
    """Tests for updated bridge.create_memory_node() using new DAO."""

    def test_create_node_no_db_returns_transient(self):
        from bridge import create_memory_node
        from bridge.bridge import MemoryNode
        result = create_memory_node(content="test", db=None)
        assert isinstance(result, MemoryNode)
        assert result.content == "test"

    def test_create_node_uses_new_dao(self):
        mock_db = MagicMock()
        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.save.return_value = MOCK_NODE_DICT
            MockDAO.return_value = mock_dao_instance

            from bridge import create_memory_node
            result = create_memory_node(
                content="ARM analysis of app.py",
                source="arm_analysis",
                tags=["arm", "analysis"],
                user_id="user-42",
                db=mock_db,
                node_type="outcome",
            )

        assert result == MOCK_NODE_DICT
        mock_dao_instance.save.assert_called_once_with(
            content="ARM analysis of app.py",
            source="arm_analysis",
            tags=["arm", "analysis"],
            user_id="user-42",
            node_type="outcome",
        )

    def test_create_node_default_node_type_is_none(self):
        """Default node_type should be None (not 'generic') to pass ORM validation."""
        mock_db = MagicMock()
        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.save.return_value = MOCK_NODE_DICT
            MockDAO.return_value = mock_dao_instance

            from bridge import create_memory_node
            create_memory_node(content="no type set", db=mock_db)

        _, kwargs = mock_dao_instance.save.call_args
        assert kwargs.get("node_type") is None


# ---------------------------------------------------------------------------
# TestARMAnalysisMemoryHook
# ---------------------------------------------------------------------------

class TestARMAnalysisMemoryHook:
    """Tests for memory hooks in deepseek_code_analyzer.run_analysis()"""

    def _make_analyzer(self):
        """Build a DeepSeekCodeAnalyzer with mocked dependencies."""
        import pathlib
        from modules.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer
        with patch("modules.deepseek.deepseek_code_analyzer.OpenAI"):
            analyzer = DeepSeekCodeAnalyzer.__new__(DeepSeekCodeAnalyzer)
        analyzer.client = MagicMock()
        analyzer.config = {
            "analysis_model": "gpt-4o",
            "temperature": 0.2,
        }
        analyzer.config_manager = MagicMock()
        analyzer.config_manager.calculate_task_priority.return_value = 5.0
        analyzer.validator = MagicMock()
        analyzer.file_processor = MagicMock()
        return analyzer

    def _mock_path(self, name="app.py", suffix=".py"):
        mock_path = MagicMock()
        mock_path.name = name
        mock_path.suffix = suffix
        mock_path.__str__ = lambda self: f"/fake/{name}"
        return mock_path

    def _mock_openai_response(self, content='{"summary": "Clean code", "findings": []}'):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = content
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        return mock_response

    def test_analysis_writes_outcome_node_on_success(self):
        analyzer = self._make_analyzer()
        mock_db = MagicMock()
        mock_path = self._mock_path()
        analyzer.validator.full_file_validation.return_value = (mock_path, "def foo(): pass")
        analyzer.file_processor.chunk_content.return_value = ["def foo(): pass"]
        analyzer.client.chat.completions.create.return_value = self._mock_openai_response()

        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.recall.return_value = []
            mock_dao_instance.save.return_value = MOCK_NODE_DICT
            MockDAO.return_value = mock_dao_instance

            result = analyzer.run_analysis(
                file_path="/fake/app.py",
                db=mock_db,
                user_id="user-42",
            )

        save_calls = mock_dao_instance.save.call_args_list
        assert len(save_calls) >= 1
        write_kwargs = save_calls[0][1]
        assert write_kwargs["node_type"] == "outcome"
        assert write_kwargs["source"] == "arm_analysis"
        assert "app.py" in write_kwargs["content"] or "ARM analysis" in write_kwargs["content"]

    def test_analysis_recall_runs_before_prompt(self):
        """Verify that recall_memories is called (retrieval hook fires)."""
        analyzer = self._make_analyzer()
        mock_db = MagicMock()
        mock_path = self._mock_path()
        analyzer.validator.full_file_validation.return_value = (mock_path, "code")
        analyzer.file_processor.chunk_content.return_value = ["code"]
        analyzer.client.chat.completions.create.return_value = self._mock_openai_response('{"summary": "OK"}')

        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.recall.return_value = MOCK_RECALL_RESULTS
            mock_dao_instance.save.return_value = MOCK_NODE_DICT
            MockDAO.return_value = mock_dao_instance

            analyzer.run_analysis(
                file_path="/fake/app.py",
                db=mock_db,
                user_id="user-42",
            )

        recall_calls = mock_dao_instance.recall.call_args_list
        assert len(recall_calls) >= 1
        recall_kwargs = recall_calls[0][1]
        assert "arm" in recall_kwargs.get("tags", [])

    def test_analysis_memory_write_skipped_when_no_user_id(self):
        analyzer = self._make_analyzer()
        mock_db = MagicMock()
        mock_path = self._mock_path()
        analyzer.validator.full_file_validation.return_value = (mock_path, "code")
        analyzer.file_processor.chunk_content.return_value = ["code"]
        analyzer.client.chat.completions.create.return_value = self._mock_openai_response('{"summary": "OK"}')

        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.recall.return_value = []
            mock_dao_instance.save.return_value = MOCK_NODE_DICT
            MockDAO.return_value = mock_dao_instance

            analyzer.run_analysis(file_path="/fake/app.py", db=mock_db, user_id=None)

        mock_dao_instance.save.assert_not_called()

    def test_analysis_memory_failure_does_not_raise(self):
        """Memory write failure must not propagate to caller."""
        analyzer = self._make_analyzer()
        mock_db = MagicMock()
        mock_path = self._mock_path()
        analyzer.validator.full_file_validation.return_value = (mock_path, "code")
        analyzer.file_processor.chunk_content.return_value = ["code"]
        analyzer.client.chat.completions.create.return_value = self._mock_openai_response('{"summary": "OK"}')

        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.recall.return_value = []
            mock_dao_instance.save.side_effect = Exception("DB exploded")
            MockDAO.return_value = mock_dao_instance

            result = analyzer.run_analysis(
                file_path="/fake/app.py",
                db=mock_db,
                user_id="user-42",
            )

        assert "session_id" in result or "summary" in result


# ---------------------------------------------------------------------------
# TestARMCodegenMemoryHook
# ---------------------------------------------------------------------------

class TestARMCodegenMemoryHook:
    """Tests for memory write hook in deepseek_code_analyzer.generate_code()"""

    def _make_analyzer(self):
        from modules.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer
        with patch("modules.deepseek.deepseek_code_analyzer.OpenAI"):
            analyzer = DeepSeekCodeAnalyzer.__new__(DeepSeekCodeAnalyzer)
        analyzer.client = MagicMock()
        analyzer.config = {
            "generation_model": "gpt-4o",
            "generation_temperature": 0.4,
        }
        analyzer.config_manager = MagicMock()
        analyzer.config_manager.calculate_task_priority.return_value = 5.0
        analyzer.validator = MagicMock()
        return analyzer

    def _mock_codegen_response(self, content='{"generated_code": "def x(): pass", "language": "python"}'):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = content
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 10
        return mock_response

    def test_codegen_writes_outcome_node(self):
        analyzer = self._make_analyzer()
        mock_db = MagicMock()
        analyzer.client.chat.completions.create.return_value = self._mock_codegen_response()

        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.save.return_value = MOCK_NODE_DICT
            MockDAO.return_value = mock_dao_instance

            result = analyzer.generate_code(
                prompt="Write a Python function to add two numbers",
                language="python",
                db=mock_db,
                user_id="user-42",
            )

        save_calls = mock_dao_instance.save.call_args_list
        assert len(save_calls) >= 1
        write_kwargs = save_calls[0][1]
        assert write_kwargs["node_type"] == "outcome"
        assert write_kwargs["source"] == "arm_codegen"
        assert "python" in write_kwargs["tags"]

    def test_codegen_memory_failure_does_not_raise(self):
        analyzer = self._make_analyzer()
        mock_db = MagicMock()
        analyzer.client.chat.completions.create.return_value = self._mock_codegen_response()

        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.save.side_effect = Exception("memory failure")
            MockDAO.return_value = mock_dao_instance

            result = analyzer.generate_code(
                prompt="test prompt",
                language="python",
                db=mock_db,
                user_id="user-42",
            )

        assert "session_id" in result

    def test_codegen_no_user_id_skips_memory(self):
        analyzer = self._make_analyzer()
        mock_db = MagicMock()
        analyzer.client.chat.completions.create.return_value = self._mock_codegen_response()

        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.save.return_value = MOCK_NODE_DICT
            MockDAO.return_value = mock_dao_instance

            analyzer.generate_code(
                prompt="test",
                language="python",
                db=mock_db,
                user_id=None,
            )

        mock_dao_instance.save.assert_not_called()


# ---------------------------------------------------------------------------
# TestTaskCompletionMemoryHook
# ---------------------------------------------------------------------------

class TestTaskCompletionMemoryHook:
    """Tests for memory write hook in task_services.complete_task()"""

    def _make_task(self, name="Test Task"):
        task = MagicMock()
        task.name = name
        task.status = "in_progress"
        task.start_time = None
        task.time_spent = 0
        task.task_complexity = 1
        task.skill_level = 1
        task.ai_utilization = 1
        task.task_difficulty = 1
        return task

    def test_complete_task_writes_outcome_node(self):
        mock_db = MagicMock()
        mock_task = self._make_task()

        with patch("services.task_services.find_task", return_value=mock_task), \
             patch("services.task_services.calculate_twr", return_value=8.5), \
             patch("services.task_services.save_calculation"), \
             patch("services.task_services.get_mongo_client", side_effect=Exception("no mongo")), \
             patch(_DAO_PATH) as MockDAO:

            mock_dao_instance = MagicMock()
            mock_dao_instance.save.return_value = MOCK_NODE_DICT
            MockDAO.return_value = mock_dao_instance

            from services.task_services import complete_task
            result = complete_task(mock_db, "Test Task", user_id="user-42")

        assert result  # returned something
        save_calls = mock_dao_instance.save.call_args_list
        assert len(save_calls) >= 1
        write_kwargs = save_calls[0][1]
        assert write_kwargs["node_type"] == "outcome"
        assert write_kwargs["source"] == "task_service"
        assert "task" in write_kwargs["tags"]
        assert "completion" in write_kwargs["tags"]

    def test_complete_task_no_user_id_skips_memory(self):
        mock_db = MagicMock()
        mock_task = self._make_task()

        with patch("services.task_services.find_task", return_value=mock_task), \
             patch("services.task_services.calculate_twr", return_value=5.0), \
             patch("services.task_services.save_calculation"), \
             patch("services.task_services.get_mongo_client", side_effect=Exception("no mongo")), \
             patch(_DAO_PATH) as MockDAO:

            mock_dao_instance = MagicMock()
            MockDAO.return_value = mock_dao_instance

            from services.task_services import complete_task
            complete_task(mock_db, "Test Task")  # no user_id

        mock_dao_instance.save.assert_not_called()

    def test_complete_task_memory_failure_does_not_raise(self):
        mock_db = MagicMock()
        mock_task = self._make_task()

        with patch("services.task_services.find_task", return_value=mock_task), \
             patch("services.task_services.calculate_twr", return_value=5.0), \
             patch("services.task_services.save_calculation"), \
             patch("services.task_services.get_mongo_client", side_effect=Exception("no mongo")), \
             patch(_DAO_PATH) as MockDAO:

            mock_dao_instance = MagicMock()
            mock_dao_instance.save.side_effect = Exception("memory failure")
            MockDAO.return_value = mock_dao_instance

            from services.task_services import complete_task
            result = complete_task(mock_db, "Test Task", user_id="user-42")

        assert result  # did not raise

    def test_complete_task_signature_accepts_user_id(self):
        """Verify backward-compat: user_id is optional, existing callers unaffected."""
        import inspect
        from services.task_services import complete_task
        sig = inspect.signature(complete_task)
        params = sig.parameters
        assert "user_id" in params
        assert params["user_id"].default is None


# ---------------------------------------------------------------------------
# TestGenesisMemoryHooks
# ---------------------------------------------------------------------------

class TestGenesisMemoryHooks:
    """Tests for memory write hooks in genesis_router.lock_masterplan() and activate_masterplan()"""

    def _make_app(self, mock_db, mock_user):
        """Build a test FastAPI app with overridden dependencies."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routes.genesis_router import router
        from db.database import get_db
        from services.auth_service import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_current_user] = lambda: mock_user
        return TestClient(app)

    def test_lock_writes_decision_node(self):
        mock_db = MagicMock()
        mock_masterplan = MagicMock()
        mock_masterplan.id = 99
        mock_masterplan.version_label = "V1"
        mock_masterplan.posture = "aggressive"
        mock_user = {"sub": "user-42"}

        with patch("routes.genesis_router._get_user_session"), \
             patch("routes.genesis_router.create_masterplan_from_genesis", return_value=mock_masterplan), \
             patch(_DAO_PATH) as MockDAO:

            mock_dao_instance = MagicMock()
            mock_dao_instance.save.return_value = MOCK_NODE_DICT
            MockDAO.return_value = mock_dao_instance

            client = self._make_app(mock_db, mock_user)
            response = client.post(
                "/genesis/lock",
                json={"session_id": 1, "draft": {"vision_summary": "Build empire"}},
            )

        assert response.status_code == 200
        save_calls = mock_dao_instance.save.call_args_list
        assert len(save_calls) >= 1
        lock_call = save_calls[0][1]
        assert lock_call["node_type"] == "decision"
        assert lock_call["source"] == "genesis_lock"

    def test_lock_memory_failure_does_not_fail_endpoint(self):
        mock_db = MagicMock()
        mock_masterplan = MagicMock()
        mock_masterplan.id = 99
        mock_masterplan.version_label = "V1"
        mock_masterplan.posture = "balanced"
        mock_user = {"sub": "user-42"}

        with patch("routes.genesis_router._get_user_session"), \
             patch("routes.genesis_router.create_masterplan_from_genesis", return_value=mock_masterplan), \
             patch(_DAO_PATH) as MockDAO:

            mock_dao_instance = MagicMock()
            mock_dao_instance.save.side_effect = Exception("memory down")
            MockDAO.return_value = mock_dao_instance

            client = self._make_app(mock_db, mock_user)
            response = client.post(
                "/genesis/lock",
                json={"session_id": 1, "draft": {"vision_summary": "Build empire"}},
            )

        assert response.status_code == 200

    def test_activate_writes_decision_node(self):
        mock_plan = MagicMock()
        mock_plan.id = 99
        mock_plan.version_label = "V1"
        mock_plan.is_active = False
        mock_plan.status = "locked"
        mock_user = {"sub": "user-42"}

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_plan
        mock_query.filter.return_value.update.return_value = None
        mock_db.query.return_value = mock_query

        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.save.return_value = MOCK_NODE_DICT
            MockDAO.return_value = mock_dao_instance

            client = self._make_app(mock_db, mock_user)
            response = client.post("/genesis/99/activate")

        assert response.status_code == 200
        save_calls = mock_dao_instance.save.call_args_list
        assert len(save_calls) >= 1
        activate_call = save_calls[0][1]
        assert activate_call["node_type"] == "decision"
        assert activate_call["source"] == "genesis_activate"

    def test_activate_memory_failure_does_not_fail_endpoint(self):
        mock_plan = MagicMock()
        mock_plan.id = 99
        mock_plan.version_label = "V1"
        mock_plan.is_active = False
        mock_plan.status = "locked"
        mock_user = {"sub": "user-42"}

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_plan
        mock_query.filter.return_value.update.return_value = None
        mock_db.query.return_value = mock_query

        with patch(_DAO_PATH) as MockDAO:
            mock_dao_instance = MagicMock()
            mock_dao_instance.save.side_effect = Exception("memory down")
            MockDAO.return_value = mock_dao_instance

            client = self._make_app(mock_db, mock_user)
            response = client.post("/genesis/99/activate")

        assert response.status_code == 200
