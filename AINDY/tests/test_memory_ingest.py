from __future__ import annotations

from services.memory_ingest_service import MemoryIngestService


class DummyDAO:
    def __init__(self):
        self.created = []

    def save(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "node-1"}

    def create_trace(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "trace-1"}

    def append_node(self, **kwargs):
        self.created.append(kwargs)
        return {"id": "trace-node-1"}


class DummyService(MemoryIngestService):
    def __init__(self):
        self.db = None
        self.user_id = "user-1"
        self.node_dao = DummyDAO()
        self.trace_dao = DummyDAO()


def test_extracts_title_and_date():
    service = DummyService()
    content = "# Title\n\n**Date:** April 17, 2025\n\nBody"
    assert service._extract_title(content) == "Title"
    assert service._extract_date(content) == "April 17, 2025"


def test_build_tags_slug():
    service = DummyService()
    tags = service._build_tags("memoryevents", "The Day I Named the Agent")
    assert "memoryevents" in tags
    assert "symbolic" in tags
    assert "the" in tags
    assert "agent" in tags
