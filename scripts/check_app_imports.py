#!/usr/bin/env python3
"""Check declared cross-app import boundaries under apps/."""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
APPS_ROOT = REPO_ROOT / "apps"
BOOTSTRAP_ROOT = APPS_ROOT / "bootstrap.py"
SHARED_MODELS_MODULE = "apps.models"


@dataclass(frozen=True)
class ImportFinding:
    importer_app: str
    imported_app: str
    source_file: Path
    line_number: int
    import_text: str
    declared: bool
    note: str = ""


def _literal_list(node: ast.AST) -> list[str]:
    value = ast.literal_eval(node)
    if not isinstance(value, list):
        raise ValueError(f"Expected list literal, got {type(value).__name__}")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("Expected list[str] literal")
    return list(value)


def discover_apps() -> list[str]:
    apps: list[str] = []
    for path in sorted(APPS_ROOT.iterdir()):
        if path.is_dir() and (path / "bootstrap.py").exists():
            apps.append(path.name)
    return apps


def load_declared_dependencies(app_names: list[str]) -> dict[str, set[str]]:
    declared: dict[str, set[str]] = {}
    for app_name in app_names:
        bootstrap_path = APPS_ROOT / app_name / "bootstrap.py"
        tree = ast.parse(bootstrap_path.read_text(encoding="utf-8"), filename=str(bootstrap_path))
        depends_on: list[str] | None = None
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "APP_DEPENDS_ON":
                        depends_on = _literal_list(node.value)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "APP_DEPENDS_ON":
                    depends_on = _literal_list(node.value)
        if depends_on is None:
            raise RuntimeError(f"{bootstrap_path} must declare APP_DEPENDS_ON")
        declared[app_name] = set(depends_on)
    return declared


def _target_from_module_name(module_name: str, app_names: set[str]) -> tuple[str | None, str]:
    if module_name == SHARED_MODELS_MODULE or module_name.startswith(f"{SHARED_MODELS_MODULE}."):
        return "__shared_models__", "shared model aggregator — needs owner"

    if not module_name.startswith("apps."):
        return None, ""

    parts = module_name.split(".")
    if len(parts) < 2:
        return None, ""

    target = parts[1]
    if target == "models":
        return "__shared_models__", "shared model aggregator — needs owner"
    if target in app_names:
        return target, ""
    return None, ""


def scan_file(path: Path, app_names: set[str], declared_dependencies: dict[str, set[str]]) -> list[ImportFinding]:
    relative_path = path.relative_to(APPS_ROOT)
    if len(relative_path.parts) < 2:
        return []

    importer_app = relative_path.parts[0]
    if importer_app not in app_names:
        return []

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    findings: list[ImportFinding] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue

        if isinstance(node, ast.Import):
            import_text = ast.get_source_segment(source, node) or "import ..."
            targets: list[tuple[str, str]] = []
            for alias in node.names:
                target_app, note = _target_from_module_name(alias.name, app_names)
                if target_app is not None:
                    targets.append((target_app, note))
        else:
            if node.level != 0:
                continue
            import_text = ast.get_source_segment(source, node) or "from ... import ..."
            targets = []
            if node.module == "apps":
                for alias in node.names:
                    target_name = alias.name.split(".")[0]
                    if target_name == "models":
                        targets.append(("__shared_models__", "shared model aggregator — needs owner"))
                    elif target_name in app_names:
                        targets.append((target_name, ""))
            elif node.module:
                target_app, note = _target_from_module_name(node.module, app_names)
                if target_app is not None:
                    targets.append((target_app, note))

        for target_app, note in targets:
            if target_app == importer_app:
                continue

            declared = target_app != "__shared_models__" and target_app in declared_dependencies[importer_app]
            findings.append(
                ImportFinding(
                    importer_app=importer_app,
                    imported_app=target_app,
                    source_file=path.relative_to(REPO_ROOT),
                    line_number=node.lineno,
                    import_text=" ".join(import_text.strip().split()),
                    declared=declared,
                    note=note,
                )
            )

    return findings


def format_table(findings: list[ImportFinding]) -> str:
    headers = ["Importer", "Imported", "Declared", "File", "Line", "Import", "Notes"]
    rows: list[list[str]] = []
    for finding in findings:
        imported = "apps.models" if finding.imported_app == "__shared_models__" else finding.imported_app
        rows.append(
            [
                finding.importer_app,
                imported,
                "yes" if finding.declared else "NO",
                finding.source_file.as_posix(),
                str(finding.line_number),
                finding.import_text,
                finding.note,
            ]
        )

    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def render_row(values: list[str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    separator = "-+-".join("-" * width for width in widths)
    lines = [render_row(headers), separator]
    lines.extend(render_row(row) for row in rows)
    return "\n".join(lines)


def build_dependency_matrix(findings: list[ImportFinding]) -> dict[str, list[str]]:
    matrix: dict[str, set[str]] = defaultdict(set)
    for finding in findings:
        target = "apps.models" if finding.imported_app == "__shared_models__" else finding.imported_app
        matrix[finding.importer_app].add(target)
    return {app: sorted(targets) for app, targets in sorted(matrix.items())}


def main() -> int:
    if not APPS_ROOT.exists():
        print(f"Missing apps/ directory at {APPS_ROOT}", file=sys.stderr)
        return 2
    if not BOOTSTRAP_ROOT.exists():
        print(f"Missing bootstrap aggregator at {BOOTSTRAP_ROOT}", file=sys.stderr)
        return 2

    app_names = discover_apps()
    app_name_set = set(app_names)
    declared_dependencies = load_declared_dependencies(app_names)

    findings: list[ImportFinding] = []
    parse_errors: list[str] = []
    for path in sorted(APPS_ROOT.rglob("*.py")):
        try:
            findings.extend(scan_file(path, app_name_set, declared_dependencies))
        except SyntaxError as exc:
            parse_errors.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {exc}")

    if parse_errors:
        print("Unable to parse Python files during import scan:", file=sys.stderr)
        for error in parse_errors:
            print(f"  {error}", file=sys.stderr)
        return 2

    findings.sort(
        key=lambda item: (
            not item.declared,
            item.importer_app,
            item.source_file.as_posix(),
            item.line_number,
            item.import_text,
        )
    )

    declared_count = sum(1 for finding in findings if finding.declared)
    undeclared_count = len(findings) - declared_count

    print("Cross-app import boundary report")
    print(f"Scanned apps: {', '.join(app_names)}")
    print()
    if findings:
        print(format_table(findings))
    else:
        print("No cross-app imports found.")

    print()
    print("Dependency matrix")
    matrix = build_dependency_matrix(findings)
    if matrix:
        for importer_app, imported_apps in matrix.items():
            print(f"  {importer_app}: {', '.join(imported_apps)}")
    else:
        print("  (none)")

    print()
    print(f"{declared_count} declared, {undeclared_count} undeclared cross-app imports found.")
    return 1 if undeclared_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
