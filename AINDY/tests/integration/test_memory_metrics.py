from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models.memory_metrics import MemoryMetric
from runtime.memory.memory_metrics import MemoryMetricsEngine
from runtime.memory.metrics_store import MemoryMetricsStore
from runtime.memory.types import MemoryContext, MemoryItem


def test_metrics_engine_quality_scores():
    engine = MemoryMetricsEngine()
    strong = "Strategy plan:\n1. Analyze\n2. Recommend\nSummary: success"
    weak = "error"

    strong_score = engine.evaluate_quality(strong)
    weak_score = engine.evaluate_quality(weak)

    assert 0 <= strong_score <= 1
    assert 0 <= weak_score <= 1
    assert strong_score > weak_score


def test_compute_impact_with_context():
    engine = MemoryMetricsEngine()
    context = MemoryContext(
        items=[
            MemoryItem(
                id="1",
                content="prior outcome",
                node_type="outcome",
                similarity=0.8,
            )
        ],
        total_tokens=10,
    )

    impact = engine.compute_impact("baseline", "improved\nsummary", context)
    assert impact > 0


def test_metrics_store_record_and_summary():
    engine = create_engine("sqlite:///:memory:")
    MemoryMetric.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    user_id = "00000000-0000-0000-0000-000000000001"

    store = MemoryMetricsStore()
    store.record(
        user_id=user_id,
        task_type="analysis",
        impact_score=0.5,
        memory_count=3,
        avg_similarity=0.7,
        db=db,
    )

    summary = store.get_summary(user_id=user_id, db=db)
    assert summary["total_runs"] == 1
    assert summary["avg_impact_score"] > 0
    assert summary["positive_impact_rate"] == 1.0

    recent = store.get_recent(user_id=user_id, db=db, limit=5)
    assert len(recent) == 1
    assert recent[0]["memory_count"] == 3


def test_memory_metrics_api_endpoints(client, auth_headers):
    response = client.get("/memory/metrics", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert "avg_impact_score" in payload
    assert "total_runs" in payload

    response = client.get("/memory/metrics/detail", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    response = client.get("/memory/metrics/dashboard", headers=auth_headers)
    assert response.status_code == 200
    dashboard = response.json()
    assert "summary" in dashboard
    assert "recent_runs" in dashboard
    assert "insights" in dashboard
