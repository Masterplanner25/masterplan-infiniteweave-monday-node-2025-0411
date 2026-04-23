from __future__ import annotations

import os
import subprocess
import sys
import types
import importlib
from pathlib import Path

# Prefer the real prometheus_client when it is installed because tests
# inspect registry samples and hit the mounted /metrics ASGI app.
if "prometheus_client" not in sys.modules:
    try:
        importlib.import_module("prometheus_client")
    except ModuleNotFoundError:
        _pm = types.ModuleType("prometheus_client")

        class _Metric:
            def __init__(self, *a, **kw): pass
            def labels(self, **kw): return self
            def inc(self, *a): pass
            def observe(self, *a): pass
            def set(self, *a): pass

        for _cls_name in ("Counter", "Histogram", "Gauge", "Summary", "Info", "Enum", "CollectorRegistry"):
            setattr(_pm, _cls_name, type(_cls_name, (_Metric,), {}))

        def _make_asgi_app(*a, **kw):
            async def _app(scope, receive, send):
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [(b"content-type", b"text/plain; version=0.0.4")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"",
                        "more_body": False,
                    }
                )
            return _app

        _pm.make_asgi_app = _make_asgi_app
        sys.modules["prometheus_client"] = _pm

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


import pytest


@pytest.fixture(autouse=True)
def reset_resource_manager():
    """Reset ResourceManager state before and after every test.

    Prevents active-count leakage from one test contaminating the next.
    The ResourceManager singleton is shared across the process; this fixture
    ensures each test starts and ends with a clean slate.
    """
    try:
        from AINDY.kernel.resource_manager import get_resource_manager
        get_resource_manager().reset()
    except Exception:
        pass
    yield
    try:
        from AINDY.kernel.resource_manager import get_resource_manager
        get_resource_manager().reset()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clear_global_app_dependency_overrides():
    """Prevent override leakage across tests that import the global FastAPI app.

    Many tests use ``from AINDY.main import app`` directly instead of the shared
    ``app`` fixture in ``tests/fixtures/client.py``. Those tests can leave
    ``app.dependency_overrides`` populated when they fail early or omit cleanup,
    which makes later authenticated tests resolve the wrong dependencies.

    Clear overrides on both sides of every test so order does not matter.
    """
    try:
        from AINDY.main import app as fastapi_app

        fastapi_app.dependency_overrides.clear()
    except Exception:
        fastapi_app = None

    yield

    if fastapi_app is not None:
        fastapi_app.dependency_overrides.clear()

