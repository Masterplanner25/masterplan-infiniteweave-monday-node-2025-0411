from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
APPS_ROOT = ROOT / "apps"
CONTRACT_DOC = ROOT / "docs" / "runtime" / "PUBLIC_API_CONTRACT.md"

PUBLIC_HEADER = "## Public Runtime API Modules"
TRANSITIONAL_HEADER = "## Transitional App Imports To Remove Or Replace"


def _parse_module_section(header: str) -> list[str]:
    lines = CONTRACT_DOC.read_text(encoding="utf-8").splitlines()
    in_section = False
    modules: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if in_section:
                break
            in_section = line.strip() == header
            continue
        if in_section and line.startswith("- `") and line.endswith("`"):
            modules.append(line[3:-1])

    if not modules:
        raise AssertionError(f"No modules found under {header!r} in {CONTRACT_DOC.relative_to(ROOT)}")
    return modules


def _iter_app_aindy_imports() -> list[tuple[str, str]]:
    imports: set[tuple[str, str]] = set()
    for path in APPS_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("AINDY"):
                imports.add((rel, node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("AINDY"):
                        imports.add((rel, alias.name))
    return sorted(imports)


def _matches(module: str, allowed: str) -> bool:
    if allowed.endswith(".*"):
        prefix = allowed[:-2]
        return module == prefix or module.startswith(prefix + ".")
    return module == allowed


@pytest.mark.runtime_only
def test_runtime_public_api_contract_has_disjoint_sorted_lists():
    public_modules = _parse_module_section(PUBLIC_HEADER)
    transitional_modules = _parse_module_section(TRANSITIONAL_HEADER)

    assert public_modules == sorted(public_modules), "Public runtime API list must stay sorted."
    assert transitional_modules == sorted(transitional_modules), (
        "Transitional runtime import list must stay sorted."
    )
    overlap = sorted(set(public_modules) & set(transitional_modules))
    assert overlap == [], f"Public and transitional runtime module lists overlap: {overlap}"


@pytest.mark.app_profile
def test_apps_only_import_public_or_documented_transitional_runtime_modules():
    public_modules = _parse_module_section(PUBLIC_HEADER)
    transitional_modules = _parse_module_section(TRANSITIONAL_HEADER)

    unexpected: list[str] = []
    seen_transitional: set[str] = set()

    for rel, module in _iter_app_aindy_imports():
        if any(_matches(module, allowed) for allowed in public_modules):
            continue
        if any(_matches(module, allowed) for allowed in transitional_modules):
            seen_transitional.add(module)
            continue
        unexpected.append(f"{rel}: {module}")

    stale_transitional = [
        module
        for module in transitional_modules
        if not any(_matches(imported_module, module) for _rel, imported_module in _iter_app_aindy_imports())
    ]

    assert not unexpected, (
        "Found app imports from undocumented internal runtime modules:\n- "
        + "\n- ".join(unexpected)
        + f"\nUpdate {CONTRACT_DOC.relative_to(ROOT)} to promote or explicitly classify them."
    )
    assert not stale_transitional, (
        "Transitional runtime import list contains stale entries that apps no longer import:\n- "
        + "\n- ".join(stale_transitional)
    )
