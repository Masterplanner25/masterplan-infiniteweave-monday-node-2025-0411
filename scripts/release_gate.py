#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A.I.N.D.Y. V1 Release Gate
============================
Run from the repo root:

    python scripts/release_gate.py

Exit 0  = READY TO TAG v1.0.0
Exit 1  = BLOCKED (prints what is failing)

Each gate maps to either a task in v1_progress.json or an automated check.
The gate runs in two modes:
  --full   Run all checks including live server checks (requires running instance)
  (default) Run all checks that do not require a live server
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

# Force UTF-8 output on Windows to handle Unicode status symbols
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Repo layout ───────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent.resolve()
AINDY_DIR = REPO_ROOT / "AINDY"
PROGRESS_FILE = REPO_ROOT / "v1_progress.json"
VERSION_FILE = AINDY_DIR / "version.json"
TARGET_VERSION = "1.0.0"

# ── Result accumulator ────────────────────────────────────────────────────────
FAILURES: list[tuple[str, str]] = []   # (severity, message)
WARNINGS: list[str] = []
PASSES:   list[str] = []


def fail(message: str) -> None:
    FAILURES.append(("BLOCKER", message))


def warn(message: str) -> None:
    WARNINGS.append(message)


def ok(message: str) -> None:
    PASSES.append(message)


# ── Individual gate checks ────────────────────────────────────────────────────

def gate_progress_tracker() -> None:
    """All BLOCKER tasks must be marked complete in v1_progress.json."""
    if not PROGRESS_FILE.exists():
        fail("v1_progress.json not found at repo root")
        return

    with open(PROGRESS_FILE) as f:
        progress = json.load(f)

    blocker_tasks = [
        tid for tid, t in progress["tasks"].items()
        if t["priority"] == "BLOCKER"
    ]
    incomplete = [
        tid for tid in blocker_tasks
        if progress["tasks"][tid]["status"] not in {"complete", "completed"}
    ]

    if incomplete:
        fail(f"Incomplete BLOCKER tasks ({len(incomplete)}/{len(blocker_tasks)}):\n"
             + "\n".join(f"  - {tid}: {progress['tasks'][tid]['title']}"
                        for tid in incomplete))
    else:
        ok(f"All {len(blocker_tasks)} BLOCKER tasks complete")


def gate_v1_gate_tests() -> None:
    """AINDY/tests/v1_gates/ must all pass."""
    gates_dir = AINDY_DIR / "tests" / "v1_gates"
    if not gates_dir.exists():
        fail("AINDY/tests/v1_gates/ directory does not exist")
        return

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/v1_gates/", "-q", "--tb=short",
         "--no-header"],
        capture_output=True, text=True, cwd=str(AINDY_DIR)
    )
    if result.returncode == 0:
        last_line = [line for line in result.stdout.strip().splitlines() if line.strip()]
        ok(f"V1 gate tests passed: {last_line[-1] if last_line else 'OK'}")
    else:
        # Show only last 40 lines of output to keep readable
        output_tail = "\n".join(result.stdout.splitlines()[-40:])
        fail(f"V1 gate tests failing:\n{output_tail}")


