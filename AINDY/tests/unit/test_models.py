"""
test_models.py
──────────────
Model structure tests.

Tests cover:
- Task model (db/models/task.py)
- CalculationResult model (db/models/calculation.py)
- MemoryNodeModel and MemoryLinkModel (services/memory_persistence.py)
- Known bugs: wrong-table usage, orphan function
"""
import pytest


class TestTaskModel:
    def test_task_model_importable(self):
        from AINDY.db.models.task import Task
        assert Task is not None

    def test_task_model_tablename(self):
        from AINDY.db.models.task import Task
        assert Task.__tablename__ == "tasks"

    def test_task_has_required_columns(self):
        from AINDY.db.models.task import Task
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(Task)
        col_names = [c.key for c in mapper.attrs]
        for required in ["id", "name", "status", "time_spent", "task_complexity",
                         "skill_level", "ai_utilization", "task_difficulty"]:
            assert required in col_names, (
                f"Task model missing column: {required}. Columns: {col_names}"
            )

    def test_task_has_scheduling_columns(self):
        from AINDY.db.models.task import Task
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(Task)
        col_names = [c.key for c in mapper.attrs]
        for col in ["due_date", "start_time", "end_time", "reminder_time", "recurrence"]:
            assert col in col_names, f"Task missing scheduling column: {col}"

    def test_task_has_user_fk(self):
        """Task model now includes user_id for ownership scoping."""
        from AINDY.db.models.task import Task
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(Task)
        col_names = [c.key for c in mapper.attrs]
        assert "user_id" in col_names, (
            "user_id FK missing from Task model"
        )


class TestCalculationResultModel:
    def test_calculation_result_importable(self):
        from AINDY.db.models.calculation import CalculationResult
        assert CalculationResult is not None

    def test_calculation_result_tablename(self):
        from AINDY.db.models.calculation import CalculationResult
        assert CalculationResult.__tablename__ == "calculation_results"

    def test_calculation_result_columns(self):
        from AINDY.db.models.calculation import CalculationResult
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(CalculationResult)
        col_names = [c.key for c in mapper.attrs]
        for col in ["id", "metric_name", "result_value", "created_at"]:
            assert col in col_names, f"CalculationResult missing column: {col}"

    def test_calculation_result_wrong_table_bug_documented(self):
        """
        DIAGNOSTIC BUG: bridge/bridge.py::create_memory_node() writes CalculationResult
        rows to store memory nodes. This table is NOT intended for memory storage.

        ADDITIONAL BUG: bridge.py uses: from db.models.models import CalculationResult
        but db/models/models.py does NOT EXIST. The correct path is db.models.calculation.

        This test documents the wrong-table bug by confirming:
        1. CalculationResult has no 'content', 'tags', or 'node_type' columns
        2. These are the fields that should be in MemoryNodeModel
        3. db/models/models.py does not exist (import would fail)
        """
        from AINDY.db.models.calculation import CalculationResult
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(CalculationResult)
        col_names = [c.key for c in mapper.attrs]

        # CalculationResult DOES NOT have memory node fields
        assert "content" not in col_names, (
            "CalculationResult unexpectedly has 'content' column — maybe wrong-table bug was fixed?"
        )
        assert "tags" not in col_names, (
            "CalculationResult unexpectedly has 'tags' column"
        )
        assert "node_type" not in col_names, (
            "CalculationResult unexpectedly has 'node_type' column"
        )

        # Additional: confirm db/models/models.py doesn't exist
        import importlib.util
        spec = importlib.util.find_spec("db.models.models")
        assert spec is None, (
            "db/models/models.py now exists — bridge.py import bug may be partially fixed. "
            "Verify create_memory_node() still uses the correct table."
        )

        # The correct table for memory nodes is memory_nodes via MemoryNodeModel
        from AINDY.memory.memory_persistence import MemoryNodeModel
        mapper2 = sa_inspect(MemoryNodeModel)
        col_names2 = [c.key for c in mapper2.attrs]
        assert "content" in col_names2
        assert "tags" in col_names2
        assert "node_type" in col_names2


class TestMemoryPersistenceModels:
    def test_memory_node_model_importable(self):
        from AINDY.memory.memory_persistence import MemoryNodeModel
        assert MemoryNodeModel is not None

    def test_memory_node_model_tablename(self):
        from AINDY.memory.memory_persistence import MemoryNodeModel
        assert MemoryNodeModel.__tablename__ == "memory_nodes"

    def test_memory_node_model_columns(self):
        from AINDY.memory.memory_persistence import MemoryNodeModel
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(MemoryNodeModel)
        col_names = [c.key for c in mapper.attrs]
        for col in ["id", "content", "tags", "node_type", "created_at", "updated_at", "extra"]:
            assert col in col_names, f"MemoryNodeModel missing column: {col}"

    def test_memory_node_has_embedding_column(self):
        """
        Memory Bridge Phase 2: MemoryNodeModel has an 'embedding' VECTOR(1536) column.
        Semantic memory search is now operational.
        """
        from AINDY.memory.memory_persistence import MemoryNodeModel
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(MemoryNodeModel)
        col_names = [c.key for c in mapper.attrs]
        assert "embedding" in col_names, (
            "MemoryNodeModel missing 'embedding' column. "
            "Run: alembic upgrade head"
        )

    def test_memory_link_model_importable(self):
        from AINDY.memory.memory_persistence import MemoryLinkModel
        assert MemoryLinkModel is not None

    def test_memory_link_model_tablename(self):
        from AINDY.memory.memory_persistence import MemoryLinkModel
        assert MemoryLinkModel.__tablename__ == "memory_links"

    def test_memory_link_model_columns(self):
        from AINDY.memory.memory_persistence import MemoryLinkModel
        from sqlalchemy import inspect as sa_inspect
        mapper = sa_inspect(MemoryLinkModel)
        col_names = [c.key for c in mapper.attrs]
        for col in ["id", "source_node_id", "target_node_id", "link_type", "strength", "created_at"]:
            assert col in col_names, f"MemoryLinkModel missing column: {col}"


