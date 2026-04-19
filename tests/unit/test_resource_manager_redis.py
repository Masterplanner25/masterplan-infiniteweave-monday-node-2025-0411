from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import redis

from AINDY.kernel import resource_manager as rm_module
from AINDY.kernel.resource_manager import RedisResourceBackend, ResourceManager


def test_tenant_concurrency_enforced_across_instances():
    shared_state = {"tenant-a": 0}
    backend = MagicMock()

    def increment_tenant_active(tenant_id: str) -> int:
        shared_state[tenant_id] = shared_state.get(tenant_id, 0) + 1
        return shared_state[tenant_id]

    backend.increment_tenant_active.side_effect = increment_tenant_active
    backend.get_tenant_active.side_effect = lambda tenant_id: shared_state.get(tenant_id, 0)
    backend.decrement_tenant_active.side_effect = lambda tenant_id: shared_state.get(tenant_id, 0)
    backend.add_cpu_ms.return_value = 0
    backend.get_cpu_ms.return_value = 0
    backend.increment_syscalls.return_value = 0
    backend.get_syscalls.return_value = 0

    with (
        patch("AINDY.kernel.resource_manager._get_backend", return_value=backend),
        patch.object(rm_module, "MAX_CONCURRENT_PER_TENANT", 1),
    ):
        rm1 = ResourceManager()
        rm2 = ResourceManager()

        rm1.mark_started("tenant-a", "eu-1")
        ok, reason = rm2.can_execute("tenant-a", "eu-2")

    assert ok is False
    assert "RESOURCE_LIMIT_EXCEEDED" in reason


def test_redis_failure_falls_through():
    backend = MagicMock()
    backend.increment_tenant_active.side_effect = redis.RedisError("redis down")
    backend.get_tenant_active.side_effect = redis.RedisError("redis down")

    with patch("AINDY.kernel.resource_manager._get_backend", return_value=backend):
        rm = ResourceManager()
        rm.mark_started("tenant-a", "eu-1")

    assert rm.get_tenant_active("tenant-a") == 1


def test_eu_keys_expired():
    backend = MagicMock()
    backend.increment_tenant_active.return_value = 1
    backend.get_tenant_active.return_value = 1
    backend.decrement_tenant_active.return_value = 0

    with patch("AINDY.kernel.resource_manager._get_backend", return_value=backend):
        rm = ResourceManager()
        rm.mark_started("tenant-a", "eu-1")
        rm.mark_completed("tenant-a", "eu-1")

    backend.delete_eu.assert_called_once_with("eu-1")


def test_reset_clears_only_aindy_rm_keys():
    client = MagicMock()
    client.register_script.return_value = MagicMock(return_value=0)
    client.scan.side_effect = [
        ("1", ["aindy:rm:tenant:t1:active"]),
        ("0", ["aindy:rm:eu:eu-1:cpu_ms", "aindy:rm:eu:eu-1:syscalls"]),
    ]

    with patch("redis.from_url", return_value=client):
        backend = RedisResourceBackend("redis://example")

    backend.reset_all()

    assert client.scan.call_args_list == [
        call(cursor=0, match="aindy:rm:*", count=100),
        call(cursor="1", match="aindy:rm:*", count=100),
    ]
    assert client.flushdb.called is False
