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
