"""Smoke tests for the analytics public contract."""

import importlib
import pathlib


def test_public_module_importable():
    mod = importlib.import_module("apps.analytics.public")
    assert hasattr(mod, "calculate_twr")
    assert hasattr(mod, "save_calculation")
    assert hasattr(mod, "get_user_kpi_snapshot")
    assert hasattr(mod, "run_infinity_orchestrator")
    assert hasattr(mod, "get_latest_adjustment")


def test_no_private_service_imports_in_external_callers():
    callers = [
        "apps/tasks/services/task_service.py",
        "AINDY/routes/agent_router.py",
        "apps/agent/flows/agent_flows.py",
        "apps/arm/services/deepseek/deepseek_code_analyzer.py",
    ]
    violations = []
    for path in callers:
        source = pathlib.Path(path).read_text(encoding="utf-8")
        if "apps.analytics.services." in source:
            violations.append(path)
    assert violations == [], f"Files importing analytics internals: {violations}"
