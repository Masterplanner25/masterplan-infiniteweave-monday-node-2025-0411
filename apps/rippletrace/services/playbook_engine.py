import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from apps.rippletrace.models import PlaybookDB, StrategyDB
from apps.rippletrace.services.strategy_engine import match_strategies, get_strategy

DEFAULT_TEMPLATE = (
    "Title: [Topic] — [Insight]\n\n"
    "Body:\n"
    "- Key idea:\n"
    "- Framework or breakdown:\n"
    "- Authority statement:\n\n"
    "Call to action:\n"
    "- Invite discussion or response\n"
)


def _extract_conditions(strategy: StrategyDB) -> dict:
    try:
        return json.loads(strategy.conditions or "{}")
    except json.JSONDecodeError:
        return {}


def build_playbook(strategy_id: str, db: Session) -> dict:
    strategy = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()
    if not strategy:
        return {
            "status": "strategy_not_found",
            "playbook": None,
        }

    conditions = _extract_conditions(strategy)
    themes = ", ".join(conditions.get("themes", [])) or "focused topics"
    entities = ", ".join(conditions.get("entities", [])) or "key players"
    platform = conditions.get("platform", "the primary platform")
    timing = conditions.get("timing", "consistent cadence")

    steps = [
        f"Create content focused on {themes}",
        f"Include references to {entities}",
        f"Publish on {platform}",
        f"Post follow-up within {timing}",
        "Engage early responses and capture signals",
    ]

    template = DEFAULT_TEMPLATE.replace("[Topic]", themes.title()).replace(
        "[Insight]", f"Leverage {platform}"
    )
    title = f"{strategy.name} Playbook"

    playbook = (
        db.query(PlaybookDB)
        .filter(PlaybookDB.strategy_id == strategy_id)
        .first()
    )
    if playbook:
        playbook.title = title
        playbook.steps = json.dumps(steps)
        playbook.template = template
        playbook.success_rate = strategy.success_rate or 0.0
        playbook.created_at = datetime.utcnow()
    else:
        playbook = PlaybookDB(
            id=str(uuid.uuid4()),
            strategy_id=strategy_id,
            title=title,
            steps=json.dumps(steps),
            template=template,
            success_rate=strategy.success_rate or 0.0,
            created_at=datetime.utcnow(),
        )
        db.add(playbook)
    db.commit()
    db.refresh(playbook)
    return {
        "id": playbook.id,
        "strategy_id": strategy_id,
        "title": playbook.title,
        "steps": json.loads(playbook.steps),
        "template": playbook.template,
        "success_rate": playbook.success_rate,
        "created_at": playbook.created_at.isoformat()
        if playbook.created_at
        else None,
    }


def list_playbooks(db: Session) -> list[dict]:
    playbooks = db.query(PlaybookDB).all()
    result = []
    for play in playbooks:
        result.append(
            {
                "id": play.id,
                "strategy_id": play.strategy_id,
                "title": play.title,
                "steps": json.loads(play.steps or "[]"),
                "template": play.template,
                "success_rate": play.success_rate,
                "created_at": play.created_at.isoformat()
                if play.created_at
                else None,
            }
        )
    return result


def get_playbook(playbook_id: str, db: Session) -> dict | None:
    playbook = (
        db.query(PlaybookDB).filter(PlaybookDB.id == playbook_id).first()
    )
    if not playbook:
        return None
    return {
        "id": playbook.id,
        "strategy_id": playbook.strategy_id,
        "title": playbook.title,
        "steps": json.loads(playbook.steps or "[]"),
        "template": playbook.template,
        "success_rate": playbook.success_rate,
        "created_at": playbook.created_at.isoformat()
        if playbook.created_at
        else None,
    }


def match_playbooks(drop_point_id: str, db: Session) -> list[dict]:
    strategy_matches = match_strategies(drop_point_id, db)
    matched = []
    for match in strategy_matches:
        playbook = (
            db.query(PlaybookDB)
            .filter(PlaybookDB.strategy_id == match["strategy_id"])
            .first()
        )
        if playbook:
            matched.append(
                {
                    "strategy_id": match["strategy_id"],
                    "playbook_id": playbook.id,
                    "name": playbook.title,
                    "confidence": match["confidence"],
                    "score": match["score"],
                }
            )
    return matched

