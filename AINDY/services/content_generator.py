import json
from datetime import datetime
from typing import Dict, List

from sqlalchemy.orm import Session

from db.models import PlaybookDB, StrategyDB
from services.playbook_engine import match_playbooks


def _safe_list(value):
    return value if isinstance(value, list) else []


def _build_title(strategy: StrategyDB, themes: List[str]) -> str:
    topic = themes[0].title() if themes else "Narrative"
    tone = strategy.name if strategy else "Strategic Insight"
    return f"Why {topic} Thinking Is the Real Advantage in {tone}"


def _build_hook(themes: List[str]) -> str:
    topic = themes[0] if themes else "this approach"
    return f"Most people are treating {topic} like a checkbox—and it’s costing them leverage."


def _build_body(steps: List[str], platform: str) -> str:
    paragraphs = []
    for step in steps:
        paragraphs.append(f"{step}.")
    if platform.lower() == "linkedin":
        return "\n\n".join(paragraphs)
    return " ".join(paragraphs)


def _build_cta() -> str:
    return "What’s your experience with this approach? Share below."


def _platform_format(platform: str) -> str:
    platform = (platform or "general").lower()
    if platform == "linkedin":
        return "short-paragraphs / conversational / spaced"
    if platform == "medium":
        return "long-form / structured / narrative"
    return "flexible / general purpose"


def generate_content(playbook_id: str, db: Session) -> Dict:
    playbook = db.query(PlaybookDB).filter(PlaybookDB.id == playbook_id).first()
    if not playbook:
        return {
            "status": "playbook_not_found",
            "content": {
                "title": "Strategy in Progress",
                "hook": "We are shaping new narratives.",
                "body": "Stay tuned for the next wave of storytelling.",
                "cta": "What would you like to explore?",
                "platform_format": "general",
            },
        }

    strategy = db.query(StrategyDB).filter(StrategyDB.id == playbook.strategy_id).first()
    conditions = {}
    try:
        conditions = json.loads(strategy.conditions) if strategy and strategy.conditions else {}
    except Exception:
        conditions = {}

    themes = _safe_list(conditions.get("themes"))
    steps = json.loads(playbook.steps) if playbook.steps else []
    platform = conditions.get("platform") or "general"

    content = {
        "title": _build_title(strategy, themes),
        "hook": _build_hook(themes),
        "body": _build_body(steps, platform),
        "cta": _build_cta(),
        "platform_format": _platform_format(platform),
    }
    return {"playbook_id": playbook_id, "content": content, "generated_at": datetime.utcnow().isoformat()}


def generate_content_for_drop(drop_point_id: str, db: Session) -> Dict:
    matches = match_playbooks(drop_point_id, db)
    if not matches:
        return {
            "status": "no_playbook_match",
            "content": None,
        }
    playbook_id = matches[0]["playbook_id"]
    return generate_content(playbook_id, db)


def generate_variations(playbook_id: str, db: Session, count: int = 3) -> Dict:
    base = generate_content(playbook_id, db)
    if base.get("status"):
        return base
    variations = []
    for idx in range(count):
        variation = {
            "title": f"{base['content']['title']} ({idx + 1})",
            "hook": base["content"]["hook"],
            "body": base["content"]["body"],
            "cta": f"{base['content']['cta']} ({idx + 1})",
            "platform_format": base["content"]["platform_format"],
        }
        variations.append(variation)
    return {"playbook_id": playbook_id, "variations": variations, "generated_at": datetime.utcnow().isoformat()}