def gate_full_test_suite() -> None:
    """Full test suite must pass at >= 69% coverage."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q",
         "--cov=.", "--cov-fail-under=69", "--tb=line", "--no-header",
         "-x",  # stop on first failure for speed
         ],
        capture_output=True, text=True, cwd=str(AINDY_DIR)
    )
    if result.returncode == 0:
        cov_lines = [line for line in result.stdout.splitlines() if "%" in line and "TOTAL" in line]
        ok(f"Full test suite passed. {cov_lines[-1].strip() if cov_lines else 'Coverage OK'}")
    else:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-25:])
        fail(f"Full test suite failing or coverage < 69%:\n{tail}")


def gate_services_directory() -> None:
    """services/ must contain only auth_service.py (and __init__.py)."""
    services_dir = AINDY_DIR / "services"
    if not services_dir.exists():
        fail("AINDY/services/ directory does not exist")
        return

    py_files = sorted(
        f.name for f in services_dir.glob("*.py")
        if f.name not in ("__init__.py",)
    )
    allowed = {"auth_service.py"}
    extra = set(py_files) - allowed

    if extra:
        fail("services/ must contain only auth_service.py, also found:\n"
             + "\n".join(f"  - {f}" for f in sorted(extra)))
    else:
        ok("services/ contains only auth_service.py")


def gate_no_shim_files() -> None:
    """No migration shim files may remain."""
    # Exclude tests/ — test files may reference the concept without being shims.
    # Use Python-native scanning so the gate works on Windows without grep.
    shim_files: list[str] = []
    for path in AINDY_DIR.rglob("*.py"):
        if "tests" in path.parts:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            warn(f"Could not read {path}: {exc}")
            continue
        if "MIGRATION SHIM" in content:
            shim_files.append(str(path))
    if shim_files:
        fail(f"Migration shims still present ({len(shim_files)} files):\n"
             + "\n".join(f"  - {f}" for f in shim_files))
    else:
        ok("No migration shim files remain")


def gate_version_json() -> None:
    """version.json must exist and declare the correct version."""
    if not VERSION_FILE.exists():
        fail("version.json not found at repo root")
        return
    try:
        with open(VERSION_FILE) as f:
            data = json.load(f)
        version = data.get("version", "")
        if version == TARGET_VERSION:
            ok(f"version.json declares version={version}")
        else:
            fail(f"version.json has version={version!r}, expected {TARGET_VERSION!r}")
    except json.JSONDecodeError as e:
        fail(f"version.json is not valid JSON: {e}")


def gate_changelog() -> None:
    """CHANGELOG.md must have a [1.0.0] section."""
    changelog = AINDY_DIR / "CHANGELOG.md"
    if not changelog.exists():
        fail("AINDY/CHANGELOG.md does not exist")
        return
    content = changelog.read_text(encoding="utf-8")
    if "[1.0.0]" in content:
        ok("CHANGELOG.md has [1.0.0] section")
    else:
        fail("CHANGELOG.md missing [1.0.0] section")


def gate_readme() -> None:
    """README.md must exist at repo root with meaningful content."""
    readme = REPO_ROOT / "README.md"
    if not readme.exists():
        fail("README.md not found at repo root")
        return
    content = readme.read_text(encoding="utf-8")
    if len(content) < 300:
        fail(f"README.md is too short ({len(content)} chars) — must have real platform content")
        return
    if "platform" not in content.lower():
        fail("README.md does not mention 'platform'")
        return
    ok("README.md exists with platform content")


def gate_root_debris() -> None:
    """Root-level debug/repair scripts must not exist."""
    debris = ["fix_backend.py", "script.py", "@echo off.bat", "git_health_check.bat"]
    found = [f for f in debris if (REPO_ROOT / f).exists()]
    if found:
        fail(f"Root-level debris files still present: {found}\n"
             "  These must be removed before V1.")
    else:
        ok("No root-level debris files")


def gate_no_bridge_directory() -> None:
    """bridge/ must not contain deprecated legacy bridge implementation files."""
    bridge_dir = AINDY_DIR / "bridge"
    if bridge_dir.exists():
        py_files = list(bridge_dir.glob("*.py"))
        allowed = {"__init__.py", "nodus_memory_bridge.py"}
        unexpected = [f for f in py_files if f.name not in allowed]
        legacy_bridge = bridge_dir / "bridge.py"
        if legacy_bridge.exists():
            fail("AINDY/bridge/ still contains legacy bridge.py (should be absorbed into memory/)")
        elif unexpected:
            fail("AINDY/bridge/ contains unexpected Python files:\n"
                 + "\n".join(f"  - {f}" for f in unexpected))
        else:
            ok("AINDY/bridge/ contains only allowed compatibility/native bridge files")
    else:
        ok("AINDY/bridge/ has been removed")


def gate_new_packages_exist() -> None:
    """kernel/, memory/, agents/, platform_layer/, analytics/, domain/ must exist."""
    required = ["kernel", "memory", "agents", "platform_layer", "analytics", "domain"]
    missing = [pkg for pkg in required if not (AINDY_DIR / pkg / "__init__.py").exists()]
    if missing:
        fail(f"Required packages not yet created: {missing}")
    else:
        ok(f"All modular packages exist: {required}")


def gate_docker_build(full_mode: bool) -> None:
    """Docker image must build successfully."""
    if not full_mode:
        warn("Docker build check skipped in default mode (run with --full to enable)")
        return

    dockerfile = AINDY_DIR / "Dockerfile"
    if not dockerfile.exists():
        fail("AINDY/Dockerfile does not exist")
        return

    result = subprocess.run(
        ["docker", "build", "-t", "aindy:v1-gate-check", "."],
        capture_output=True, text=True, cwd=str(AINDY_DIR),
        timeout=300,
    )
    if result.returncode == 0:
        ok("Docker build succeeded")
    else:
        fail(f"Docker build failed:\n{result.stderr[-1500:]}")


def gate_health_endpoint(full_mode: bool) -> None:
    """GET /health must return {status, db, version} with db=ok."""
    if not full_mode:
        warn("Health endpoint check skipped (run with --full and a running server to enable)")
        return

    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request("http://localhost:8000/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
        if body.get("db") == "ok":
            ok(f"Health endpoint: {body}")
        else:
            fail(f"Health endpoint reports db={body.get('db')!r}, expected 'ok'. Full: {body}")
        if "version" not in body:
            fail("Health endpoint missing 'version' field")
        if body.get("version") != TARGET_VERSION:
            fail(f"Health endpoint version={body.get('version')!r}, expected {TARGET_VERSION!r}")
    except Exception as e:
        fail(f"Health endpoint unreachable: {e}")


def gate_docs_exist() -> None:
    """Required documentation files must exist."""
    required_docs = [
        AINDY_DIR / "docs" / "getting-started" / "index.md",
        AINDY_DIR / "docs" / "syscalls" / "reference.md",
    ]
    missing = [str(p) for p in required_docs if not p.exists()]
    if missing:
        fail("Required docs missing:\n" + "\n".join(f"  - {p}" for p in missing))
    else:
        ok("Required documentation files exist")


def gate_env_example_secret_key() -> None:
    """SECRET_KEY in .env.example must not be a real/guessable value."""
    env_example = REPO_ROOT / ".env.example"
    if not env_example.exists():
        warn(".env.example not found — skipping SECRET_KEY check")
        return

    content = env_example.read_text(encoding="utf-8")
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("SECRET_KEY="):
            value = stripped.split("=", 1)[1].strip()
            # A good placeholder starts with REPLACE/CHANGE/YOUR or contains
            # instructional text. A bad value is short or is a known default.
            value_lower = value.lower()
            is_explicit_placeholder = any(
                value_lower.startswith(p)
                for p in ("replace", "change_this", "your-", "your_", "<", "!!",
                          "generate", "run_python", "python3_-c")
            )
            bad_exact = {"secret", "changeme", "password", "12345678",
                        "insecure", "unsafe", "dev", "development"}
            is_bad_exact = value_lower in bad_exact
            is_too_short = len(value) < 12

            if is_bad_exact or is_too_short:
                fail(f"SECRET_KEY in .env.example is a known-bad default: {value!r}\n"
                     "  Replace with a placeholder that cannot be used directly.")
            elif is_explicit_placeholder or len(value) >= 20:
                ok("SECRET_KEY in .env.example is a safe placeholder")
            else:
                warn(f"SECRET_KEY in .env.example may be a real value: {value!r} — verify it is a placeholder")
            return
    warn("SECRET_KEY line not found in .env.example")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="A.I.N.D.Y. V1 Release Gate — exits 0 if ready to tag"
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Run all checks including Docker build and live server checks"
    )
    parser.add_argument(
        "--skip-tests", action="store_true",
        help="Skip pytest runs (for fast structure-only checks)"
    )
    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("  A.I.N.D.Y. V1 RELEASE GATE")
    print(f"  Mode: {'full' if args.full else 'standard'}")
    print("=" * 65 + "\n")

    # Run all gates
    gate_progress_tracker()
    gate_version_json()
    gate_services_directory()
    gate_no_shim_files()
    gate_new_packages_exist()
    gate_no_bridge_directory()
    gate_root_debris()
    gate_changelog()
    gate_readme()
    gate_docs_exist()
    gate_env_example_secret_key()

    if not args.skip_tests:
        gate_v1_gate_tests()
        gate_full_test_suite()

    gate_docker_build(full_mode=args.full)
    gate_health_endpoint(full_mode=args.full)

    # ── Print results ─────────────────────────────────────────────────────────
    print("\n" + "-" * 65)
    print("  PASSED CHECKS")
    print("-" * 65)
    for msg in PASSES:
        print(f"  ✓  {msg}")

    if WARNINGS:
        print("\n" + "-" * 65)
        print("  WARNINGS (non-blocking)")
        print("-" * 65)
        for msg in WARNINGS:
            print(f"  ⚠  {msg}")

    if FAILURES:
        print("\n" + "-" * 65)
        print("  FAILURES (BLOCKING RELEASE)")
        print("-" * 65)
        for _, msg in FAILURES:
            # Indent multi-line messages
            lines = msg.splitlines()
            print(f"  ✗  {lines[0]}")
            for line in lines[1:]:
                print(f"     {line}")

        print("\n" + "=" * 65)
        print("  ❌  RELEASE GATE: FAILED")
        print(f"  {len(FAILURES)} blocker(s) must be resolved before tagging v1.0.0")
        print("=" * 65 + "\n")
        return 1
    else:
        print("\n" + "=" * 65)
        print("  ✅  RELEASE GATE: PASSED")
        print("  All checks green. Ready to tag v1.0.0:")
        print("    git tag -a v1.0.0 -m 'A.I.N.D.Y. Platform V1'")
        print("    git push origin v1.0.0")
        print("=" * 65 + "\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
