from __future__ import annotations

import pathlib
import subprocess
import sys


def test_analytics_has_no_loop_adjustment_public_orm_import():
    for path in pathlib.Path("apps/analytics").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "from apps.automation.public import LoopAdjustment" not in source


def test_analytics_has_no_user_feedback_public_orm_import():
    for path in pathlib.Path("apps/analytics").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "from apps.automation.public import UserFeedback" not in source


def test_analytics_scoring_modules_import_without_circular_import():
    command = [
        sys.executable,
        "-c",
        (
            "import sys; "
            "sys.path.insert(0, '.'); "
            "import apps.analytics.services.integration.dependency_adapter; "
            "import apps.analytics.services.scoring.kpi_weight_service; "
            "import apps.analytics.services.scoring.policy_adaptation_service; "
            "print('No circular import')"
        ),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)

    assert "No circular import" in result.stdout
