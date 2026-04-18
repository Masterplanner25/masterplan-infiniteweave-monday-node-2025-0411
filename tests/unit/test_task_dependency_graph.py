from types import SimpleNamespace

import pytest

from apps.tasks.services.task_service import build_task_graph


def _task(task_id, name, status="pending", priority="medium", parent_task_id=None, depends_on=None):
    return SimpleNamespace(
        id=task_id,
        name=name,
        status=status,
        priority=priority,
        parent_task_id=parent_task_id,
        depends_on=depends_on or [],
    )


def test_build_task_graph_orders_dependencies_before_children():
    parent = _task(1, "parent", status="completed")
    child = _task(2, "child", depends_on=[{"task_id": 1, "dependency_type": "hard"}])
    grandchild = _task(3, "grandchild", depends_on=[{"task_id": 2, "dependency_type": "hard"}])

    graph = build_task_graph([grandchild, child, parent])

    assert graph["topological_order"] == [1, 2, 3]
    assert graph["ready"] == [2]
    assert 3 in graph["blocked"]


def test_build_task_graph_detects_cycles():
    a = _task(1, "a", depends_on=[{"task_id": 2, "dependency_type": "hard"}])
    b = _task(2, "b", depends_on=[{"task_id": 1, "dependency_type": "hard"}])

    with pytest.raises(ValueError, match="task_dependency_cycle_detected"):
        build_task_graph([a, b])

