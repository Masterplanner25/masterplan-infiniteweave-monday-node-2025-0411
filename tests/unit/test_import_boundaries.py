"""
Import boundary enforcement tests.

These tests assert that specific cross-domain imports documented in
docs/architecture/CROSS_DOMAIN_COUPLING.md have been removed or are
not present in violation of the coupling policy.

Tests here fail when coupling is introduced. That is intentional.
When a coupling is RESOLVED, add a test asserting the import is gone.
When a coupling is ACCEPTED, add a comment explaining why.
"""

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).parent.parent.parent
AINDY_ROOT = ROOT / "AINDY"


ALLOWED_AINDY_TO_APPS_IMPORTS: dict[str, dict[str, str]] = {}


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def _iter_aindy_import_statements() -> list[tuple[str, str]]:
    statements: set[tuple[str, str]] = set()

    for source_file in AINDY_ROOT.glob("**/*.py"):
        source = source_file.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(source_file))
        relative_path = source_file.relative_to(ROOT).as_posix()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "apps" or alias.name.startswith("apps."):
                        statement = f"import {alias.name}"
                        if alias.asname:
                            statement += f" as {alias.asname}"
                        statements.add((relative_path, statement))
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "apps" or node.module.startswith("apps.")):
                    imported_names = ", ".join(
                        alias.name if alias.asname is None else f"{alias.name} as {alias.asname}"
                        for alias in node.names
                    )
                    statements.add((relative_path, f"from {node.module} import {imported_names}"))

    return sorted(statements)


def test_aindy_tree_direct_app_imports_are_explicit_and_minimal():
    """AINDY must not directly import apps.*."""
    unexpected: list[str] = []
    seen_allowed: set[tuple[str, str]] = set()

    for relative_path, statement in _iter_aindy_import_statements():
        allowed_for_file = ALLOWED_AINDY_TO_APPS_IMPORTS.get(relative_path, {})
        if statement in allowed_for_file:
            seen_allowed.add((relative_path, statement))
            continue
        unexpected.append(f"{relative_path}: {statement}")

    missing_allowed = []
    for relative_path, allowed_statements in ALLOWED_AINDY_TO_APPS_IMPORTS.items():
        for statement in allowed_statements:
            if (relative_path, statement) not in seen_allowed:
                missing_allowed.append(f"{relative_path}: {statement}")

    assert not unexpected, (
        "Found unauthorized direct imports from AINDY/ into apps.*:\n- "
        + "\n- ".join(unexpected)
        + "\nThe runtime must interact with plugins only through explicit runtime-owned contracts."
    )
    assert not missing_allowed, (
        "Allowlist drift: remove stale AINDY -> apps import exceptions that no longer exist:\n- "
        + "\n- ".join(missing_allowed)
    )


def test_aindy_tree_has_no_direct_agent_model_imports():
    """Runtime code must not depend on apps.agent.models.* after model promotion."""
    direct_agent_model_imports = [
        f"{relative_path}: {statement}"
        for relative_path, statement in _iter_aindy_import_statements()
        if statement.startswith("from apps.agent.models")
        or statement.startswith("import apps.agent.models")
    ]
    assert not direct_agent_model_imports, (
        "Found forbidden runtime imports from apps.agent.models.*:\n- "
        + "\n- ".join(direct_agent_model_imports)
        + "\nAgent persistence models must be imported from AINDY.db.models."
    )


def test_aindy_tree_has_no_direct_apps_agent_imports():
    """Runtime code must not import app-layer agent modules directly."""
    direct_agent_imports = []
    for source_file in AINDY_ROOT.glob("**/*.py"):
        source = source_file.read_text(encoding="utf-8-sig")
        if "apps.agent" in source:
            direct_agent_imports.append(f"{source_file.relative_to(ROOT).as_posix()}: contains apps.agent")

    assert not direct_agent_imports, (
        "Found forbidden app-layer agent references under AINDY/:\n- "
        + "\n- ".join(direct_agent_imports)
        + "\nRuntime code must depend on runtime-owned modules or explicit platform interfaces."
    )


def test_aindy_tree_has_no_direct_apps_references():
    """Runtime code must not contain direct apps.* import statements or references."""
    direct_app_references = []
    for source_file in AINDY_ROOT.glob("**/*.py"):
        source = source_file.read_text(encoding="utf-8-sig")
        if "from apps." in source or "import apps." in source:
            direct_app_references.append(f"{source_file.relative_to(ROOT).as_posix()}: contains direct apps.* import text")

    assert not direct_app_references, (
        "Found forbidden direct apps.* references under AINDY/:\n- "
        + "\n- ".join(direct_app_references)
        + "\nRuntime code must not import plugins directly."
    )


