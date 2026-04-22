from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from AINDY.platform_layer.bootstrap_graph import resolve_boot_order


APPS_ROOT = Path("apps")
APP_NAMES = sorted(
    path.name
    for path in APPS_ROOT.iterdir()
    if path.is_dir() and not path.name.startswith("__")
)


def _bootstrap_metadata() -> dict[str, dict[str, list[str]]]:
    metadata: dict[str, dict[str, list[str]]] = {}
    for app in APP_NAMES:
        bootstrap_path = APPS_ROOT / app / "bootstrap.py"
        assert bootstrap_path.exists(), f"Missing bootstrap.py for app '{app}'"
        tree = ast.parse(bootstrap_path.read_text(encoding="utf-8", errors="ignore"))
        values = {"BOOTSTRAP_DEPENDS_ON": None, "APP_DEPENDS_ON": None}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    name = getattr(target, "id", None)
                    if name in values:
                        values[name] = ast.literal_eval(node.value)
            elif isinstance(node, ast.AnnAssign):
                name = getattr(node.target, "id", None)
                if name in values:
                    values[name] = ast.literal_eval(node.value)
        for field, value in values.items():
            assert value is not None, f"{bootstrap_path} must declare {field}"
        metadata[app] = {
            "BOOTSTRAP_DEPENDS_ON": list(values["BOOTSTRAP_DEPENDS_ON"] or []),
            "APP_DEPENDS_ON": list(values["APP_DEPENDS_ON"] or []),
        }
    return metadata


def _actual_cross_app_imports() -> dict[str, set[str]]:
    edges: dict[str, set[str]] = {app: set() for app in APP_NAMES}
    for app in APP_NAMES:
        for path in (APPS_ROOT / app).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    parts = node.module.split(".")
                    if len(parts) >= 2 and parts[0] == "apps" and parts[1] in APP_NAMES and parts[1] != app:
                        edges[app].add(parts[1])
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        parts = alias.name.split(".")
                        if len(parts) >= 2 and parts[0] == "apps" and parts[1] in APP_NAMES and parts[1] != app:
                            edges[app].add(parts[1])
    return edges


def test_app_dependency_metadata_matches_direct_cross_app_imports():
    metadata = _bootstrap_metadata()
    actual = _actual_cross_app_imports()

    mismatches: list[str] = []
    for app in APP_NAMES:
        declared = set(metadata[app]["APP_DEPENDS_ON"])
        missing = sorted(actual[app] - declared)
        extra = sorted(declared - actual[app])
        if missing or extra:
            mismatches.append(
                f"{app}: missing={missing or '-'} extra={extra or '-'}"
            )

    assert not mismatches, "APP_DEPENDS_ON drift detected:\n" + "\n".join(mismatches)


def test_declared_dependencies_reference_existing_apps():
    metadata = _bootstrap_metadata()
    failures: list[str] = []
    app_set = set(APP_NAMES)

    for app, declared in metadata.items():
        for field, dependencies in declared.items():
            invalid = sorted(set(dependencies) - app_set)
            if invalid:
                failures.append(f"{app}.{field}: {invalid}")

    assert not failures, "Invalid app dependency references:\n" + "\n".join(failures)


def test_bootstrap_dependency_graph_is_acyclic():
    metadata = _bootstrap_metadata()
    app_bootstraps = {
        app: SimpleNamespace(BOOTSTRAP_DEPENDS_ON=declared["BOOTSTRAP_DEPENDS_ON"])
        for app, declared in metadata.items()
    }

    ordered = resolve_boot_order(app_bootstraps)
    assert sorted(ordered) == APP_NAMES
