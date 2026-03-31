from __future__ import annotations

import os
import sys

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

pytest_plugins = [
    "tests.fixtures.db",
    "tests.fixtures.auth",
    "tests.fixtures.users",
    "tests.fixtures.client",
    "tests.fixtures.common",
]
