from __future__ import annotations


def test_requires_redis_dev_does_not_require(monkeypatch):
    from AINDY.config import settings

    monkeypatch.setattr(settings, "ENV", "dev")
    monkeypatch.setattr(settings, "AINDY_REQUIRE_REDIS", False)
    assert settings.requires_redis is False


def test_requires_redis_staging_requires(monkeypatch):
    from AINDY.config import settings

    monkeypatch.setattr(settings, "ENV", "staging")
    monkeypatch.setattr(settings, "AINDY_REQUIRE_REDIS", False)
    assert settings.requires_redis is True


def test_requires_redis_explicit_flag_overrides(monkeypatch):
    from AINDY.config import settings

    monkeypatch.setattr(settings, "ENV", "dev")
    monkeypatch.setattr(settings, "AINDY_REQUIRE_REDIS", True)
    assert settings.requires_redis is True
