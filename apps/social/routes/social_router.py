from datetime import datetime, timezone
import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from pymongo.database import Database
from sqlalchemy.orm import Session

from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.db.mongo_setup import get_mongo_db
from AINDY.platform_layer.app_runtime import execute_with_pipeline_sync
from AINDY.services.auth_service import get_current_user
from apps.social.models.social_models import FeedItem, SocialPost, SocialProfile, TrustTier
from apps.social.services.social_performance_service import (
    compute_conversion_signal,
    compute_engagement_score,
    summarize_social_performance,
)

router = APIRouter(prefix="/social", tags=["Social Layer"], dependencies=[Depends(get_current_user)])


class SocialInteractionRequest(BaseModel):
    action: str
    amount: int = 1


TRUST_TIER_WEIGHTS = {
    TrustTier.INNER_CIRCLE: 2.0,
    TrustTier.COLLAB: 1.5,
    TrustTier.OBSERVER: 1.0,
    TrustTier.SYSTEM: 1.2,
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _compute_visibility_score(post: SocialPost) -> float:
    trust_weight = TRUST_TIER_WEIGHTS.get(post.trust_tier_required, 1.0)
    engagement_total = max(post.likes, 0) + max(post.boosts, 0) * 2 + max(post.comments_count, 0)
    engagement_score = math.log1p(engagement_total) / 5.0
    return trust_weight * (1.0 + min(engagement_score, 1.0))


def _refresh_post_metrics(post_doc: dict) -> dict:
    post_doc["engagement_score"] = compute_engagement_score(post_doc)
    post_doc["conversion_signal"] = compute_conversion_signal(post_doc)
    return post_doc


def _build_social_performance_memory_hint(
    *,
    user_id: str,
    post_doc: dict,
    signal_type: str,
    reason: str,
) -> dict:
    return {
        "event_type": "social_performance",
        "content": f"Social performance {signal_type}: {str(post_doc.get('content', ''))[:160]}",
        "source": "social_router",
        "tags": ["social", "performance", signal_type],
        "node_type": "insight" if signal_type == "high" else "failure",
        "force": True,
        "user_id": user_id,
        "agent_namespace": "social",
        "extra": {
            "post_id": str(post_doc.get("id")),
            "engagement_score": float(post_doc.get("engagement_score", 0.0) or 0.0),
            "conversion_signal": float(post_doc.get("conversion_signal", 0.0) or 0.0),
            "impressions": int(post_doc.get("impressions", 0) or 0),
            "clicks": int(post_doc.get("clicks", 0) or 0),
            "reason": reason,
        },
    }


def _maybe_capture_performance_signal(
    *,
    db: Database,
    user_id: str,
    post_doc: dict,
) -> tuple[dict, list[dict]]:
    refreshed = _refresh_post_metrics(dict(post_doc))
    db["posts"].update_one(
        {"id": refreshed["id"]},
        {
            "$set": {
                "engagement_score": refreshed["engagement_score"],
                "conversion_signal": refreshed["conversion_signal"],
            }
        },
    )
    hints: list[dict] = []
    if refreshed["impressions"] >= 10 and refreshed["engagement_score"] >= 8.0:
        hints.append(
            _build_social_performance_memory_hint(
                user_id=user_id,
                post_doc=refreshed,
                signal_type="high",
                reason="high_engagement",
            )
        )
    elif refreshed["impressions"] >= 10 and refreshed["engagement_score"] <= 2.0:
        hints.append(
            _build_social_performance_memory_hint(
                user_id=user_id,
                post_doc=refreshed,
                signal_type="low",
                reason="low_engagement",
            )
        )
    return refreshed, hints


def _compute_infinity_ranked_score(
    post: SocialPost,
    author_master_score: float,
) -> float:
    try:
        age_hours = (_now_utc() - _ensure_aware_utc(post.created_at)).total_seconds() / 3600
        recency_score = math.exp(-age_hours / 24)
    except Exception:
        recency_score = 0.5

    author_component = min(1.0, max(0.0, author_master_score / 100.0))
    raw_trust = TRUST_TIER_WEIGHTS.get(post.trust_tier_required, 1.0)
    trust_component = min(1.0, raw_trust / 2.0)

    return round(
        (recency_score * 0.4) + (author_component * 0.4) + (trust_component * 0.2),
        4,
    )


@router.post("/profile")
@limiter.limit("30/minute")
def upsert_profile(
    request: Request,
    profile_data: SocialProfile,
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        profiles = db["profiles"]
        user_id = str(current_user["sub"])
        existing_any = profiles.find_one({"username": profile_data.username})
        if existing_any and existing_any.get("user_id") != user_id:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "profile_forbidden",
                    "message": "Cannot modify another user's profile",
                },
            )

        existing = profiles.find_one(
            {
                "username": profile_data.username,
                "user_id": user_id,
            }
        )

        if existing:
            update_data = profile_data.dict(exclude={"id", "joined_at"})
            update_data["updated_at"] = _now_utc()
            update_data["user_id"] = user_id
            profiles.update_one(
                {"username": profile_data.username, "user_id": user_id},
                {"$set": update_data},
            )
            return {**existing, **update_data}

        new_profile = profile_data.dict()
        new_profile["user_id"] = user_id
        db["profiles"].insert_one(new_profile)
        return new_profile

    return execute_with_pipeline_sync(
        request=None,
        route_name="social.profile.upsert",
        handler=handler,
        user_id=str(current_user["sub"]),
    )


