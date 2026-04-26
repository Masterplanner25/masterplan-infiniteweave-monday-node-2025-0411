from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from AINDY.db.mongo_setup import get_mongo_client
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

logger = logging.getLogger(__name__)


def compute_engagement_score(post: dict[str, Any]) -> float:
    impressions = max(1, int(post.get("impressions", 0) or 0))
    clicks = max(0, int(post.get("clicks", 0) or 0))
    likes = max(0, int(post.get("likes", 0) or 0))
    boosts = max(0, int(post.get("boosts", 0) or 0))
    comments = max(0, int(post.get("comments_count", 0) or 0))
    weighted_actions = likes + (boosts * 2) + (comments * 1.5) + (clicks * 0.75)
    return round((weighted_actions / impressions) * 100.0, 3)


def compute_conversion_signal(post: dict[str, Any]) -> float:
    clicks = max(0, int(post.get("clicks", 0) or 0))
    boosts = max(0, int(post.get("boosts", 0) or 0))
    comments = max(0, int(post.get("comments_count", 0) or 0))
    return round(min(1.0, ((clicks * 0.4) + (boosts * 0.35) + (comments * 0.25)) / 10.0), 3)


def summarize_social_performance(*, user_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    try:
        mongo = get_mongo_client()
        if mongo is None:
            logger.warning("MongoDB unavailable for social performance query — returning empty")
            return {"status": "degraded", "data": [], "reason": "mongodb_unavailable"}
        social_db = mongo["aindy_social_layer"]
        posts = social_db["posts"]
        query: dict[str, Any] = {}
        if user_id:
            query["user_id"] = str(user_id)

        docs = list(posts.find(query).sort("created_at", -1).limit(limit))
    except ServerSelectionTimeoutError:
        logger.warning("MongoDB unavailable for social performance query — returning empty")
        return {"status": "degraded", "data": [], "reason": "mongodb_unavailable"}
    except PyMongoError as exc:
        logger.error("MongoDB error in social performance query: %s", exc)
        return {"status": "degraded", "data": [], "reason": str(exc)}

    if not docs:
        return {
            "overview": {
                "post_count": 0,
                "total_impressions": 0,
                "total_clicks": 0,
                "avg_engagement_score": 0.0,
                "avg_conversion_signal": 0.0,
            },
            "top_posts": [],
            "trend": [],
            "signals": [],
        }

    total_impressions = sum(int(doc.get("impressions", 0) or 0) for doc in docs)
    total_clicks = sum(int(doc.get("clicks", 0) or 0) for doc in docs)
    avg_engagement = round(sum(float(doc.get("engagement_score", 0.0) or 0.0) for doc in docs) / len(docs), 3)
    avg_conversion = round(sum(float(doc.get("conversion_signal", 0.0) or 0.0) for doc in docs) / len(docs), 3)

    top_posts = sorted(
        docs,
        key=lambda doc: (float(doc.get("engagement_score", 0.0) or 0.0), int(doc.get("impressions", 0) or 0)),
        reverse=True,
    )[:5]
    return {
        "overview": {
            "post_count": len(docs),
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "avg_engagement_score": avg_engagement,
            "avg_conversion_signal": avg_conversion,
        },
        "top_posts": [
            {
                "id": str(doc.get("id")),
                "content": str(doc.get("content", ""))[:160],
                "engagement_score": float(doc.get("engagement_score", 0.0) or 0.0),
                "conversion_signal": float(doc.get("conversion_signal", 0.0) or 0.0),
                "impressions": int(doc.get("impressions", 0) or 0),
                "clicks": int(doc.get("clicks", 0) or 0),
            }
            for doc in top_posts
        ],
        "trend": _build_trend(docs),
        "signals": _build_social_signals(top_posts, docs),
    }


def get_social_performance_signals(*, user_id: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
    summary = summarize_social_performance(user_id=user_id, limit=50)
    if summary.get("status") == "degraded":
        return []
    return list(summary.get("signals") or [])[:limit]


def _build_trend(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for doc in docs:
        created_at = doc.get("created_at")
        if isinstance(created_at, datetime):
            dt = created_at.astimezone(timezone.utc) if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        else:
            dt = datetime.now(timezone.utc)
        key = dt.strftime("%Y-%m-%d")
        bucket = buckets.setdefault(key, {"date": key, "impressions": 0, "clicks": 0, "engagement_score_total": 0.0, "count": 0})
        bucket["impressions"] += int(doc.get("impressions", 0) or 0)
        bucket["clicks"] += int(doc.get("clicks", 0) or 0)
        bucket["engagement_score_total"] += float(doc.get("engagement_score", 0.0) or 0.0)
        bucket["count"] += 1
    return [
        {
            "date": bucket["date"],
            "impressions": bucket["impressions"],
            "clicks": bucket["clicks"],
            "avg_engagement_score": round(bucket["engagement_score_total"] / max(1, bucket["count"]), 3),
        }
        for bucket in sorted(buckets.values(), key=lambda item: item["date"])[-7:]
    ]


def _build_social_signals(top_posts: list[dict[str, Any]], docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    if top_posts:
        best = top_posts[0]
        signals.append(
            {
                "type": "success",
                "reason": "top_performing_content",
                "engagement_score": float(best.get("engagement_score", 0.0) or 0.0),
                "content": str(best.get("content", ""))[:120],
            }
        )
    low_posts = [
        doc for doc in docs
        if int(doc.get("impressions", 0) or 0) >= 5 and float(doc.get("engagement_score", 0.0) or 0.0) < 3.0
    ]
    if low_posts:
        worst = sorted(low_posts, key=lambda doc: float(doc.get("engagement_score", 0.0) or 0.0))[0]
        signals.append(
            {
                "type": "failure",
                "reason": "low_engagement_content",
                "engagement_score": float(worst.get("engagement_score", 0.0) or 0.0),
                "content": str(worst.get("content", ""))[:120],
            }
        )
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent_high = [
        doc for doc in docs
        if isinstance(doc.get("created_at"), datetime)
        and ((doc["created_at"].astimezone(timezone.utc) if doc["created_at"].tzinfo else doc["created_at"].replace(tzinfo=timezone.utc)) >= recent_cutoff)
        and float(doc.get("engagement_score", 0.0) or 0.0) >= 8.0
    ]
    if len(recent_high) >= 2:
        signals.append(
            {
                "type": "pattern",
                "reason": "repeating_high_engagement_pattern",
                "count": len(recent_high),
                "engagement_score": round(sum(float(doc.get("engagement_score", 0.0) or 0.0) for doc in recent_high) / len(recent_high), 3),
            }
        )
    return signals

