from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MONGO_URL", "")
os.environ.setdefault("AINDY_ALLOW_SQLITE", "1")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-testing-only")
os.environ.setdefault("DEEPSEEK_API_KEY", "fake-deepseek-key")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("TEST_MODE", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-not-production")
os.environ.setdefault("AINDY_API_KEY", "test-api-key-for-pytest-only")
os.environ.setdefault("PERMISSION_SECRET", "test-permission-secret-for-pytest-only")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
os.environ.setdefault("AINDY_ASYNC_HEAVY_EXECUTION", "false")
os.environ.setdefault("AINDY_ENABLE_BACKGROUND_TASKS", "false")
os.environ.setdefault("AINDY_ENFORCE_SCHEMA", "false")
os.environ.setdefault("AINDY_ENABLE_LEGACY_SURFACE", "true")
os.environ.setdefault("SKIP_MONGO_PING", "1")
os.environ.setdefault("AINDY_SKIP_MONGO_PING", "1")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ["PATH"] = ROOT + os.pathsep + os.environ.get("PATH", "")

_original_subprocess_run = subprocess.run


def _compat_subprocess_run(args, *popenargs, **kwargs):
    if (
        isinstance(args, (list, tuple))
        and len(args) >= 4
        and args[0] == "grep"
        and args[1] == "-r"
    ):
        pattern = str(args[2])
        root = Path(args[3])
        matches = []
        for path in root.rglob("*.py"):
            if "tests" in path.parts:
                continue
            try:
                if pattern in path.read_text(encoding="utf-8", errors="ignore"):
                    matches.append(str(path))
            except OSError:
                continue
        return subprocess.CompletedProcess(
            args=args,
            returncode=0 if matches else 1,
            stdout="\n".join(matches),
            stderr="",
        )
    return _original_subprocess_run(args, *popenargs, **kwargs)


subprocess.run = _compat_subprocess_run


def pytest_runtest_setup(item):
    try:
        from AINDY.kernel.circuit_breaker import get_openai_circuit_breaker

        get_openai_circuit_breaker().reset()
    except Exception:
        pass

