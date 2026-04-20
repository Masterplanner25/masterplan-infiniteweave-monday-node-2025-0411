from __future__ import annotations

import pytest


def test_redis_guard_raises_in_prod_without_redis_url(monkeypatch):
    from AINDY import main

    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(main.settings, "TESTING", False)
    monkeypatch.setattr(main.settings, "TEST_MODE", False)
    monkeypatch.setattr(main.settings, "REDIS_URL", None)
    monkeypatch.setattr(main.settings, "AINDY_REQUIRE_REDIS", False)

    with pytest.raises(RuntimeError, match="REDIS_URL is required"):
        main._enforce_redis_startup_guard()


def test_redis_guard_skipped_in_test_mode(monkeypatch):
    from AINDY import main

    monkeypatch.setattr(main.settings, "ENV", "test")
    monkeypatch.setattr(main.settings, "TESTING", True)
    monkeypatch.setattr(main.settings, "TEST_MODE", True)
    monkeypatch.setattr(main.settings, "REDIS_URL", None)
    monkeypatch.setattr(main.settings, "AINDY_REQUIRE_REDIS", True)

    main._enforce_redis_startup_guard()


def test_health_returns_redis_status(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert "dependencies" in response.json()
    assert "redis" not in response.json()["dependencies"] or "status" in response.json()["dependencies"]["redis"]
