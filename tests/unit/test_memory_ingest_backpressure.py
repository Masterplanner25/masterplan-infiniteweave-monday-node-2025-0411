from __future__ import annotations

import threading
from pathlib import Path

from AINDY.memory.ingest_queue import MemoryIngestQueue
from AINDY.memory.memory_ingest_service import MemoryIngestService


class _LightweightMemoryIngestService(MemoryIngestService):
    def __init__(self, user_id: str = "user-1"):
        self.db = None
        self.user_id = user_id
        self.node_dao = None
        self.trace_dao = None


def test_memory_ingest_queue_accepts_writes_below_capacity():
    ingest_queue = MemoryIngestQueue(maxsize=2)

    assert ingest_queue.enqueue({"path": "a.md"}) is True
    assert ingest_queue.snapshot()["depth"] == 1
    assert ingest_queue.snapshot()["capacity"] == 2


def test_memory_ingest_queue_rejects_writes_at_capacity():
    ingest_queue = MemoryIngestQueue(maxsize=1)

    assert ingest_queue.enqueue({"path": "a.md"}) is True
    assert ingest_queue.enqueue({"path": "b.md"}) is False
    assert ingest_queue.snapshot()["depth"] == 1


def test_memory_ingest_service_does_not_raise_when_queue_is_full(monkeypatch, tmp_path: Path):
    class FullQueue:
        def enqueue(self, _payload):
            return False

    monkeypatch.setattr(
        "AINDY.memory.memory_ingest_service.configure_memory_ingest_queue",
        lambda: FullQueue(),
    )
    path = tmp_path / "memory.md"
    path.write_text("# Title\n\nBody", encoding="utf-8")

    service = _LightweightMemoryIngestService()

    results = service.ingest_paths([path])

    assert len(results) == 1
    assert results[0].status == "dropped"
    assert results[0].message == "memory ingest queue full"


def test_memory_ingest_queue_dropped_counter_increments_on_each_rejected_write(monkeypatch):
    increments: list[int] = []

    monkeypatch.setattr(
        "AINDY.memory.ingest_queue._increment_drop_metrics",
        lambda: increments.append(1),
    )
    ingest_queue = MemoryIngestQueue(maxsize=1)

    assert ingest_queue.enqueue({"path": "a.md"}) is True
    assert ingest_queue.enqueue({"path": "b.md"}) is False
    assert ingest_queue.enqueue({"path": "c.md"}) is False

    assert ingest_queue.snapshot()["dropped_total"] == 2
    assert len(increments) == 2


def test_memory_ingest_queue_worker_processes_enqueued_items():
    processed: list[dict] = []
    processed_event = threading.Event()

    def _handler(payload):
        processed.append(payload)
        processed_event.set()

    ingest_queue = MemoryIngestQueue(
        maxsize=2,
        worker_handler=_handler,
        poll_interval=0.05,
    )
    ingest_queue.start()
    try:
        assert ingest_queue.enqueue({"path": "a.md", "user_id": "user-1"}) is True
        assert processed_event.wait(1.0), "queue worker did not process payload in time"
        assert processed == [{"path": "a.md", "user_id": "user-1"}]
        assert ingest_queue.snapshot()["depth"] == 0
    finally:
        ingest_queue.stop(timeout=1.0, drain=True)
