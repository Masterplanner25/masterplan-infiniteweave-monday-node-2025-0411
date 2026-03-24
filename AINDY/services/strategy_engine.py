import json
import uuid
from collections import Counter
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from db.models import (
    StrategyDB,
    DropPointDB,
    LearningRecordDB,
)

SUCCESS_NARRATIVE_THRESHOLD = 15.0
MIN_SUCCESSFUL_DROPS = 3


def _split_terms(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [term.strip().lower() for term in value.split(",") if term.strip()]


def get_successful_drops(db: Session) -> List[Dict]:
    narrative_success = (
        db.query(DropPointDB)
        .filter(DropPointDB.narrative_score >= SUCCESS_NARRATIVE_THRESHOLD)
        .all()
    )
    spiked_ids = (
        db.query(LearningRecordDB.drop_point_id)
        .filter(LearningRecordDB.actual_outcome == "spiked")
        .distinct()
        .all()
    )
    spiked_set = {row[0] for row in spiked_ids if row[0]}

    unique_ids = {dp.id for dp in narrative_success}
    unique_ids.update(spiked_set)

    results = []
    drops = (
        db.query(DropPointDB)
        .filter(DropPointDB.id.in_(list(unique_ids)))
        .order_by(DropPointDB.date_dropped.asc())
        .all()
    )
    for dp in drops:
        success = {
            "id": dp.id,
            "themes": _split_terms(dp.core_themes),
            "entities": _split_terms(dp.tagged_entities),
            "platform": dp.platform or "unknown",
            "narrative_score": dp.narrative_score or 0.0,
            "date": dp.date_dropped,
        }
        results.append(success)
    return results


def build_strategies(db: Session) -> List[Dict]:
    successful = get_successful_drops(db)
    if len(successful) < MIN_SUCCESSFUL_DROPS:
        return []

    theme_counter = Counter()
    entity_counter = Counter()
    platform_counter = Counter()
    narratives = []
    date_diffs = []
    last_date = None
    for drop in successful:
        theme_counter.update(drop["themes"])
        entity_counter.update(drop["entities"])
        platform_counter.update([drop["platform"]])
        narratives.append(drop["narrative_score"])
        if last_date and drop["date"]:
            diff = drop["date"] - last_date
            date_diffs.append(diff.days or 0)
        last_date = drop["date"]

    avg_narrative = sum(narratives) / len(narratives) if narratives else 0
    avg_delta_days = sum(date_diffs) / len(date_diffs) if date_diffs else 0
    timing_pattern = (
        f"within {round(avg_delta_days,1)} day(s)"
        if avg_delta_days
        else "varied timing"
    )

    top_platform = platform_counter.most_common(1)
    platform_value = top_platform[0][0] if top_platform else "varied"

    existing = {strategy.name: strategy for strategy in db.query(StrategyDB).all()}
    created: List[Dict] = []
    for theme, count in theme_counter.most_common(3):
        if not theme:
            continue
        conditions = {
            "themes": [theme],
            "platform": platform_value,
            "timing": timing_pattern,
            "avg_narrative": round(avg_narrative, 2),
        }
        name = f"{theme.title()} Momentum Play"
        pattern_description = (
            f"Combine {theme} focus with platform {platform_value} {timing_pattern}."
        )
        success_rate = round(count / len(successful), 3)
        strategy = existing.get(name)
        if strategy:
            strategy.pattern_description = pattern_description
            strategy.conditions = json.dumps(conditions)
            strategy.success_rate = success_rate
            strategy.usage_count = (strategy.usage_count or 0) + 1
        else:
            strategy = StrategyDB(
                id=str(uuid.uuid4()),
                name=name,
                pattern_description=pattern_description,
                conditions=json.dumps(conditions),
                success_rate=success_rate,
                usage_count=1,
                created_at=datetime.utcnow(),
            )
        db.add(strategy)
        created.append(
            {
                "name": name,
                "conditions": conditions,
                "success_rate": success_rate,
            }
        )
        existing[name] = strategy

    for entity, count in entity_counter.most_common(2):
        if not entity:
            continue
        conditions = {
            "entities": [entity],
            "platform": platform_value,
            "timing": timing_pattern,
            "avg_narrative": round(avg_narrative, 2),
        }
        name = f"{entity.title()} Influence Spike"
        pattern_description = (
            f"Leverage {entity} signaled content on {platform_value} {timing_pattern}."
        )
        success_rate = round(count / len(successful), 3)
        strategy = existing.get(name)
        if strategy:
            strategy.pattern_description = pattern_description
            strategy.conditions = json.dumps(conditions)
            strategy.success_rate = success_rate
            strategy.usage_count = (strategy.usage_count or 0) + 1
        else:
            strategy = StrategyDB(
                id=str(uuid.uuid4()),
                name=name,
                pattern_description=pattern_description,
                conditions=json.dumps(conditions),
                success_rate=success_rate,
                usage_count=1,
                created_at=datetime.utcnow(),
            )
        db.add(strategy)
        created.append(
            {
                "name": name,
                "conditions": conditions,
                "success_rate": success_rate,
            }
        )
        existing[name] = strategy
    db.commit()
    return created


def _strategy_score(strategy: StrategyDB) -> float:
    try:
        cond = json.loads(strategy.conditions or "{}")
    except json.JSONDecodeError:
        cond = {}
    avg_narrative = cond.get("avg_narrative", 0.0)
    success_rate = strategy.success_rate or 0.0
    usage_factor = min(1.0, (strategy.usage_count or 0) / 10)
    narrative_factor = min(1.0, avg_narrative / 50)
    score = success_rate * 0.5 + usage_factor * 0.3 + narrative_factor * 0.2
    return round(score, 3)


def list_strategies(db: Session) -> List[Dict]:
    strategies = db.query(StrategyDB).all()
    decorated = []
    for strategy in strategies:
        decorated.append(
            {
                "id": strategy.id,
                "name": strategy.name,
                "pattern_description": strategy.pattern_description,
                "conditions": json.loads(strategy.conditions or "{}"),
                "success_rate": strategy.success_rate,
                "usage_count": strategy.usage_count,
                "created_at": strategy.created_at.isoformat()
                if strategy.created_at
                else None,
                "score": _strategy_score(strategy),
            }
        )
    return sorted(decorated, key=lambda s: s["score"], reverse=True)


def get_strategy(strategy_id: str, db: Session) -> Optional[Dict]:
    strategy = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()
    if not strategy:
        return None
    return {
        "id": strategy.id,
        "name": strategy.name,
        "pattern_description": strategy.pattern_description,
        "conditions": json.loads(strategy.conditions or "{}"),
        "success_rate": strategy.success_rate,
        "usage_count": strategy.usage_count,
        "score": _strategy_score(strategy),
        "created_at": strategy.created_at.isoformat()
        if strategy.created_at
        else None,
    }


def match_strategies(drop_point_id: str, db: Session) -> List[Dict]:
    drop = db.query(DropPointDB).filter(DropPointDB.id == drop_point_id).first()
    if not drop:
        return []
    drop_themes = set(_split_terms(drop.core_themes))
    drop_entities = set(_split_terms(drop.tagged_entities))
    drop_platform = drop.platform or "unknown"
    strategies = list_strategies(db)
    matches = []
    for strategy in strategies:
        cond = strategy["conditions"]
        criteria = 0
        hits = 0
        if cond.get("themes"):
            criteria += len(cond["themes"])
            hits += len(set(cond["themes"]) & drop_themes)
        if cond.get("entities"):
            criteria += len(cond["entities"])
            hits += len(set(cond["entities"]) & drop_entities)
        if cond.get("platform"):
            criteria += 1
            if cond["platform"] == drop_platform:
                hits += 1
        confidence = round(min(1.0, hits / criteria), 3) if criteria else 0.0
        if confidence:
            matches.append(
                {
                    "strategy_id": strategy["id"],
                    "name": strategy["name"],
                    "confidence": confidence,
                    "score": strategy["score"],
                }
            )
    return sorted(matches, key=lambda m: (m["confidence"], m["score"]), reverse=True)
