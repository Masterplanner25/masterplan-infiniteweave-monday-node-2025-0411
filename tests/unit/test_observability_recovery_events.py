import logging


def test_emit_recovery_failure_increments_prometheus_counter(monkeypatch):
    from AINDY.core.observability_events import emit_recovery_failure

    class _FakeCounter:
        def __init__(self):
            self.calls = []

        def labels(self, **labels):
            self.calls.append(("labels", labels))
            return self

        def inc(self, amount=1):
            self.calls.append(("inc", amount))

    fake_counter = _FakeCounter()
    monkeypatch.setattr(
        "AINDY.platform_layer.metrics.startup_recovery_failure_total",
        fake_counter,
    )

    emit_recovery_failure(
        "test_type",
        ValueError("test error"),
        None,
        logger=logging.getLogger("test"),
    )

    assert ("labels", {"recovery_type": "test_type"}) in fake_counter.calls
    assert ("inc", 1) in fake_counter.calls


def test_emit_recovery_failure_is_noop_when_db_is_none():
    from AINDY.core.observability_events import emit_recovery_failure

    emit_recovery_failure(
        "event_drain",
        RuntimeError("bus error"),
        None,
        logger=logging.getLogger("test"),
    )