@router.get("/profile/{username}")
@limiter.limit("60/minute")
def get_profile(request: Request, username: str, db: Database = Depends(get_mongo_db)):
    def handler(ctx):
        profile = db["profiles"].find_one({"username": username})
        if not profile:
            raise HTTPException(
                status_code=404,
                detail={"error": "profile_not_found", "message": "Profile not found"},
            )
        return profile

    return execute_with_pipeline_sync(
        request=None,
        route_name="social.profile.get",
        handler=handler,
    )


@router.post("/post")
@limiter.limit("30/minute")
def create_post(
    request: Request,
    post: SocialPost,
    db: Database = Depends(get_mongo_db),
    sql_db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        post_data = post.dict()
        post_data["user_id"] = str(current_user["sub"])
        post_data["impressions"] = int(post_data.get("impressions", 0) or 0)
        post_data["clicks"] = int(post_data.get("clicks", 0) or 0)
        post_data["engagement_score"] = float(post_data.get("engagement_score", 0.0) or 0.0)
        post_data["conversion_signal"] = float(post_data.get("conversion_signal", 0.0) or 0.0)
        db["posts"].insert_one(post_data)
        return {
            "data": post_data,
            "execution_hints": {
                "memory": [
                    {
                        "event_type": "social_post",
                        "content": f"Social Broadcast: @{post.author_username} | {post.content}",
                        "source": "social_router",
                        "tags": ["social", "broadcast", post.trust_tier_required] + post.tags,
                        "node_type": "outcome",
                        "user_id": str(current_user["sub"]),
                        "agent_namespace": "social",
                    }
                ]
            },
        }

    return execute_with_pipeline_sync(
        request=None,
        route_name="social.post.create",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": sql_db},
    )


@router.get("/feed")
@limiter.limit("60/minute")
def get_feed(
    request: Request,
    limit: int = 20,
    trust_filter: Optional[str] = None,
    db: Database = Depends(get_mongo_db),
    sql_db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        posts_collection = db["posts"]
        query = {}
        if trust_filter:
            query["trust_tier_required"] = trust_filter

        cursor = posts_collection.find(query).sort("created_at", -1).limit(limit * 2)
        post_docs = list(cursor)
        memory_hints: list[dict] = []

        if post_docs:
            post_ids = [doc.get("id") for doc in post_docs if doc.get("id")]
            if post_ids:
                posts_collection.update_many(
                    {"id": {"$in": post_ids}},
                    {"$inc": {"impressions": 1}},
                )
                refreshed_docs = [
                    _maybe_capture_performance_signal(
                        db=db,
                        user_id=str(current_user["sub"]),
                        post_doc=post_doc,
                    )
                    for post_doc in posts_collection.find({"id": {"$in": post_ids}})
                ]
                post_docs = [item[0] for item in refreshed_docs]
                for _, hints in refreshed_docs:
                    memory_hints.extend(hints)

        author_ids = list({doc.get("author_id") for doc in post_docs if doc.get("author_id")})
        from apps.social.services.social_service import get_user_scores
        author_scores = get_user_scores(sql_db, author_ids)

        feed_items = []
        for post_doc in post_docs:
            try:
                post_obj = SocialPost(**post_doc)
                author_master = author_scores.get(post_obj.author_id, 50.0)
                relevance = _compute_infinity_ranked_score(post_obj, author_master)
                feed_items.append(
                    FeedItem(
                        post=post_obj,
                        relevance_score=relevance,
                        reason=f"Infinity score: {author_master:.0f} | tier: {post_obj.trust_tier_required}",
                    )
                )
            except Exception:
                continue

        feed_items.sort(key=lambda item: item.relevance_score, reverse=True)
        return {
            "data": feed_items[:limit],
            "execution_hints": {"memory": memory_hints},
        }

    return execute_with_pipeline_sync(
        request=None,
        route_name="social.feed.get",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": sql_db},
    )


@router.post("/posts/{post_id}/interact")
@limiter.limit("30/minute")
def record_post_interaction(
    request: Request,
    post_id: str,
    body: SocialInteractionRequest,
    db: Database = Depends(get_mongo_db),
    sql_db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    def handler(ctx):
        action = (body.action or "").strip().lower()
        if action not in {"view", "click", "like", "boost", "comment"}:
            raise HTTPException(
                status_code=422,
                detail={"error": "invalid_social_action", "message": "Unsupported social action"},
            )
        field = {
            "view": "impressions",
            "click": "clicks",
            "like": "likes",
            "boost": "boosts",
            "comment": "comments_count",
        }[action]
        amount = max(1, int(body.amount or 1))
        posts = db["posts"]
        post_doc = posts.find_one({"id": post_id})
        if not post_doc:
            raise HTTPException(
                status_code=404,
                detail={"error": "post_not_found", "message": "Post not found"},
            )

        posts.update_one({"id": post_id}, {"$inc": {field: amount}})
        updated = posts.find_one({"id": post_id}) or post_doc
        updated, memory_hints = _maybe_capture_performance_signal(
            db=db,
            user_id=str(current_user["sub"]),
            post_doc=updated,
        )
        return {
            "data": {
                "post_id": post_id,
                "action": action,
                "impressions": int(updated.get("impressions", 0) or 0),
                "clicks": int(updated.get("clicks", 0) or 0),
                "likes": int(updated.get("likes", 0) or 0),
                "boosts": int(updated.get("boosts", 0) or 0),
                "comments_count": int(updated.get("comments_count", 0) or 0),
                "engagement_score": float(updated.get("engagement_score", 0.0) or 0.0),
                "conversion_signal": float(updated.get("conversion_signal", 0.0) or 0.0),
            },
            "execution_hints": {"memory": memory_hints},
        }

    return execute_with_pipeline_sync(
        request=None,
        route_name="social.post.interact",
        handler=handler,
        user_id=str(current_user["sub"]),
        metadata={"db": sql_db},
    )


@router.get("/analytics")
@limiter.limit("60/minute")
def get_social_analytics(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    return execute_with_pipeline_sync(
        request=None,
        route_name="social.analytics.get",
        handler=lambda ctx: summarize_social_performance(user_id=str(current_user["sub"])),
        user_id=str(current_user["sub"]),
    )

