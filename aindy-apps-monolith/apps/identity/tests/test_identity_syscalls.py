from __future__ import annotations

import pathlib
import uuid

from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY, SyscallContext


def test_identity_syscalls_registered(client):
    """Both identity syscalls must be in the registry after startup."""
    assert "sys.v1.identity.get_context" in SYSCALL_REGISTRY
    assert "sys.v1.identity.observe" in SYSCALL_REGISTRY


def test_get_context_returns_string_on_missing_user():
    """get_context must return empty string for unknown user, not raise."""
    handler = SYSCALL_REGISTRY["sys.v1.identity.get_context"].handler
    ctx = SyscallContext(
        execution_unit_id=str(uuid.uuid4()),
        user_id="00000000-0000-0000-0000-000000000000",
        capabilities=["identity.read"],
        trace_id=str(uuid.uuid4()),
    )
    result = handler({"user_id": "00000000-0000-0000-0000-000000000000"}, ctx)
    assert "context" in result
    assert isinstance(result["context"], str)


def test_observe_returns_false_on_missing_identity():
    """observe must return safe false result, not raise."""
    handler = SYSCALL_REGISTRY["sys.v1.identity.observe"].handler
    ctx = SyscallContext(
        execution_unit_id=str(uuid.uuid4()),
        user_id="",
        capabilities=["identity.write"],
        trace_id=str(uuid.uuid4()),
    )
    result = handler(
        {
            "user_id": "",
            "event_type": "test_event",
            "context": {},
        },
        ctx,
    )
    assert result == {"observed": False}


def test_arm_no_direct_identity_import():
    """ARM must not import from apps.identity directly."""
    source = pathlib.Path(
        "apps/arm/services/deepseek/deepseek_code_analyzer.py"
    ).read_text(encoding="utf-8")
    assert "from apps.identity" not in source, (
        "deepseek_code_analyzer.py still imports from apps.identity directly. "
        "Use sys.v1.identity.* syscalls instead."
    )
