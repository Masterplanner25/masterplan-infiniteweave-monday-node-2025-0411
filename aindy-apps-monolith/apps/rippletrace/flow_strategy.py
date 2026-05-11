from __future__ import annotations

from AINDY.platform_layer.user_ids import parse_user_id
from apps.rippletrace.strategy import StrategyDB


def select_strategy(context: dict):
    intent_type = str(context.get("flow_type") or context.get("intent_type") or "generic")
    db = context.get("db")
    user_id = context.get("user_id")
    if db is None:
        return None
    owner_user_id = parse_user_id(user_id)
    if owner_user_id:
        user_strategy = (
            db.query(StrategyDB)
            .filter(
                StrategyDB.intent_type == intent_type,
                StrategyDB.user_id == owner_user_id,
            )
            .order_by(StrategyDB.score.desc())
            .first()
        )
        if user_strategy:
            user_strategy.usage_count += 1
            db.commit()
            return user_strategy.flow

    system_strategy = (
        db.query(StrategyDB)
        .filter(
            StrategyDB.intent_type == intent_type,
            StrategyDB.user_id.is_(None),
        )
        .order_by(StrategyDB.score.desc())
        .first()
    )

    if system_strategy:
        system_strategy.usage_count += 1
        db.commit()
        return system_strategy.flow

    return None


def update_strategy_score(
    intent_type: str,
    flow_name: str,
    success: bool,
    db,
    user_id: str | None = None,
) -> None:
    query = db.query(StrategyDB).filter(StrategyDB.intent_type == intent_type)
    owner_user_id = parse_user_id(user_id)
    if owner_user_id:
        query = query.filter(StrategyDB.user_id == owner_user_id)

    strategy = query.order_by(StrategyDB.score.desc()).first()
    if not strategy:
        return

    if success:
        strategy.success_count += 1
        strategy.score = min(2.0, strategy.score + 0.1)
    else:
        strategy.failure_count += 1
        strategy.score = max(0.1, strategy.score - 0.15)

    db.commit()


def register(register_flow_strategy) -> None:
    register_flow_strategy("default", select_strategy)
