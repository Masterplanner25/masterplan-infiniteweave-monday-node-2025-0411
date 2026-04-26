from __future__ import annotations

import pathlib


def test_genesis_ai_has_no_direct_identity_service_import():
    source = pathlib.Path(
        "apps/masterplan/services/genesis_ai.py"
    ).read_text(encoding="utf-8")
    assert "from apps.identity.services.identity_service import IdentityService" not in source


def test_masterplan_factory_has_no_direct_identity_service_import():
    source = pathlib.Path(
        "apps/masterplan/services/masterplan_factory.py"
    ).read_text(encoding="utf-8")
    assert "from apps.identity.services.identity_service import IdentityService" not in source


def test_dependency_adapter_has_no_direct_identity_boot_service_import():
    source = pathlib.Path(
        "apps/analytics/services/integration/dependency_adapter.py"
    ).read_text(encoding="utf-8")
    assert "from apps.identity.services.identity_boot_service" not in source
