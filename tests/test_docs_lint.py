from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "lint_docs.py"
SPEC = importlib.util.spec_from_file_location("lint_docs", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
lint_docs = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = lint_docs
SPEC.loader.exec_module(lint_docs)


def write_doc(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "sample.md"
    path.write_text(body, encoding="utf-8")
    return path


def valid_frontmatter(last_verified: str = "2026-04-20", status: str = "current") -> str:
    return (
        "---\n"
        'title: "Sample"\n'
        f'last_verified: "{last_verified}"\n'
        'api_version: "1.0"\n'
        f"status: {status}\n"
        'owner: "platform-team"\n'
        "---\n"
        "# Sample\n"
    )


def test_lint_passes_on_valid_frontmatter(tmp_path: Path) -> None:
    path = write_doc(tmp_path, valid_frontmatter())
    result = lint_docs.lint_file(path, today=dt.date(2026, 4, 25))
    assert result.errors == []
    assert result.warnings == []


def test_lint_fails_on_missing_frontmatter(tmp_path: Path) -> None:
    path = write_doc(tmp_path, "# Sample\n")
    result = lint_docs.lint_file(path)
    assert "MISSING_FRONTMATTER" in result.errors


def test_lint_fails_on_missing_field(tmp_path: Path) -> None:
    path = write_doc(
        tmp_path,
        "---\n"
        'title: "Sample"\n'
        'api_version: "1.0"\n'
        "status: current\n"
        'owner: "platform-team"\n'
        "---\n",
    )
    result = lint_docs.lint_file(path)
    assert "MISSING_FIELD (last_verified)" in result.errors


def test_lint_fails_on_invalid_date_format(tmp_path: Path) -> None:
    path = write_doc(
        tmp_path,
        valid_frontmatter(last_verified="April 25 2026"),
    )
    result = lint_docs.lint_file(path)
    assert "INVALID_DATE" in result.errors


def test_lint_fails_on_invalid_status(tmp_path: Path) -> None:
    path = write_doc(tmp_path, valid_frontmatter(status="unknown"))
    result = lint_docs.lint_file(path)
    assert "INVALID_STATUS" in result.errors


def test_lint_warns_on_stale_doc(tmp_path: Path) -> None:
    path = write_doc(tmp_path, valid_frontmatter(last_verified="2026-01-01", status="current"))
    result = lint_docs.lint_file(path, today=dt.date(2026, 4, 25), stale_after_days=90)
    assert result.errors == []
    assert any(warning.startswith("STALE") for warning in result.warnings)


def test_lint_no_stale_warning_when_status_outdated(tmp_path: Path) -> None:
    path = write_doc(tmp_path, valid_frontmatter(last_verified="2026-01-01", status="outdated"))
    result = lint_docs.lint_file(path, today=dt.date(2026, 4, 25), stale_after_days=90)
    assert result.errors == []
    assert result.warnings == []


def test_all_required_docs_pass_lint() -> None:
    results = lint_docs.lint_paths(
        lint_docs.REQUIRED_DIRECTORIES,
        today=dt.date.today(),
        stale_after_days=90,
    )
    assert all(not result.errors for result in results), [
        (result.path, result.errors) for result in results if result.errors
    ]
