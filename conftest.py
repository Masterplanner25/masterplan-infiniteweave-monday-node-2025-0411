# Root conftest â€” pytest_plugins must be declared here (not in a sub-conftest).
import os
import sys

os.environ.setdefault("TEST_MODE", "1")
os.environ.setdefault("SKIP_MONGO_PING", "1")
os.environ.setdefault("AINDY_SKIP_MONGO_PING", "1")

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
SDK_DIR = os.path.join(PROJECT_ROOT, "sdk")

if os.path.isdir(SDK_DIR) and SDK_DIR not in sys.path:
    sys.path.insert(0, SDK_DIR)

pytest_plugins = [
    "tests.fixtures.db",
    "tests.fixtures.auth",
    "tests.fixtures.users",
    "tests.fixtures.client",
    "tests.fixtures.common",
]
