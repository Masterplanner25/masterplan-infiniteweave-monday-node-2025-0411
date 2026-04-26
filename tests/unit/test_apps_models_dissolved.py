from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_apps_models_file_does_not_exist():
    assert not (REPO_ROOT / "apps" / "models.py").exists()


def test_category_a_b_models_importable_from_owner_app():
    imports = [
        ("apps.analytics.models", "AIEfficiency"),
        ("apps.analytics.models", "AIProductivityBoost"),
        ("apps.analytics.models", "AttentionValue"),
        ("apps.analytics.models", "BusinessGrowth"),
        ("apps.analytics.models", "CalculationResult"),
        ("apps.analytics.models", "CanonicalMetricDB"),
        ("apps.analytics.models", "DecisionEfficiency"),
        ("apps.analytics.models", "Efficiency"),
        ("apps.analytics.models", "Engagement"),
        ("apps.analytics.models", "EngagementRate"),
        ("apps.analytics.models", "ExecutionSpeed"),
        ("apps.analytics.models", "Impact"),
        ("apps.analytics.models", "LostPotential"),
        ("apps.analytics.models", "MonetizationEfficiency"),
        ("apps.analytics.models", "RevenueScaling"),
        ("apps.analytics.models", "ScoreHistory"),
        ("apps.analytics.models", "ScoreSnapshotDB"),
        ("apps.analytics.models", "UserScore"),
        ("apps.arm.models", "ARMConfig"),
        ("apps.arm.models", "ARMLog"),
        ("apps.arm.models", "ARMRun"),
        ("apps.arm.models", "AnalysisResult"),
        ("apps.arm.models", "ArmConfig"),
        ("apps.arm.models", "CodeGeneration"),
        ("apps.authorship.models", "AuthorDB"),
        ("apps.automation.public", "AutomationLog"),
        ("apps.automation.public", "BridgeUserEvent"),
        ("apps.automation.public", "LearningRecordDB"),
        ("apps.automation.public", "LearningThresholdDB"),
        ("apps.automation.public", "LoopAdjustment"),
        ("apps.automation.public", "UserFeedback"),
        ("apps.freelance.models", "ClientFeedback"),
        ("apps.freelance.models", "FreelanceOrder"),
        ("apps.freelance.models", "RevenueMetrics"),
        ("apps.masterplan.public", "GenesisSessionDB"),
        ("apps.masterplan.public", "Goal"),
        ("apps.masterplan.public", "GoalState"),
        ("apps.masterplan.public", "MasterPlan"),
        ("apps.rippletrace.public", "DropPointDB"),
        ("apps.rippletrace.public", "PingDB"),
        ("apps.rippletrace.public", "PlaybookDB"),
        ("apps.rippletrace.public", "RippleEdge"),
        ("apps.rippletrace.public", "StrategyDB"),
        ("apps.search.public", "LeadGenResult"),
        ("apps.search.public", "ResearchResult"),
        ("apps.search.public", "SearchHistory"),
        ("apps.tasks.public", "Task"),
    ]

    for module_name, symbol_name in imports:
        module = importlib.import_module(module_name)
        assert getattr(module, symbol_name) is not None


def test_no_cross_app_models_import_in_codebase():
    forbidden_patterns = (
        "from " + "apps" + ".models import",
        "import " + "apps" + ".models",
        "from " + "apps" + " import models",
    )
    result = subprocess.run(
        [sys.executable, "scripts/check_app_imports.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    combined_output = f"{result.stdout}\n{result.stderr}"
    assert "apps.models" not in combined_output
    for path in REPO_ROOT.rglob("*.py"):
        if (
            ".venv" in path.parts
            or "__pycache__" in path.parts
            or path == Path(__file__)
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in forbidden_patterns:
            assert pattern not in text