def test_arm_agent_tools_no_direct_dispatch_tool_helper_import():
    """ARM agent tools must not import dispatch_tool_syscall directly."""
    source = _read("apps", "arm", "agents", "tools.py")
    assert "from apps.agent.agents.tool_helpers import dispatch_tool_syscall" not in source, (
        "apps/arm/agents/tools.py still imports dispatch_tool_syscall directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_masterplan_agent_tools_no_direct_dispatch_tool_helper_import():
    """Masterplan agent tools must not import dispatch_tool_syscall directly."""
    source = _read("apps", "masterplan", "agents", "tools.py")
    assert "from apps.agent.agents.tool_helpers import dispatch_tool_syscall" not in source, (
        "apps/masterplan/agents/tools.py still imports dispatch_tool_syscall directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_search_agent_tools_no_direct_dispatch_tool_helper_import():
    """Search agent tools must not import dispatch_tool_syscall directly."""
    source = _read("apps", "search", "agents", "tools.py")
    assert "from apps.agent.agents.tool_helpers import dispatch_tool_syscall" not in source, (
        "apps/search/agents/tools.py still imports dispatch_tool_syscall directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_tasks_agent_tools_no_direct_dispatch_tool_helper_import():
    """Task agent tools must not import dispatch_tool_syscall directly."""
    source = _read("apps", "tasks", "agents", "tools.py")
    assert "from apps.agent.agents.tool_helpers import dispatch_tool_syscall" not in source, (
        "apps/tasks/agents/tools.py still imports dispatch_tool_syscall directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_kpi_weight_service_no_loopadjustment_public_model_import():
    """KPI weight service must not import LoopAdjustment as a cross-domain model."""
    source = _read("apps", "analytics", "services", "scoring", "kpi_weight_service.py")
    assert "from apps.automation.public import LoopAdjustment" not in source, (
        "apps/analytics/services/scoring/kpi_weight_service.py still imports LoopAdjustment directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_policy_adaptation_service_no_loopadjustment_public_model_import():
    """Policy adaptation service must not import LoopAdjustment as a cross-domain model."""
    source = _read("apps", "analytics", "services", "scoring", "policy_adaptation_service.py")
    assert "from apps.automation.public import LoopAdjustment" not in source, (
        "apps/analytics/services/scoring/policy_adaptation_service.py still imports LoopAdjustment directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_dependency_adapter_no_automation_public_model_imports():
    """Dependency adapter must not import LoopAdjustment or UserFeedback model exports."""
    source = _read("apps", "analytics", "services", "integration", "dependency_adapter.py")
    assert "from apps.automation.public import LoopAdjustment" not in source, (
        "apps/analytics/services/integration/dependency_adapter.py still imports LoopAdjustment directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )
    assert "from apps.automation.public import UserFeedback" not in source, (
        "apps/analytics/services/integration/dependency_adapter.py still imports UserFeedback directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_genesis_ai_no_direct_identity_service_import():
    """Genesis AI must not import IdentityService directly."""
    source = _read("apps", "masterplan", "services", "genesis_ai.py")
    assert "from apps.identity.services.identity_service import IdentityService" not in source, (
        "apps/masterplan/services/genesis_ai.py still imports IdentityService directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_masterplan_factory_no_direct_identity_service_import():
    """Masterplan factory must not import IdentityService directly."""
    source = _read("apps", "masterplan", "services", "masterplan_factory.py")
    assert "from apps.identity.services.identity_service import IdentityService" not in source, (
        "apps/masterplan/services/masterplan_factory.py still imports IdentityService directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_dependency_adapter_no_identity_boot_service_import():
    """Dependency adapter must not import identity boot service directly."""
    source = _read("apps", "analytics", "services", "integration", "dependency_adapter.py")
    assert "from apps.identity.services.identity_boot_service" not in source, (
        "apps/analytics/services/integration/dependency_adapter.py still imports identity_boot_service directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_social_tree_no_analytics_model_imports():
    """Social domain must not import analytics ORM models directly."""
    for source_file in ROOT.joinpath("apps", "social").glob("**/*.py"):
        source = source_file.read_text(encoding="utf-8")
        assert "from apps.analytics.models" not in source, (
            f"{source_file} still imports apps.analytics.models directly. "
            "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
        )
        assert "from analytics.models" not in source, (
            f"{source_file} still imports analytics.models directly. "
            "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
        )


def test_rippletrace_tree_no_analytics_model_imports():
    """Rippletrace domain must not import analytics ORM models directly."""
    for source_file in ROOT.joinpath("apps", "rippletrace").glob("**/*.py"):
        source = source_file.read_text(encoding="utf-8")
        assert "from apps.analytics.models" not in source, (
            f"{source_file} still imports apps.analytics.models directly. "
            "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
        )
        assert "from analytics.models" not in source, (
            f"{source_file} still imports analytics.models directly. "
            "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
        )


def test_infinity_service_no_arm_model_import():
    """Infinity service must not import ARM ORM models directly."""
    source = _read("apps", "analytics", "services", "scoring", "infinity_service.py")
    assert "from apps.arm.models import AnalysisResult" not in source, (
        "apps/analytics/services/scoring/infinity_service.py still imports AnalysisResult directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_automation_flows_no_private_run_to_dict_import():
    """Automation flows must not import private _run_to_dict from agent runtime."""
    source = _read("apps", "automation", "flows", "automation_flows.py")
    assert "from AINDY.agents.agent_runtime import _run_to_dict" not in source, (
        "apps/automation/flows/automation_flows.py still imports _run_to_dict directly. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_infinity_orchestrator_no_module_level_identity_boot_service_import():
    """Infinity orchestrator must not retain module-level identity boot imports."""
    source = _read("apps", "analytics", "services", "orchestration", "infinity_orchestrator.py")
    assert "from apps.identity.services.identity_boot_service import get_recent_memory, get_user_metrics" not in source, (
        "apps/analytics/services/orchestration/infinity_orchestrator.py still imports identity boot helpers at module level. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_infinity_orchestrator_no_module_level_masterplan_goal_import():
    """Infinity orchestrator must not retain module-level goal service imports."""
    source = _read("apps", "analytics", "services", "orchestration", "infinity_orchestrator.py")
    assert "from apps.masterplan.services.goal_service import rank_goals" not in source, (
        "apps/analytics/services/orchestration/infinity_orchestrator.py still imports rank_goals at module level. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_infinity_orchestrator_no_module_level_social_import():
    """Infinity orchestrator must not retain module-level social signal imports."""
    source = _read("apps", "analytics", "services", "orchestration", "infinity_orchestrator.py")
    assert "from apps.social.services.social_performance_service import get_social_performance_signals" not in source, (
        "apps/analytics/services/orchestration/infinity_orchestrator.py still imports social signals at module level. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_infinity_orchestrator_no_module_level_task_graph_import():
    """Infinity orchestrator must not retain module-level task graph imports."""
    source = _read("apps", "analytics", "services", "orchestration", "infinity_orchestrator.py")
    assert "from apps.tasks.services.task_service import get_task_graph_context" not in source, (
        "apps/analytics/services/orchestration/infinity_orchestrator.py still imports get_task_graph_context at module level. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_infinity_loop_no_module_level_next_ready_task_import():
    """Infinity loop must not retain module-level next-task imports."""
    source = _read("apps", "analytics", "services", "orchestration", "infinity_loop.py")
    assert "from apps.tasks.services.task_service import get_next_ready_task" not in source, (
        "apps/analytics/services/orchestration/infinity_loop.py still imports get_next_ready_task at module level. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_infinity_loop_no_module_level_goal_alignment_import():
    """Infinity loop must not retain module-level goal-alignment imports."""
    source = _read("apps", "analytics", "services", "orchestration", "infinity_loop.py")
    assert "from apps.masterplan.services.goal_service import calculate_goal_alignment" not in source, (
        "apps/analytics/services/orchestration/infinity_loop.py still imports calculate_goal_alignment at module level. "
        "See docs/architecture/CROSS_DOMAIN_COUPLING.md §7 for the migration path."
    )


def test_masterplan_execution_service_no_direct_tasks_or_automation_public_imports():
    """Masterplan execution must use syscall boundaries for task and automation helpers."""
    source = _read("apps", "masterplan", "services", "masterplan_execution_service.py")
    assert "from apps.tasks.public import" not in source, (
        "apps/masterplan/services/masterplan_execution_service.py still imports apps.tasks.public directly. "
        "Masterplan execution should use owner syscalls instead."
    )
    assert "from apps.automation.public import" not in source, (
        "apps/masterplan/services/masterplan_execution_service.py still imports apps.automation.public directly. "
        "Masterplan execution should use owner syscalls instead."
    )


def test_masterplan_eta_service_no_direct_tasks_public_imports():
    """Masterplan ETA service must use task syscalls instead of tasks.public imports."""
    source = _read("apps", "masterplan", "services", "eta_service.py")
    assert "from apps.tasks.public import" not in source, (
        "apps/masterplan/services/eta_service.py still imports apps.tasks.public directly. "
        "ETA projection should use owner syscalls instead."
    )
