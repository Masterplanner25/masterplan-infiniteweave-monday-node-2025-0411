from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest


def test_memory_cache_raises_in_production(monkeypatch):
    """Memory cache is rejected when requires_redis is True and ENV=production."""
    import AINDY.main as main_module

    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            is_prod=True,
            is_testing=False,
            requires_redis=True,
            AINDY_CACHE_BACKEND="memory",
            ENV="production",
            AINDY_REQUIRE_REDIS=True,
            REDIS_URL="redis://example",
        ),
    )

    with pytest.raises(RuntimeError, match="AINDY_CACHE_BACKEND=memory is not permitted"):
        main_module._enforce_cache_backend_coherence()


def test_memory_cache_warns_in_dev(monkeypatch, caplog):
    """Memory cache logs a warning (does not raise) in dev mode."""
    import AINDY.main as main_module

    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            is_prod=False,
            is_testing=False,
            requires_redis=True,
            AINDY_CACHE_BACKEND="memory",
            ENV="development",
            AINDY_REQUIRE_REDIS=True,
            REDIS_URL="redis://example",
        ),
    )

    with caplog.at_level(logging.WARNING, logger="AINDY.main"):
        main_module._enforce_cache_backend_coherence()

    assert any("not permitted" in record.message for record in caplog.records)


def test_off_backend_passes_coherence_check(monkeypatch):
    """AINDY_CACHE_BACKEND=off is always acceptable."""
    import AINDY.main as main_module

    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            is_prod=True,
            is_testing=False,
            requires_redis=True,
            AINDY_CACHE_BACKEND="off",
            ENV="production",
            AINDY_REQUIRE_REDIS=True,
            REDIS_URL="redis://example",
        ),
    )

    main_module._enforce_cache_backend_coherence()


def test_redis_backend_without_url_warns_in_dev(monkeypatch, caplog):
    """AINDY_CACHE_BACKEND=redis without REDIS_URL warns but does not raise."""
    import AINDY.main as main_module

    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(
            is_prod=False,
            is_testing=False,
            requires_redis=True,
            AINDY_CACHE_BACKEND="redis",
            ENV="development",
            AINDY_REQUIRE_REDIS=False,
            REDIS_URL=None,
        ),
    )

    with caplog.at_level(logging.WARNING, logger="AINDY.main"):
        main_module._enforce_cache_backend_coherence()

    assert any("REDIS_URL is not set" in record.message for record in caplog.records)
