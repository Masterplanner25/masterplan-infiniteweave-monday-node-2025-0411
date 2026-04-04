import json
import importlib
import sys
from datetime import datetime, timedelta
from types import ModuleType

import pytest

aps_module = ModuleType("apscheduler")
aps_sched = ModuleType("apscheduler.schedulers")
aps_bg = ModuleType("apscheduler.schedulers.background")
aps_bg.BackgroundScheduler = type(
    "BackgroundScheduler",
    (),
    {
        "__init__": lambda self, **kwargs: setattr(self, "_jobs", []),
        "add_job": lambda self, *args, **kwargs: self._jobs.append(
            type("Job", (), {"id": kwargs.get("id")})()
        ),
        "remove_job": lambda self, job_id=None, **kwargs: setattr(
            self,
            "_jobs",
            [job for job in self._jobs if getattr(job, "id", None) != job_id],
        ),
        "get_jobs": lambda self: list(getattr(self, "_jobs", [])),
        "start": lambda self, **kwargs: None,
        "shutdown": lambda self, **kwargs: None,
        "running": False,
    },
)
aps_singleton = ModuleType("apscheduler.schedulers.background")
aps_singleton.BackgroundScheduler = aps_bg.BackgroundScheduler
aps_triggers = ModuleType("apscheduler.triggers")
aps_triggers_cron = ModuleType("apscheduler.triggers.cron")
aps_triggers_cron.CronTrigger = type("CronTrigger", (), {"__init__": lambda self, **kwargs: None})
aps_triggers_interval = ModuleType("apscheduler.triggers.interval")
aps_triggers_interval.IntervalTrigger = type("IntervalTrigger", (), {"__init__": lambda self, **kwargs: None})
sys.modules["apscheduler.triggers"] = aps_triggers
sys.modules["apscheduler.triggers.cron"] = aps_triggers_cron
sys.modules["apscheduler.triggers.interval"] = aps_triggers_interval

tenacity_module = ModuleType("tenacity")
tenacity_module.retry = lambda *args, **kwargs: (lambda func: func)
tenacity_module.stop_after_attempt = lambda *args, **kwargs: ("stop_after_attempt", args, kwargs)
tenacity_module.wait_exponential = lambda *args, **kwargs: ("wait_exponential", args, kwargs)
tenacity_module.before_sleep_log = lambda *args, **kwargs: (lambda func, retry_state: None)
sys.modules["tenacity"] = tenacity_module
sys.modules["apscheduler"] = aps_module
sys.modules["apscheduler.schedulers"] = aps_sched
sys.modules["apscheduler.schedulers.background"] = aps_singleton

import main

from db.models import (
    DropPointDB,
    LearningRecordDB,
    LearningThresholdDB,
    PlaybookDB,
    ScoreSnapshotDB,
    StrategyDB,
)
from analytics import (
    causal_engine,
    delta_engine,
    learning_engine,
    playbook_engine,
    prediction_engine,
    recommendation_engine,
)
from domain import content_generator, strategy_engine


