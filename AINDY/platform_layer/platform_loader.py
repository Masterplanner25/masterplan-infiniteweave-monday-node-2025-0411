"""
services/platform_loader.py â€” Startup persistence loader for the dynamic platform registry.

Reads all active rows from the three persistence tables and re-registers
them into their respective in-memory registries.  Called once during the
FastAPI lifespan startup, immediately after register_all_flows().

Guarantees
-----------
  Idempotent    â€” safe to call multiple times; already-registered names are
                  skipped, not duplicated or overwritten.
  Non-fatal     â€” individual row failures are logged and skipped; a single
                  bad row cannot prevent other registrations from loading.
  db=None path  â€” all registry functions are called without a db argument so
                  they do NOT attempt a second DB write.

Load order
-----------
  1. Dynamic nodes  â€” must exist in NODE_REGISTRY before flows reference them
  2. Dynamic flows  â€” validated against NODE_REGISTRY at registration time
  3. Webhook subs   â€” independent; loaded last as a convenience
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def load_dynamic_registry(db: Session) -> dict[str, int]:
    """
    Re-register all active dynamic platform registrations from the DB.

    Returns a summary dict:
        {
            "nodes_loaded":  <int>,
            "nodes_skipped": <int>,
            "flows_loaded":  <int>,
            "flows_skipped": <int>,
            "webhooks_loaded":  <int>,
            "webhooks_skipped": <int>,
        }
    """
    stats: dict[str, int] = {
        "nodes_loaded": 0,
        "nodes_skipped": 0,
        "flows_loaded": 0,
        "flows_skipped": 0,
        "webhooks_loaded": 0,
        "webhooks_skipped": 0,
    }

    _load_nodes(db, stats)
    _load_flows(db, stats)
    _load_webhooks(db, stats)

    logger.info(
        "platform_loader: registry restored â€” "
        "nodes=%d/%d flows=%d/%d webhooks=%d/%d",
        stats["nodes_loaded"],
        stats["nodes_loaded"] + stats["nodes_skipped"],
        stats["flows_loaded"],
        stats["flows_loaded"] + stats["flows_skipped"],
        stats["webhooks_loaded"],
        stats["webhooks_loaded"] + stats["webhooks_skipped"],
    )
    return stats


# ---------------------------------------------------------------------------
# Internal loaders
# ---------------------------------------------------------------------------

def _load_nodes(db: Session, stats: dict[str, int]) -> None:
    from AINDY.db.models.dynamic_node import DynamicNode
    from AINDY.runtime.flow_engine import NODE_REGISTRY
    from AINDY.platform_layer.node_registry import register_external_node

    try:
        rows = db.query(DynamicNode).filter(DynamicNode.is_active).all()
    except Exception as exc:
        logger.error("platform_loader: cannot query dynamic_nodes: %s", exc)
        return

    for row in rows:
        if row.name in NODE_REGISTRY:
            logger.debug("platform_loader: node %r already registered â€” skip", row.name)
            stats["nodes_skipped"] += 1
            continue
        try:
            cfg: dict[str, Any] = row.handler_config or {}
            if row.node_type == "webhook":
                handler = cfg.get("url", "")
                timeout = int(cfg.get("timeout_seconds", 10))
            else:
                handler = cfg.get("handler", "")
                timeout = 10

            register_external_node(
                row.name,
                row.node_type,
                handler,
                timeout_seconds=timeout,
                secret=row.secret,
                user_id=row.created_by,
                overwrite=False,
                db=None,   # â† do NOT re-persist; we're reading from DB
            )
            stats["nodes_loaded"] += 1
            logger.debug("platform_loader: node %r restored (type=%s)", row.name, row.node_type)
        except Exception as exc:
            logger.warning(
                "platform_loader: skipping node %r â€” %s", row.name, exc
            )
            stats["nodes_skipped"] += 1


def _load_flows(db: Session, stats: dict[str, int]) -> None:
    from AINDY.db.models.dynamic_flow import DynamicFlow
    from AINDY.runtime.flow_engine import FLOW_REGISTRY
    from AINDY.runtime.flow_registry import register_dynamic_flow

    try:
        rows = db.query(DynamicFlow).filter(DynamicFlow.is_active).all()
    except Exception as exc:
        logger.error("platform_loader: cannot query dynamic_flows: %s", exc)
        return

    for row in rows:
        if row.name in FLOW_REGISTRY:
            logger.debug("platform_loader: flow %r already registered â€” skip", row.name)
            stats["flows_skipped"] += 1
            continue
        try:
            defn: dict[str, Any] = row.definition_json or {}
            register_dynamic_flow(
                row.name,
                nodes=defn.get("nodes", []),
                edges=defn.get("edges", {}),
                start=defn.get("start", ""),
                end=defn.get("end", []),
                user_id=row.created_by,
                overwrite=False,
                db=None,   # â† do NOT re-persist
            )
            stats["flows_loaded"] += 1
            logger.debug("platform_loader: flow %r restored", row.name)
        except Exception as exc:
            logger.warning(
                "platform_loader: skipping flow %r â€” %s", row.name, exc
            )
            stats["flows_skipped"] += 1


def _load_webhooks(db: Session, stats: dict[str, int]) -> None:
    from AINDY.db.models.webhook_subscription import WebhookSubscription as WS
    from AINDY.platform_layer.event_service import _SUBSCRIPTIONS, _load_subscription

    try:
        rows = db.query(WS).filter(WS.is_active).all()
    except Exception as exc:
        logger.error("platform_loader: cannot query webhook_subscriptions: %s", exc)
        return

    for row in rows:
        sub_id = str(row.id)
        if sub_id in _SUBSCRIPTIONS:
            logger.debug("platform_loader: webhook %s already loaded â€” skip", sub_id)
            stats["webhooks_skipped"] += 1
            continue
        try:
            _load_subscription(
                subscription_id=sub_id,
                event_type=row.event_type,
                callback_url=row.callback_url,
                secret=row.secret,
                user_id=row.created_by,
                created_at=row.created_at.isoformat() if row.created_at else "",
            )
            stats["webhooks_loaded"] += 1
            logger.debug(
                "platform_loader: webhook %s restored (event_type=%s)", sub_id, row.event_type
            )
        except Exception as exc:
            logger.warning(
                "platform_loader: skipping webhook %s â€” %s", sub_id, exc
            )
            stats["webhooks_skipped"] += 1

