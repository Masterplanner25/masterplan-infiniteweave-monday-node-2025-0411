from __future__ import annotations

import builtins
import importlib
import sys


def _block_imports(monkeypatch, blocked_modules: set[str]):
    original_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in blocked_modules:
            raise ImportError(f"blocked import: {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)


def test_infinity_loop_imports_without_tasks_or_masterplan_modules(monkeypatch):
    _block_imports(
        monkeypatch,
        {
            "apps.automation.models",
            "apps.tasks.models",
            "apps.tasks.services.task_service",
            "apps.masterplan.services.goal_service",
        },
    )
    module_name = "apps.analytics.services.infinity_loop"
    original = sys.modules.get(module_name)
    if original is not None:
        mod = importlib.reload(original)
        assert mod is original
        return

    mod = importlib.import_module(module_name)
    assert mod is not None
    sys.modules.pop(module_name, None)


def test_infinity_orchestrator_imports_without_cross_domain_modules(monkeypatch):
    _block_imports(
        monkeypatch,
        {
            "apps.identity.services.identity_boot_service",
            "apps.masterplan.services.goal_service",
            "apps.social.services.social_performance_service",
            "apps.tasks.services.task_service",
        },
    )
    module_name = "apps.analytics.services.infinity_orchestrator"
    original = sys.modules.get(module_name)
    if original is not None:
        mod = importlib.reload(original)
        assert mod is original
        return

    mod = importlib.import_module(module_name)
    assert mod is not None
    sys.modules.pop(module_name, None)


def test_analytics_dependency_adapter_imports_without_cross_domain_modules(monkeypatch):
    _block_imports(
        monkeypatch,
        {
            "apps.automation.models",
            "apps.identity.services.identity_boot_service",
            "apps.social.services.social_performance_service",
            "apps.tasks.models",
            "apps.tasks.services.task_service",
        },
    )
    module_name = "apps.analytics.services.dependency_adapter"
    original = sys.modules.get(module_name)
    if original is not None:
        mod = importlib.reload(original)
        assert mod is original
        return

    mod = importlib.import_module(module_name)
    assert mod is not None
    sys.modules.pop(module_name, None)


def test_infinity_modules_import_without_memory_scoring_service(monkeypatch):
    module_names = [
        "apps.analytics.services.infinity_orchestrator",
        "apps.analytics.services.infinity_loop",
    ]

    for module_name in module_names:
        sys.modules.pop(module_name, None)

    with monkeypatch.context() as m:
        m.setitem(sys.modules, "AINDY.memory.memory_scoring_service", None)
        for module_name in module_names:
            mod = importlib.import_module(module_name)
            assert mod is not None
            sys.modules.pop(module_name, None)
