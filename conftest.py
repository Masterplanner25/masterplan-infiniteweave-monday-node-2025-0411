# Root conftest — pytest_plugins must be declared here (not in a sub-conftest).
pytest_plugins = [
    "AINDY.tests.fixtures.db",
    "AINDY.tests.fixtures.auth",
    "AINDY.tests.fixtures.users",
    "AINDY.tests.fixtures.client",
    "AINDY.tests.fixtures.common",
]