from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from apps._bootstrap_validator import (
    BootstrapDependencyError,
    compute_boot_order,
    extract_actual_top_level_imports,
    find_circular_dependencies,
    validate_bootstrap_deps,
)


def _write_bootstrap(tmp_path: Path, app_name: str, body: str) -> None:
    app_dir = tmp_path / "apps" / app_name
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "bootstrap.py").write_text(body, encoding="utf-8")


def test_no_undeclared_deps_in_current_codebase() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    validate_bootstrap_deps(str(repo_root / "apps"))


def test_undeclared_dep_raises_bootstrap_error(tmp_path: Path) -> None:
    _write_bootstrap(
        tmp_path,
        "tasks",
        'APP_DEPENDS_ON = []\nfrom apps.analytics import public\n',
    )
    _write_bootstrap(tmp_path, "analytics", "APP_DEPENDS_ON = []\n")

    with pytest.raises(BootstrapDependencyError, match="analytics"):
        validate_bootstrap_deps(str(tmp_path / "apps"))


def test_circular_dependency_detected() -> None:
    cycles = find_circular_dependencies({"A": ["B"], "B": ["A"]})
    assert ["A", "B", "A"] in cycles or ["B", "A", "B"] in cycles


def test_no_false_positives_on_intra_app_imports(tmp_path: Path) -> None:
    _write_bootstrap(
        tmp_path,
        "tasks",
        'APP_DEPENDS_ON = []\nfrom apps.tasks import public\n',
    )
    actual = extract_actual_top_level_imports(str(tmp_path / "apps"))

    assert actual["tasks"] == []


def test_topological_sort_respects_deps() -> None:
    order = compute_boot_order({"C": ["A", "B"], "B": ["A"], "A": []})

    assert order.index("A") < order.index("B") < order.index("C")


def test_topological_sort_raises_on_cycle() -> None:
    with pytest.raises(BootstrapDependencyError, match="Circular dependencies detected"):
        compute_boot_order({"A": ["B"], "B": ["A"]})


def test_startup_fails_if_undeclared_dep_introduced(monkeypatch: pytest.MonkeyPatch) -> None:
    import apps._bootstrap_validator as validator
    import AINDY.startup as startup

    original = validator.validate_bootstrap_deps

    def _raise(_bootstrap_dir: str) -> None:
        raise BootstrapDependencyError("forced undeclared dependency")

    monkeypatch.setattr(validator, "validate_bootstrap_deps", _raise)
    try:
        with pytest.raises(RuntimeError, match="forced undeclared dependency"):
            importlib.reload(startup)
    finally:
        monkeypatch.setattr(validator, "validate_bootstrap_deps", original)
        importlib.reload(startup)
