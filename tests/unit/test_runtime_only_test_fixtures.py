from __future__ import annotations

import pytest

from tests.fixtures import client as client_fixtures


pytestmark = pytest.mark.runtime_only


def test_runtime_only_fresh_app_does_not_touch_app_bootstrap(monkeypatch):
    monkeypatch.setattr(
        client_fixtures,
        "reset_app_bootstrap_state",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("app bootstrap should not be reset")),
    )

    app = client_fixtures._fresh_main_app(runtime_only=True, require_apps=False)

    assert app is not None


def test_runtime_only_client_fixture_uses_runtime_boot_profile(runtime_only_client):
    response = runtime_only_client.get("/health")

    assert response.status_code == 200
