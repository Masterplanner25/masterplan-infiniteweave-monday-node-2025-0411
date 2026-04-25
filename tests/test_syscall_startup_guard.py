import logging
from types import SimpleNamespace


def test_get_registered_syscalls_returns_list():
    from AINDY.kernel.syscall_registry import get_registered_syscalls

    result = get_registered_syscalls()
    assert isinstance(result, list)


def test_required_syscalls_registry_roundtrip():
    from AINDY.platform_layer.registry import (
        get_required_syscalls,
        register_required_syscall,
    )

    register_required_syscall("test.syscall.probe")
    assert "test.syscall.probe" in get_required_syscalls()


def test_missing_syscalls_logged_not_raised_in_dev(monkeypatch, caplog):
    """In non-production mode, missing required syscalls warn but do not raise."""
    from AINDY.main import _verify_required_syscalls_registered

    monkeypatch.setattr(
        "AINDY.main.settings",
        SimpleNamespace(is_prod=False, is_testing=False),
    )
    monkeypatch.setattr(
        "AINDY.platform_layer.registry.get_required_syscalls",
        lambda: ["sys.v1.test.missing"],
    )
    monkeypatch.setattr(
        "AINDY.kernel.syscall_registry.get_registered_syscalls",
        lambda: [],
    )

    with caplog.at_level(logging.WARNING):
        _verify_required_syscalls_registered()

    assert "Required syscalls missing after bootstrap" in caplog.text


def test_get_registered_syscalls_not_empty_after_boot(client):
    """After a full app boot, at least one syscall must be registered."""
    from AINDY.kernel.syscall_registry import get_registered_syscalls

    syscalls = get_registered_syscalls()
    assert len(syscalls) > 0, (
        "No syscalls registered after startup. "
        "Domain bootstrap modules likely failed to load."
    )