class FakeQuery:
    def __init__(self, session, key):
        self.session = session
        self.key = key
        self._limit = None

    def filter(self, *args, **kwargs):
        return self

    def filter_by(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, count):
        self._limit = count
        return self

    def group_by(self, *args, **kwargs):
        return self

    def having(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def all(self):
        data = list(self.session.results.get(self.key, []))
        if self._limit is not None:
            return data[: self._limit]
        return data

    def first(self):
        data = self.all()
        return data[0] if data else None

    def scalar(self):
        scalar_key = f"{self.key}.scalar"
        if scalar_key in self.session.results:
            return self.session.results[scalar_key]
        first = self.first()
        return first

    def __getattr__(self, item):
        def _dummy(*args, **kwargs):
            return self

        return _dummy


class FakeSession:
    def __init__(self, results=None):
        self.results = results or {}
        self.added = []
        self.committed = False

    def query(self, entity):
        key = self._entity_key(entity)
        return FakeQuery(self, key)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        pass

    @staticmethod
    def _entity_key(entity):
        if hasattr(entity, "class_") and hasattr(entity, "key"):
            return f"{entity.class_.__name__}.{entity.key}"
        if hasattr(entity, "__name__"):
            return entity.__name__
        return str(entity)


def make_snapshot(drop_point_id, *, timestamp, narrative, velocity, spread=0.0):
    return ScoreSnapshotDB(
        id=f"snap-{drop_point_id}-{timestamp.timestamp()}",
        drop_point_id=drop_point_id,
        timestamp=timestamp,
        narrative_score=narrative,
        velocity_score=velocity,
        spread_score=spread,
    )


def test_construct_delta_payload_detects_spike_and_momentum():
    now = datetime.utcnow()
    previous = make_snapshot(
        "dp1", timestamp=now - timedelta(minutes=20), narrative=5.0, velocity=1.0, spread=0.5
    )
    latest = make_snapshot(
        "dp1", timestamp=now, narrative=12.0, velocity=3.0, spread=1.5
    )
    payload = delta_engine._construct_delta_payload("dp1", previous, latest)
    assert payload["momentum"] == "accelerating"
    assert payload["signal_spike"]
    assert payload["deltas"]["narrative"] == pytest.approx(7.0, rel=1e-3)
    assert payload["rates"]["velocity_rate"] > 0


def test_compute_deltas_handles_missing_snapshots():
    db = FakeSession({"ScoreSnapshotDB": []})
    payload = delta_engine.compute_deltas("dp-missing", db)
    assert payload["status"] == "no_snapshots"
    db_one = FakeSession({"ScoreSnapshotDB": [make_snapshot("dp1", timestamp=datetime.utcnow(), narrative=1, velocity=1, spread=0)]})
    payload = delta_engine.compute_deltas("dp1", db_one)
    assert payload["status"] == "insufficient_data"


def _build_prediction_db(snapshots, ping_count):
    results = {
        "ScoreSnapshotDB": snapshots,
        "count(pings.id)": [ping_count],
        "count(pings.id).scalar": ping_count,
    }
    return FakeSession(results)


class Thresholds:
    def __init__(
        self,
        velocity_trend=0.1,
        narrative_trend=0.1,
        early_velocity_rate=0.2,
        early_narrative_ceiling=20.0,
    ):
        self.velocity_trend = velocity_trend
        self.narrative_trend = narrative_trend
        self.early_velocity_rate = early_velocity_rate
        self.early_narrative_ceiling = early_narrative_ceiling


def _setup_prediction(
    monkeypatch, snapshots, velocity_rate=0.0, ping_count=1, thresholds=None
):
    prediction_engine.HIGH_PING_THRESHOLD = 3
    db = _build_prediction_db(snapshots, ping_count)
    delta_payload = {"rates": {"velocity_rate": velocity_rate}, "delta_minutes": 5}
    monkeypatch.setattr(prediction_engine, "compute_deltas", lambda *_: delta_payload)
    threshold_record = thresholds or Thresholds()
    monkeypatch.setattr(prediction_engine, "get_learning_thresholds", lambda *_: threshold_record)
    monkeypatch.setattr(prediction_engine, "record_prediction", lambda *args, **kwargs: None)
    return db


def test_predict_drop_point_likely_to_spike(monkeypatch):
    now = datetime.utcnow()
    snapshots = [
        make_snapshot("dp1", timestamp=now, narrative=30.0, velocity=5.0),
        make_snapshot("dp1", timestamp=now - timedelta(minutes=10), narrative=20.0, velocity=3.0),
        make_snapshot("dp1", timestamp=now - timedelta(minutes=20), narrative=10.0, velocity=1.0),
    ]
    db = _setup_prediction(
        monkeypatch,
        snapshots,
        velocity_rate=0.3,
        thresholds=Thresholds(velocity_trend=0.1, narrative_trend=0.1),
    )
    result = prediction_engine.predict_drop_point("dp1", db, record_learning=False)
    assert result["prediction"] == "likely_to_spike"


def test_predict_drop_point_emerging_signal(monkeypatch):
    now = datetime.utcnow()
    snapshots = [
        make_snapshot("dp2", timestamp=now, narrative=12.0, velocity=2.0),
        make_snapshot("dp2", timestamp=now - timedelta(minutes=10), narrative=11.0, velocity=2.0),
        make_snapshot("dp2", timestamp=now - timedelta(minutes=20), narrative=10.5, velocity=2.0),
    ]
    db = _setup_prediction(
        monkeypatch,
        snapshots,
        velocity_rate=0.5,
        thresholds=Thresholds(velocity_trend=1.0, narrative_trend=1.0, early_velocity_rate=0.1),
    )
    result = prediction_engine.predict_drop_point("dp2", db, record_learning=False)
    assert result["prediction"] == "emerging_signal"


def test_predict_drop_point_plateauing(monkeypatch):
    now = datetime.utcnow()
    snapshots = [
        make_snapshot("dp3", timestamp=now, narrative=25.0, velocity=1.0),
        make_snapshot("dp3", timestamp=now - timedelta(minutes=10), narrative=25.5, velocity=2.0),
        make_snapshot("dp3", timestamp=now - timedelta(minutes=20), narrative=26.0, velocity=2.5),
    ]
    db = _setup_prediction(
        monkeypatch,
        snapshots,
        velocity_rate=0.1,
        ping_count=5,
        thresholds=Thresholds(velocity_trend=1.0, narrative_trend=1.0, early_velocity_rate=2.0),
    )
    result = prediction_engine.predict_drop_point("dp3", db, record_learning=False)
    assert result["prediction"] == "plateauing"


def test_predict_drop_point_declining(monkeypatch):
    now = datetime.utcnow()
    snapshots = [
        make_snapshot("dp4", timestamp=now, narrative=40.0, velocity=1.0),
        make_snapshot("dp4", timestamp=now - timedelta(minutes=10), narrative=42.0, velocity=1.5),
        make_snapshot("dp4", timestamp=now - timedelta(minutes=20), narrative=45.0, velocity=2.0),
    ]
    db = _setup_prediction(
        monkeypatch,
        snapshots,
        velocity_rate=-0.5,
        thresholds=Thresholds(velocity_trend=5.0, narrative_trend=5.0, early_velocity_rate=1.0),
    )
    result = prediction_engine.predict_drop_point("dp4", db, record_learning=False)
    assert result["prediction"] == "declining"


@pytest.mark.parametrize(
    "prediction,action",
    [
        ("likely_to_spike", "amplify"),
        ("emerging_signal", "nurture"),
        ("plateauing", "revive"),
        ("declining", "archive_or_replace"),
    ],
)
def test_recommendation_actions(monkeypatch, prediction, action):
    monkeypatch.setattr(
        recommendation_engine,
        "compute_deltas",
        lambda *_: {"rates": {"velocity_rate": 0.2}, "delta_minutes": 1},
    )
    monkeypatch.setattr(
        recommendation_engine,
        "_latest_snapshot",
        lambda *_: ScoreSnapshotDB(
            id="snap-latest",
            drop_point_id="dp",
            timestamp=datetime.utcnow(),
            narrative_score=10.0,
            velocity_score=1.0,
            spread_score=0.5,
        ),
    )
    def fake_prediction(*args, **kwargs):
        return {"prediction": prediction, "confidence": 0.7}

    monkeypatch.setattr(prediction_engine, "predict_drop_point", fake_prediction)
    monkeypatch.setattr(recommendation_engine, "predict_drop_point", fake_prediction)
    db = FakeSession({"ScoreSnapshotDB": []})
    result = recommendation_engine.recommend_for_drop_point("dp", db, log_prediction=False)
    assert result["action"] == action


def test_causal_graph_respects_temporal_order(monkeypatch):
    now = datetime.utcnow()
    drop_a = DropPointDB(
        id="a",
        date_dropped=now - timedelta(days=2),
        core_themes="ai,vision",
        tagged_entities="team",
        platform="linkedin",
    )
    drop_b = DropPointDB(
        id="b",
        date_dropped=now,
        core_themes="ai,vision",
        tagged_entities="team",
        platform="twitter",
    )
    db = FakeSession({"DropPointDB": [drop_a, drop_b]})
    nodes = [
        {"id": "a", "title": "A", "platform": "linkedin", "narrative_score": 10, "date_dropped": drop_a.date_dropped.isoformat()},
        {"id": "b", "title": "B", "platform": "twitter", "narrative_score": 12, "date_dropped": drop_b.date_dropped.isoformat()},
    ]
    monkeypatch.setattr(
        causal_engine,
        "build_influence_graph",
        lambda _db: {"nodes": nodes, "edges": []},
    )
    monkeypatch.setattr(
        causal_engine,
        "compute_deltas",
        lambda *_: {"rates": {"velocity_rate": 0.5}},
    )
    graph = causal_engine.build_causal_graph(db)
    assert any(edge["source"] == "a" and edge["target"] == "b" for edge in graph["causal_edges"])
    assert all(edge["confidence"] > 0.3 for edge in graph["causal_edges"])


def test_strategy_build_synthesizes_patterns():
    now = datetime.utcnow()
    drops = [
        DropPointDB(
            id="dp1",
            narrative_score=20.0,
            date_dropped=now - timedelta(days=3),
            core_themes="ai,framework",
            tagged_entities="vision",
            platform="linkedin",
        ),
        DropPointDB(
            id="dp2",
            narrative_score=22.0,
            date_dropped=now - timedelta(days=2),
            core_themes="ai,design",
            tagged_entities="vision",
            platform="linkedin",
        ),
        DropPointDB(
            id="dp3",
            narrative_score=25.0,
            date_dropped=now - timedelta(days=1),
            core_themes="ai,framework",
            tagged_entities="insight",
            platform="linkedin",
        ),
    ]
    learning_rows = [("dp3",)]
    db = FakeSession(
        {
            "DropPointDB": drops,
            "LearningRecordDB.drop_point_id": learning_rows,
        }
    )
    created = strategy_engine.build_strategies(db)
    assert any("Momentum" in strat["name"] for strat in created)
    assert any("Influence" in strat["name"] for strat in created)


def test_playbook_build_creates_steps():
    strategy = StrategyDB(
        id="strategy-1",
        name="AI Play",
        pattern_description="desc",
        conditions=json.dumps({"themes": ["ai"], "platform": "linkedin", "timing": "within 24h"}),
        success_rate=0.9,
        usage_count=1,
    )
    db = FakeSession(
        {
            "StrategyDB": [strategy],
            "PlaybookDB": [],
        }
    )
    result = playbook_engine.build_playbook("strategy-1", db)
    assert result["title"] == "AI Play Playbook"
    assert len(result["steps"]) == 5
    assert result["template"]


def test_list_playbooks_returns_serialized():
    playbook = PlaybookDB(
        id="pb-1",
        strategy_id="strategy-1",
        title="Title",
        steps=json.dumps(["step1"]),
        template="tmpl",
        success_rate=0.5,
        created_at=datetime.utcnow(),
    )
    db = FakeSession({"PlaybookDB": [playbook]})
    listed = playbook_engine.list_playbooks(db)
    assert listed[0]["steps"] == ["step1"]
    assert listed[0]["template"] == "tmpl"


def test_content_generator_returns_structured_content():
    strategy = StrategyDB(
        id="strategy-1",
        name="AI Strategy",
        pattern_description="desc",
        conditions=json.dumps({"themes": ["ai"], "platform": "LinkedIn", "timing": "within 24h"}),
        success_rate=0.8,
    )
    playbook = PlaybookDB(
        id="play-1",
        strategy_id="strategy-1",
        title="Template",
        steps=json.dumps(["step1", "step2"]),
        template="tmpl",
        success_rate=0.8,
        created_at=datetime.utcnow(),
    )
    db = FakeSession({"PlaybookDB": [playbook], "StrategyDB": [strategy]})
    result = content_generator.generate_content("play-1", db)
    content = result["content"]
    assert {"title", "hook", "body", "cta", "platform_format"} <= set(content.keys())


def test_content_generator_fallback():
    db = FakeSession({"PlaybookDB": [], "StrategyDB": []})
    result = content_generator.generate_content("missing", db)
    assert result["status"] == "playbook_not_found"
    assert "content" in result


def test_learning_engine_records_and_evaluates(monkeypatch):
    db = FakeSession({"LearningRecordDB": [], "ScoreSnapshotDB": []})
    prediction = learning_engine.record_prediction(
        db, "dp", "likely_to_spike", velocity_at_prediction=1.0, narrative_at_prediction=2.0
    )
    assert isinstance(prediction, LearningRecordDB)
    record = LearningRecordDB(
        id="lr-1",
        drop_point_id="dp",
        prediction="likely_to_spike",
        predicted_at=datetime.utcnow() - timedelta(minutes=5),
        velocity_at_prediction=1.0,
        narrative_at_prediction=2.0,
    )
    db = FakeSession(
        {
            "LearningRecordDB": [record],
            "ScoreSnapshotDB": [
                make_snapshot("dp", timestamp=datetime.utcnow(), narrative=10.0, velocity=0.5)
            ],
        }
    )
    result = learning_engine.evaluate_outcome("dp", db)
    assert result["actual_outcome"] in {"spiked", "declined", "stable"}


def test_learning_engine_adjust_thresholds(monkeypatch):
    records = []
    for idx in range(3):
        rec = LearningRecordDB(
            id=f"lr{idx}",
            drop_point_id="dp",
            prediction="likely_to_spike" if idx == 0 else "emerging_signal",
            actual_outcome="declined" if idx == 0 else "spiked",
            predicted_at=datetime.utcnow() - timedelta(minutes=idx + 1),
            was_correct=False if idx == 0 else True,
            velocity_at_prediction=1.0,
            narrative_at_prediction=1.0,
        )
        records.append(rec)
    db = FakeSession({"LearningRecordDB": records})
    threshold = LearningThresholdDB(
        id="thr-1",
        velocity_trend=0.5,
        narrative_trend=1.0,
        early_velocity_rate=0.2,
        early_narrative_ceiling=15.0,
    )
    monkeypatch.setattr(learning_engine, "get_learning_thresholds", lambda *_: threshold)
    summary = learning_engine.adjust_thresholds(db)
    assert "thresholds" in summary
    assert summary["false_negatives"] >= 0


def test_learning_engine_stats_reports_rates():
    records = [
        LearningRecordDB(
            id="lr1",
            drop_point_id="dp",
            prediction="likely_to_spike",
            actual_outcome="spiked",
            was_correct=True,
        ),
        LearningRecordDB(
            id="lr2",
            drop_point_id="dp",
            prediction="likely_to_spike",
            actual_outcome="declined",
            was_correct=False,
        ),
    ]
    db = FakeSession({"LearningRecordDB": records})
    stats = learning_engine.learning_stats(db)
    assert stats["total_predictions"] == 2
    assert stats["accuracy"] <= 1.0


@pytest.mark.parametrize(
    "endpoint,patches",
    [
        (
            "/dashboard",
            [
                ("get_dashboard_snapshot", lambda db: {"overview": {"foo": "bar"}}),
                ("find_momentum_leaders", lambda db: {"fastest_accelerating": None, "biggest_spike": None}),
                ("scan_drop_point_predictions", lambda db, limit=20: []),
                ("recommendations_summary", lambda db, limit=10: {"high_priority_actions": [], "medium_priority_actions": [], "low_priority_actions": []}),
            ],
        ),
        ("/ripple_deltas/fake", [("compute_deltas", lambda drop_point_id, db: {"drop_point_id": drop_point_id, "rates": {"velocity_rate": 0.1}})]),
        ("/predict/fake", [("predict_drop_point", lambda drop_point_id, db: {"drop_point_id": drop_point_id, "prediction": "stable"})]),
        ("/recommend/fake", [("recommend_for_drop_point", lambda drop_point_id, db: {"drop_point_id": drop_point_id, "action": "monitor", "priority": "low"})]),
        ("/influence_graph", [("build_influence_graph", lambda db: {"nodes": [], "edges": []})]),
        ("/causal_graph", [("build_causal_graph", lambda db: {"nodes": [], "causal_edges": []})]),
        ("/narrative/fake", [("generate_narrative", lambda drop_point_id, db: {"drop_point_id": drop_point_id, "timeline": []})]),
        ("/strategies", [("build_strategies", lambda db: []), ("list_strategies", lambda db: [])]),
        ("/playbooks", [("list_playbooks", lambda db: [])]),
        ("/generate_content/play-1", [("generate_content", lambda playbook_id, db: {"playbook_id": playbook_id, "content": {}})]),
    ],
)
def test_endpoints_return_success(client, monkeypatch, endpoint, patches, api_key_headers):
    legacy_surface_module = importlib.import_module("routes.legacy_surface_router")
    for attr_name, fn in patches:
        monkeypatch.setattr(legacy_surface_module, attr_name, fn)
    response = client.get(endpoint, headers=api_key_headers)
    assert response.status_code == 200
