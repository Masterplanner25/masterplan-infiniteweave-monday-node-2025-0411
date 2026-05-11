from __future__ import annotations

import pytest

from tests.helpers.app_profile import bootstrap_app_models
from tests.helpers.runtime import import_runtime_model_registry


pytestmark = pytest.mark.app_profile


def test_app_bootstrap_extends_runtime_metadata_with_app_models():
    import_runtime_model_registry()
    bootstrap_app_models(required=True)

    from AINDY.db.database import Base

    assert "users" in Base.metadata.tables
    assert "agent_runs" in Base.metadata.tables
    assert "tasks" in Base.metadata.tables
    assert "master_plans" in Base.metadata.tables
