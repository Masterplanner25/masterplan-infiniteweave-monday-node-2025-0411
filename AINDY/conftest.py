# Root conftest — pytest_plugins must be declared here (not in a sub-conftest).
pytest_plugins = [
    "tests.fixtures.db",
    "tests.fixtures.auth",
    "tests.fixtures.users",
    "tests.fixtures.client",
    "tests.fixtures.common",
]
