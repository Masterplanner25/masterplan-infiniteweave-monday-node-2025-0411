from __future__ import annotations

from pathlib import Path

import pytest


def test_scan_file_detects_module_level_as_hard(tmp_path):
    from AINDY.core.router_guard import _scan_file

    path = tmp_path / "hard_router.py"
    path.write_text(
        "from apps.tasks.services.task_service import get_next_ready_task\n",
        encoding="utf-8",
    )

    violations = _scan_file(path)

    assert len(violations) == 1
    assert violations[0].is_deferred is False


def test_scan_file_detects_function_body_as_soft(tmp_path):
    from AINDY.core.router_guard import _scan_file

    path = tmp_path / "soft_router.py"
    path.write_text(
        "def my_handler(state, context):\n"
        "    from apps.tasks.services.task_service import get_next_ready_task\n"
        "    return get_next_ready_task(state['user_id'], context['db'])\n",
        encoding="utf-8",
    )

    violations = _scan_file(path)

    assert len(violations) == 1
    assert violations[0].is_deferred is True


def test_validate_router_boundary_raises_only_on_hard_violations(tmp_path):
    from AINDY.core.router_guard import validate_router_boundary

    route_file = tmp_path / "test_router.py"
    route_file.write_text(
        "def handler():\n"
        "    from apps.tasks.services.task_service import x\n",
        encoding="utf-8",
    )

    validate_router_boundary(routes_dir=tmp_path, include_app_routes=False)


def test_validate_router_boundary_raises_on_module_level_violation(tmp_path):
    from AINDY.core.router_guard import RouterBoundaryViolation, validate_router_boundary

    route_file = tmp_path / "test_router.py"
    route_file.write_text(
        "from apps.tasks.services.task_service import x\n",
        encoding="utf-8",
    )

    with pytest.raises(RouterBoundaryViolation):
        validate_router_boundary(routes_dir=tmp_path, include_app_routes=False)


def test_app_route_same_domain_imports_are_ignored(tmp_path):
    from AINDY.core.router_guard import _scan_file

    route_dir = tmp_path / "apps" / "demo" / "routes"
    route_dir.mkdir(parents=True)
    route_file = route_dir / "demo_router.py"
    route_file.write_text(
        "from apps.demo.services.demo_service import run_demo\n",
        encoding="utf-8",
    )

    assert _scan_file(route_file) == []


def test_existing_app_routes_have_zero_hard_violations():
    from AINDY.core.router_guard import _scan_file

    hard: list[object] = []
    for route_file in Path("apps").glob("*/routes/*.py"):
        for violation in _scan_file(route_file):
            if not violation.is_deferred:
                hard.append(violation)

    assert hard == [], f"Hard boundary violations found in app routes: {hard}"
