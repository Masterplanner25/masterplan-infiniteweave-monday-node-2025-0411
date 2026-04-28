#!/usr/bin/env python3
"""
check_api_contracts.py

Verifies that every router file referenced in API_CONTRACTS.md exists on
disk, and that every router file on disk is referenced in the doc.

Usage:
  python scripts/check_api_contracts.py
  python scripts/check_api_contracts.py --warn-only
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
API_CONTRACTS_PATH = REPO_ROOT / "docs" / "platform" / "interfaces" / "API_CONTRACTS.md"
ROUTER_PATH_RE = re.compile(r"`([^`]+(?:router|routes)[^`]*\.py)`")

ALLOWLIST = {
    "AINDY/routes/__init__.py",
    "AINDY/routes/platform/nodus_shared.py",  # shared helper module, not a router surface
    "AINDY/routes/platform/schemas.py",  # shared request/response models, not a router surface
    "AINDY/routes/version_router.py",  # dormant router module; not mounted by the live app
    "apps/search/routes/_route_helpers.py",  # helper utilities for search routes, never mounted directly
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check API contract router inventory drift.")
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Print the report but always exit 0.",
    )
    return parser


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_doc_paths(text: str) -> list[str]:
    return [match.replace("\\", "/") for match in ROUTER_PATH_RE.findall(text)]


def iter_router_files() -> set[str]:
    found: set[str] = set()
    for pattern in (
        "AINDY/routes/*.py",
        "AINDY/routes/**/*.py",
        "apps/*/routes/*.py",
        "apps/*/routes/**/*.py",
    ):
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            name = path.name
            if name == "__init__.py":
                continue
            if "__pycache__" in rel.split("/"):
                continue
            if name.endswith("_test.py") or name.startswith("test_"):
                continue
            found.add(rel)
    return found


def report_section(title: str, items: list[str], intro: str) -> None:
    print(title)
    print(intro)
    if items:
        for item in items:
            print(f"  - {item}")
    else:
        print("  (none)")
    print()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    text = read_text(API_CONTRACTS_PATH)
    doc_paths = extract_doc_paths(text)
    doc_path_set = set(doc_paths)

    ghosts = sorted(path for path in doc_path_set if not (REPO_ROOT / path).exists())

    actual_router_files = iter_router_files()
    missing = sorted(
        path for path in actual_router_files
        if path not in doc_path_set and path not in ALLOWLIST
    )

    print("API contract drift report")
    print(f"Doc: {API_CONTRACTS_PATH.relative_to(REPO_ROOT).as_posix()}")
    print(f"Referenced router paths: {len(doc_paths)}")
    print(f"Router files on disk: {len(actual_router_files)}")
    print()

    report_section(
        "GHOST entries",
        ghosts,
        "These paths are in API_CONTRACTS.md but the files do not exist.",
    )
    report_section(
        "MISSING entries",
        missing,
        "These router files exist on disk but are not referenced in API_CONTRACTS.md.",
    )

    print("SUMMARY")
    print(f"  Ghost:   {len(ghosts)}")
    print(f"  Missing: {len(missing)}")
    print(f"  Allowlist: {len(ALLOWLIST)}")

    if args.warn_only:
        return 0
    return 1 if ghosts or missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
