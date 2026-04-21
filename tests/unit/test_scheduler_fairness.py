from __future__ import annotations

from unittest.mock import MagicMock, patch

from AINDY.kernel.scheduler_engine import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    ScheduledItem,
    SchedulerEngine,
)


def _make_engine():
    se = SchedulerEngine()
    se._rehydration_complete.set()
    se._check_stale_waits = lambda: 0  # type: ignore[method-assign]
    return se


def _item(tenant_id, eu_id, priority=PRIORITY_NORMAL, callback=None, **kwargs):
    return ScheduledItem(
        execution_unit_id=eu_id,
        tenant_id=tenant_id,
        priority=priority,
        run_callback=callback or (lambda: None),
        **kwargs,
    )


def test_saturated_tenant_does_not_block_other_tenants():
    se = _make_engine()
    rm = MagicMock()
    rm.can_execute.side_effect = lambda tenant_id, eu_id: (
        (False, "limit") if tenant_id == "tenant-A" else (True, None)
    )
    ran: list[str] = []
    se.enqueue(_item("tenant-A", "eu-a", callback=lambda: ran.append("A")))
    se.enqueue(_item("tenant-B", "eu-b", callback=lambda: ran.append("B")))

    with patch("AINDY.kernel.scheduler_engine.get_resource_manager", return_value=rm), patch(
        "AINDY.core.execution_dispatcher.dispatch",
        side_effect=lambda _stub, cb, _ctx: cb(),
    ):
        dispatched = se.schedule()

    assert dispatched == 1
    assert ran == ["B"]
    assert se.queue_depth()[PRIORITY_NORMAL] == 1


def test_saturated_tenant_stays_in_queue():
    se = _make_engine()
    rm = MagicMock()
    rm.can_execute.side_effect = lambda tenant_id, eu_id: (
        (False, "limit") if tenant_id == "tenant-A" else (True, None)
    )
    se.enqueue(_item("tenant-A", "eu-a"))
    se.enqueue(_item("tenant-B", "eu-b"))

    with patch("AINDY.kernel.scheduler_engine.get_resource_manager", return_value=rm), patch(
        "AINDY.core.execution_dispatcher.dispatch",
        side_effect=lambda _stub, cb, _ctx: cb(),
    ):
        se.schedule()

    remaining = se.dequeue_next()
    assert remaining is not None
    assert remaining.tenant_id == "tenant-A"
    assert remaining.execution_unit_id == "eu-a"


def test_single_saturated_tenant_does_not_stall_cycle():
    se = _make_engine()
    rm = MagicMock()
    rm.can_execute.side_effect = lambda tenant_id, eu_id: (
        (False, "limit") if tenant_id == "tenant-A" else (True, None)
    )
    ran: list[str] = []
    for idx in range(5):
        se.enqueue(_item("tenant-A", f"eu-a-{idx}"))
    for idx in range(3):
        se.enqueue(_item("tenant-B", f"eu-b-{idx}", callback=lambda i=idx: ran.append(f"B{i}")))

    with patch("AINDY.kernel.scheduler_engine.get_resource_manager", return_value=rm), patch(
        "AINDY.core.execution_dispatcher.dispatch",
        side_effect=lambda _stub, cb, _ctx: cb(),
    ):
        dispatched = se.schedule()

    assert dispatched == 3
    assert sorted(ran) == ["B0", "B1", "B2"]
    assert se.queue_depth()[PRIORITY_NORMAL] == 5


def test_dispatch_failure_re_enqueues_up_to_max_retries():
    se = _make_engine()
    rm = MagicMock()
    rm.can_execute.return_value = (True, None)
    item = _item("tenant-A", "eu-fail", max_retries=2)
    se.enqueue(item)

    with patch("AINDY.kernel.scheduler_engine.get_resource_manager", return_value=rm), patch(
        "AINDY.core.execution_dispatcher.dispatch",
        side_effect=RuntimeError("boom"),
    ):
        first = se.schedule()
        retry1 = se.dequeue_next()
        assert first == 0
        assert retry1 is not None
        assert retry1.retry_count == 1
        assert retry1.priority == PRIORITY_LOW
        se.enqueue(retry1)

        second = se.schedule()
        retry2 = se.dequeue_next()
        assert second == 0
        assert retry2 is not None
        assert retry2.retry_count == 2
        assert retry2.priority == PRIORITY_LOW
        se.enqueue(retry2)

        third = se.schedule()

    assert third == 0
    assert se.dequeue_next() is None
    assert se.stats()["total_dropped"] == 1


def test_dispatch_success_after_transient_failure():
    se = _make_engine()
    rm = MagicMock()
    rm.can_execute.return_value = (True, None)
    calls: list[str] = []
    item = _item("tenant-A", "eu-transient", callback=lambda: calls.append("ran"), max_retries=2)
    se.enqueue(item)

    dispatch_results = [RuntimeError("boom"), None]

    def _dispatch(_stub, cb, _ctx):
        result = dispatch_results.pop(0)
        if isinstance(result, Exception):
            raise result
        cb()

    with patch("AINDY.kernel.scheduler_engine.get_resource_manager", return_value=rm), patch(
        "AINDY.core.execution_dispatcher.dispatch",
        side_effect=_dispatch,
    ):
        first = se.schedule()
        retry = se.dequeue_next()
        assert first == 0
        assert retry is not None
        se.enqueue(retry)
        second = se.schedule()

    assert second == 1
    assert calls == ["ran"]
    assert se.stats()["total_dropped"] == 0


def test_dispatch_failure_priority_demoted_to_low():
    se = _make_engine()
    rm = MagicMock()
    rm.can_execute.return_value = (True, None)
    se.enqueue(_item("tenant-A", "eu-high", priority=PRIORITY_HIGH, max_retries=2))

    with patch("AINDY.kernel.scheduler_engine.get_resource_manager", return_value=rm), patch(
        "AINDY.core.execution_dispatcher.dispatch",
        side_effect=RuntimeError("boom"),
    ):
        se.schedule()

    retry = se.dequeue_next()
    assert retry is not None
    assert retry.priority == PRIORITY_LOW
