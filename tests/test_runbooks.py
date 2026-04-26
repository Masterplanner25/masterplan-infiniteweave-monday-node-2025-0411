from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS_OPS = ROOT / "docs" / "ops"
RUNBOOK_FILES = [
    DOCS_OPS / "RUNBOOK_REDIS_FAILURE.md",
    DOCS_OPS / "RUNBOOK_STUCK_RUNS.md",
    DOCS_OPS / "RUNBOOK_LEADER_FAILOVER.md",
    DOCS_OPS / "RUNBOOK_WAIT_FLOW_DEADLETTER.md",
]


def _load_lint_docs_module():
    module_path = ROOT / "scripts" / "lint_docs.py"
    spec = importlib.util.spec_from_file_location("lint_docs", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _route_source_text() -> str:
    parts: list[str] = []
    for base in (ROOT / "AINDY" / "routes", ROOT / "apps"):
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "/routes/" in path.as_posix() or path.parent.name == "routes":
                parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _extract_runbook_paths(text: str) -> set[str]:
    paths = set(re.findall(r"(/(?:platform|apps)/[A-Za-z0-9_./?={}-]+)", text))
    return {
        path
        for path in paths
        if not path.endswith((".py", ".md"))
    }


def _extract_env_vars(text: str) -> set[str]:
    return set(re.findall(r"\$([A-Z][A-Z0-9_]+)", text))


def _path_exists_in_routes(path: str) -> bool:
    route_files: list[Path] = []
    for base in (ROOT / "AINDY" / "routes", ROOT / "apps"):
        if not base.exists():
            continue
        for candidate in base.rglob("*.py"):
            if "/routes/" in candidate.as_posix() or candidate.parent.name == "routes":
                route_files.append(candidate)

    stripped = path.split("?", 1)[0]
    for prefix_to_strip in ("/platform", "/apps"):
        if stripped.startswith(prefix_to_strip + "/"):
            stripped = stripped[len(prefix_to_strip):]
            break

    if not stripped.startswith("/"):
        stripped = "/" + stripped

    for route_file in route_files:
        text = route_file.read_text(encoding="utf-8")
        if stripped in text:
            return True
        parts = [part for part in stripped.split("/") if part]
        if len(parts) >= 2:
            router_prefix = "/" + parts[0]
            route_suffix = "/" + "/".join(parts[1:])
            if router_prefix in text and route_suffix in text:
                return True
    return False


def test_all_runbooks_exist() -> None:
    for path in RUNBOOK_FILES:
        assert path.exists(), path


def test_all_runbooks_pass_frontmatter_lint() -> None:
    lint_docs = _load_lint_docs_module()
    results = lint_docs.lint_paths([DOCS_OPS])
    assert all(not result.errors for result in results), [
        (result.path, result.errors) for result in results if result.errors
    ]


def test_all_runbooks_reference_real_endpoints() -> None:
    for runbook in RUNBOOK_FILES:
        paths = _extract_runbook_paths(runbook.read_text(encoding="utf-8"))
        for path in paths:
            assert _path_exists_in_routes(path), (runbook.name, path)


def test_all_runbooks_reference_real_env_vars() -> None:
    config_text = (ROOT / "AINDY" / "config.py").read_text(encoding="utf-8")
    config_vars = set(re.findall(r"^\s+([A-Z][A-Z0-9_]+):", config_text, flags=re.MULTILINE))
    readme_vars = _extract_env_vars((DOCS_OPS / "README.md").read_text(encoding="utf-8"))
    allowed = config_vars | readme_vars
    for runbook in RUNBOOK_FILES:
        vars_in_doc = _extract_env_vars(runbook.read_text(encoding="utf-8"))
        assert vars_in_doc <= allowed, (runbook.name, sorted(vars_in_doc - allowed))


def test_runbook_index_references_all_runbooks() -> None:
    readme = (DOCS_OPS / "README.md").read_text(encoding="utf-8")
    for path in RUNBOOK_FILES:
        assert f"({path.name})" in readme
