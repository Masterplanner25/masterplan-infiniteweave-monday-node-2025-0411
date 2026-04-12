from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from AINDY.db.models.memory_metrics import MemoryMetric
from AINDY.runtime.memory.memory_metrics import MemoryMetricsEngine
from AINDY.runtime.memory.metrics_store import MemoryMetricsStore
from AINDY.runtime.memory.types import MemoryContext, MemoryItem


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
    response = client.get("/apps/memory/metrics", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    data = payload.get("data", payload)
    assert "avg_impact_score" in data
    assert "total_runs" in data

    response = client.get("/apps/memory/metrics/detail", headers=auth_headers)
    assert response.status_code == 200
    detail_payload = response.json()
    detail_data = (
        detail_payload["data"]
        if isinstance(detail_payload, dict) and "data" in detail_payload
        else detail_payload
    )
    assert isinstance(detail_data, list)

    response = client.get("/apps/memory/metrics/dashboard", headers=auth_headers)
    assert response.status_code == 200
    dashboard = response.json()
    dashboard_data = dashboard.get("data", dashboard)
    assert "summary" in dashboard_data
    assert "recent_runs" in dashboard_data
    assert "insights" in dashboard_data
