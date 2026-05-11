from __future__ import annotations

import pytest

from tests.fixtures import client as client_fixtures


pytestmark = pytest.mark.runtime_only


def test_runtime_only_fresh_app_does_not_touch_app_bootstrap(monkeypatch):
    app = client_fixtures._fresh_main_app(runtime_only=True, require_apps=False)

    assert app is not None


def test_runtime_only_fixture_rejects_app_profile_boot_requests():
    with pytest.raises(RuntimeError, match="runtime-only boot"):
        client_fixtures._fresh_main_app(runtime_only=False, require_apps=True)


def test_runtime_only_client_fixture_uses_runtime_boot_profile(runtime_only_client):
    response = runtime_only_client.get("/health")

    assert response.status_code == 200
