from __future__ import annotations

from types import SimpleNamespace

import pytest

from AINDY.platform_layer.bootstrap_graph import resolve_boot_order


def _module(*depends_on: str) -> SimpleNamespace:
    return SimpleNamespace(BOOTSTRAP_DEPENDS_ON=list(depends_on))


def test_resolve_boot_order_linear_dependencies():
    app_bootstraps = {
        "a": _module("b"),
        "b": _module("c"),
        "c": _module(),
    }

    assert resolve_boot_order(app_bootstraps) == ["c", "b", "a"]


def test_resolve_boot_order_diamond_dependencies():
    app_bootstraps = {
        "a": _module("b", "c"),
        "b": _module("d"),
        "c": _module("d"),
        "d": _module(),
    }

    order = resolve_boot_order(app_bootstraps)

    assert order[0] == "d"
    assert order[-1] == "a"
    assert set(order[1:3]) == {"b", "c"}


def test_resolve_boot_order_no_dependencies_includes_every_app():
    app_bootstraps = {
        "alpha": _module(),
        "beta": _module(),
        "gamma": _module(),
    }

    order = resolve_boot_order(app_bootstraps)

    assert set(order) == {"alpha", "beta", "gamma"}
    assert len(order) == 3


def test_resolve_boot_order_detects_cycles():
    app_bootstraps = {
        "analytics": _module("masterplan"),
        "masterplan": _module("analytics"),
    }

    with pytest.raises(RuntimeError, match="Bootstrap dependency cycle detected: analytics → masterplan → analytics"):
        resolve_boot_order(app_bootstraps)


def test_resolve_boot_order_detects_missing_dependency():
    app_bootstraps = {
        "analytics": _module("nonexistent"),
    }

    with pytest.raises(
        RuntimeError,
        match="App 'analytics' declares dependency on 'nonexistent' but no such app is registered.",
    ):
        resolve_boot_order(app_bootstraps)


def test_resolve_boot_order_empty_input():
    assert resolve_boot_order({}) == []


def test_app_depends_on_ordering_check_emits_warning(monkeypatch):
    """
    _check_app_depends_on_ordering() must return a warning when an
    APP_DEPENDS_ON edge points to an app that boots later.
    """
    import apps.bootstrap as bs

    fake_metadata = {
        "alpha": SimpleNamespace(
            BOOTSTRAP_DEPENDS_ON=[],
            APP_DEPENDS_ON=["beta"],
        ),
        "beta": SimpleNamespace(
            BOOTSTRAP_DEPENDS_ON=[],
            APP_DEPENDS_ON=[],
        ),
    }
    monkeypatch.setattr(bs, "get_resolved_boot_order", lambda: ["alpha", "beta"])
    monkeypatch.setattr(bs, "_load_bootstrap_metadata", lambda: fake_metadata)

    warnings = bs._check_app_depends_on_ordering()
    assert len(warnings) == 1
    assert "alpha" in warnings[0]
    assert "beta" in warnings[0]
    assert "BOOTSTRAP_DEPENDS_ON" in warnings[0]


def test_app_depends_on_ordering_no_warning_when_correct(monkeypatch):
    """
    _check_app_depends_on_ordering() must return no warnings when all
    APP_DEPENDS_ON dependencies boot before or at the same position.
    """
    import apps.bootstrap as bs

    fake_metadata = {
        "alpha": SimpleNamespace(
            BOOTSTRAP_DEPENDS_ON=["beta"],
            APP_DEPENDS_ON=["beta"],
        ),
        "beta": SimpleNamespace(
            BOOTSTRAP_DEPENDS_ON=[],
            APP_DEPENDS_ON=[],
        ),
    }
    monkeypatch.setattr(bs, "get_resolved_boot_order", lambda: ["beta", "alpha"])
    monkeypatch.setattr(bs, "_load_bootstrap_metadata", lambda: fake_metadata)

    warnings = bs._check_app_depends_on_ordering()
    assert warnings == []
