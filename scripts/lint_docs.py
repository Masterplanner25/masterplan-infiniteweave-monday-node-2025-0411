from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None


REQUIRED_DIRECTORIES = [
    Path("docs/architecture"),
    Path("docs/platform"),
    Path("docs/runtime"),
    Path("docs/syscalls"),
    Path("docs/memory"),
    Path("docs/nodus"),
    Path("docs/sdk"),
]
REQUIRED_FIELDS = ("title", "last_verified", "api_version", "status", "owner")
VALID_STATUS = {"current", "outdated", "draft"}
API_VERSION_RE = re.compile(r"^\d+\.\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class LintResult:
    path: str
    errors: list[str]
    warnings: list[str]


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_simple_yaml(frontmatter: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in frontmatter.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip().strip('"').strip("'")
    return parsed


def parse_frontmatter(text: str) -> tuple[dict[str, object] | None, str | None]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return None, "MISSING_FRONTMATTER"
    end_marker = "\n---\n"
    end_index = normalized.find(end_marker, 4)
    if end_index == -1:
        return None, "MISSING_FRONTMATTER"
    raw_frontmatter = normalized[4:end_index]
    if yaml is not None:
        try:
            parsed = yaml.safe_load(raw_frontmatter) or {}
            if isinstance(parsed, dict):
                return parsed, None
        except Exception:
            pass
    return _parse_simple_yaml(raw_frontmatter), None


def lint_file(
    path: str | Path,
    *,
    today: dt.date | None = None,
    stale_after_days: int = 90,
) -> LintResult:
    doc_path = Path(path)
    text = _read_text(doc_path)
    errors: list[str] = []
    warnings: list[str] = []
    frontmatter, frontmatter_error = parse_frontmatter(text)
    if frontmatter_error is not None:
        errors.append(frontmatter_error)
        return LintResult(str(doc_path).replace("\\", "/"), errors, warnings)

    assert frontmatter is not None
    for field in REQUIRED_FIELDS:
        value = frontmatter.get(field)
        if value is None or str(value).strip() == "":
            errors.append(f"MISSING_FIELD ({field})")

    last_verified_raw = str(frontmatter.get("last_verified", "")).strip()
    status_raw = str(frontmatter.get("status", "")).strip()
    api_version_raw = str(frontmatter.get("api_version", "")).strip()

    verified_date: dt.date | None = None
    if last_verified_raw:
        if not DATE_RE.fullmatch(last_verified_raw):
            errors.append("INVALID_DATE")
        else:
            try:
                verified_date = dt.date.fromisoformat(last_verified_raw)
            except ValueError:
                errors.append("INVALID_DATE")

    if status_raw and status_raw not in VALID_STATUS:
        errors.append("INVALID_STATUS")

    if api_version_raw and not API_VERSION_RE.fullmatch(api_version_raw):
        errors.append("INVALID_API_VERSION")

    if verified_date is not None:
        today_value = today or dt.date.today()
        age_days = (today_value - verified_date).days
        if age_days > stale_after_days and status_raw != "outdated":
            warnings.append(
                f"STALE (last_verified: {last_verified_raw}, {age_days} days ago)"
            )

    return LintResult(str(doc_path).replace("\\", "/"), errors, warnings)


def iter_markdown_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_file() and path.suffix.lower() == ".md":
            files.append(path)
            continue
        files.extend(sorted(candidate for candidate in path.rglob("*.md") if candidate.is_file()))
    return files


def lint_paths(
    paths: list[Path],
    *,
    today: dt.date | None = None,
    stale_after_days: int = 90,
) -> list[LintResult]:
    return [
        lint_file(path, today=today, stale_after_days=stale_after_days)
        for path in iter_markdown_files(paths)
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lint docs frontmatter and freshness metadata.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors.",
    )
    parser.add_argument(
        "--dir",
        dest="dirs",
        action="append",
        default=[],
        help="Lint only the provided directory or file. May be passed multiple times.",
    )
    parser.add_argument(
        "--stale-after-days",
        type=int,
        default=90,
        help="Warn when last_verified is older than this many days.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = [Path(item) for item in args.dirs] if args.dirs else REQUIRED_DIRECTORIES
    results = lint_paths(paths, stale_after_days=args.stale_after_days)

    error_results = [result for result in results if result.errors]
    warning_results = [result for result in results if result.warnings]
    clean_count = sum(1 for result in results if not result.errors and not result.warnings)

    if error_results:
        print("ERRORS:")
        for result in error_results:
            for error in result.errors:
                print(f"  {result.path}: {error}")
        print()

    if warning_results:
        print("WARNINGS:")
        for result in warning_results:
            for warning in result.warnings:
                print(f"  {result.path}: {warning}")
        print()

    print("SUMMARY:")
    print(f"  Checked: {len(results)} files")
    print(f"  Errors:  {len(error_results)} files")
    print(f"  Warnings: {len(warning_results)} files")
    print(f"  Clean:   {clean_count} files")

    has_errors = bool(error_results)
    has_strict_warnings = bool(args.strict and warning_results)
    return 1 if has_errors or has_strict_warnings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
