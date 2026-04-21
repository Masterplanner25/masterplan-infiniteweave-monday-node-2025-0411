from __future__ import annotations

from AINDY.kernel.resource_manager import ResourceManager


def test_pending_purge_cleaned_on_next_can_execute():
    rm = ResourceManager()

    rm.mark_started("t1", "eu-1")
    rm.mark_completed("t1", "eu-1")

    assert "eu-1" in rm._pending_purge

    rm.can_execute("t1")

    assert "eu-1" not in rm._usage
    assert "eu-1" not in rm._pending_purge


def test_usage_not_purged_before_can_execute_called():
    rm = ResourceManager()

    rm.mark_started("t1", "eu-1")
    rm.record_usage("eu-1", {"cpu_time_ms": 5, "memory_bytes": 10, "syscall_count": 1})
    rm.mark_completed("t1", "eu-1")

    usage = rm.get_usage("eu-1")

    assert usage["cpu_time_ms"] == 5
    assert "eu-1" in rm._usage
    assert "eu-1" in rm._pending_purge


def test_reset_clears_pending_purge():
    rm = ResourceManager()

    rm.mark_started("t1", "eu-1")
    rm.mark_completed("t1", "eu-1")
    rm.reset()

    assert rm._pending_purge == set()


def test_many_completions_do_not_leak_usage():
    rm = ResourceManager()

    for idx in range(100):
        eu_id = f"eu-{idx}"
        rm.mark_started("t1", eu_id)
        rm.mark_completed("t1", eu_id)

    rm.can_execute("t1")

    assert len(rm._usage) == 0
