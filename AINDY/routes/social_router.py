from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from typing import List, Optional
import math
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.orm import Session
import logging

# ✅ Import the Mongo setup
from db.mongo_setup import get_mongo_db
from db.database import get_db
# ✅ Import the Data Models
from db.models.social_models import SocialProfile, SocialPost, FeedItem, TrustTier

# ✅ NEW: Import the Memory Scribe Bridge
# This allows us to "teleport" data from the Social Layer (Mongo) to the Memory Layer (SQL/Symbolic)
from services.memory_capture_engine import MemoryCaptureEngine
from services.auth_service import get_current_user

router = APIRouter(prefix="/social", tags=["Social Layer"], dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)

TRUST_TIER_WEIGHTS = {
    TrustTier.INNER_CIRCLE: 2.0,
    TrustTier.COLLAB: 1.5,
    TrustTier.OBSERVER: 1.0,
    TrustTier.SYSTEM: 1.2,
}


def _utcnow() -> datetime:
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


def _compute_infinity_ranked_score(
    post: SocialPost,
    author_master_score: float,
) -> float:
    """
    Infinity Algorithm feed ranking.

    rank = recency_score × 0.4 + author_score × 0.4 + trust_weight × 0.2

    recency_score: exponential decay (half-life 24h) based on post age
    author_score:  UserScore.master_score / 100 (0-1 scale)
    trust_weight:  normalized TRUST_TIER_WEIGHTS value (0-1 scale)
    """
    import math as _math

    # Recency: exp(-age_hours / 24), so a 24h-old post scores ~0.37
    try:
        age_hours = (_utcnow() - _ensure_aware_utc(post.created_at)).total_seconds() / 3600
        recency_score = _math.exp(-age_hours / 24)
    except Exception:
        recency_score = 0.5

    # Author Infinity score (0-1)
    author_component = min(1.0, max(0.0, author_master_score / 100.0))

    # Trust weight normalized (max weight is 2.0 → normalize to 0-1)
    raw_trust = TRUST_TIER_WEIGHTS.get(post.trust_tier_required, 1.0)
    trust_component = min(1.0, raw_trust / 2.0)

    return round(
        (recency_score * 0.4) +
        (author_component * 0.4) +
        (trust_component * 0.2),
        4
    )

# --- 1. IDENTITY ENDPOINTS (The "Anti-Resume") ------------------------------

@router.post("/profile", response_model=SocialProfile)
def upsert_profile(
    profile_data: SocialProfile,
    db: Database = Depends(get_mongo_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create or Update a user's social profile.
    Uses 'username' as the unique key.
    """
    profiles = db["profiles"]

    user_id = str(current_user["sub"])
    try:
        existing_any = profiles.find_one({"username": profile_data.username})
    except Exception as exc:
        logger.warning("Profile lookup failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "profile_lookup_failed", "message": "Profile lookup failed", "details": str(exc)},
        )
    if existing_any and existing_any.get("user_id") != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "profile_forbidden",
                "message": "Cannot modify another user's profile",
            },
        )

    try:
        existing = profiles.find_one({
            "username": profile_data.username,
            "user_id": user_id,
        })
    except Exception as exc:
        logger.warning("Profile lookup failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "profile_lookup_failed", "message": "Profile lookup failed", "details": str(exc)},
        )
    
    if existing:
        update_data = profile_data.dict(exclude={"id", "joined_at"})
        update_data["updated_at"] = _utcnow()
        update_data["user_id"] = user_id
        try:
            profiles.update_one(
                {"username": profile_data.username, "user_id": user_id},
                {"$set": update_data},
            )
        except Exception as exc:
            logger.warning("Profile update failed: %s", exc)
            raise HTTPException(
                status_code=500,
                detail={"error": "profile_update_failed", "message": "Profile update failed", "details": str(exc)},
            )
        return {**existing, **update_data}
    else:
        new_profile = profile_data.dict()
        new_profile["user_id"] = user_id
        try:
            profiles.insert_one(new_profile)
        except Exception as exc:
            logger.warning("Profile insert failed: %s", exc)
            raise HTTPException(
                status_code=500,
                detail={"error": "profile_create_failed", "message": "Profile create failed", "details": str(exc)},
            )
        return new_profile

@router.get("/profile/{username}", response_model=SocialProfile)
def get_profile(username: str, db: Database = Depends(get_mongo_db)):
    """
    Fetch a public profile.
    """
    try:
        profile = db["profiles"].find_one({"username": username})
    except Exception as exc:
        logger.warning("Profile fetch failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "profile_fetch_failed", "message": "Profile fetch failed", "details": str(exc)},
        )
    if not profile:
        raise HTTPException(
            status_code=404,
            detail={"error": "profile_not_found", "message": "Profile not found"},
        )
    return profile

# --- 2. CONTENT ENDPOINTS (The Trust Feed) ----------------------------------

@router.post("/post", response_model=SocialPost)
def create_post(
    post: SocialPost,
    db: Database = Depends(get_mongo_db),
    sql_db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Publish a new update to the network AND log it to the Memory Scribe.
    """
    posts = db["posts"]
    post_data = post.dict()
    try:
        # 1. Save to Social Layer (MongoDB)
        posts.insert_one(post_data)
    except Exception as exc:
        logger.warning("Post insert failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "post_create_failed", "message": "Post create failed", "details": str(exc)},
        )
    
    # 2. 🧠 Awaken the Memory Scribe (Bridge to AI Memory)
    try:
        engine = MemoryCaptureEngine(
            db=sql_db,
            user_id=str(current_user["sub"]),
            agent_namespace="social",
        )
        engine.evaluate_and_capture(
            event_type="social_post",
            content=f"Social Broadcast: @{post.author_username} | {post.content}",
            source="social_router",
            tags=["social", "broadcast", post.trust_tier_required] + post.tags,
            node_type="outcome",
        )
        logger.info("[Scribe] Logged post by %s to Memory Bridge.", post.author_username)
    except Exception as e:
        # We don't want to crash the post if the scribe fails, just log the error
        logger.warning("[Scribe] Failed to capture memory: %s", e)

    return post_data

@router.get("/feed", response_model=List[FeedItem])
def get_feed(
    limit: int = 20,
    trust_filter: Optional[str] = None,
    db: Database = Depends(get_mongo_db),
    sql_db: Session = Depends(get_db),
):
    """
    Retrieve the main feed, ranked by the Infinity Algorithm.

    Ranking: recency(0.4) + author_infinity_score(0.4) + trust_tier(0.2)
    """
    from db.models.user_score import UserScore

    posts_collection = db["posts"]
    query = {}

    if trust_filter:
        query["trust_tier_required"] = trust_filter

    try:
        cursor = posts_collection.find(query).sort("created_at", -1).limit(limit * 2)
    except Exception as exc:
        logger.warning("Feed query failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "feed_load_failed", "message": "Feed load failed", "details": str(exc)},
        )

    post_docs = list(cursor)

    # Batch-load author Infinity scores from PostgreSQL
    author_ids = list({doc.get("author_id") for doc in post_docs if doc.get("author_id")})
    author_scores: dict = {}
    try:
        if author_ids:
            author_uuid_ids = [UUID(str(author_id)) for author_id in author_ids]
            score_rows = sql_db.query(UserScore).filter(
                UserScore.user_id.in_(author_uuid_ids)
            ).all()
            author_scores = {str(row.user_id): row.master_score for row in score_rows}
    except Exception as exc:
        logger.warning("Author score lookup failed (non-fatal): %s", exc)

    feed_items = []
    for post_doc in post_docs:
        try:
            post_obj = SocialPost(**post_doc)
            author_master = author_scores.get(post_obj.author_id, 50.0)
            relevance = _compute_infinity_ranked_score(post_obj, author_master)
            feed_items.append(FeedItem(
                post=post_obj,
                relevance_score=relevance,
                reason=f"Infinity score: {author_master:.0f} | tier: {post_obj.trust_tier_required}",
            ))
        except Exception as exc:
            logger.debug("Feed item skipped: %s", exc)

    feed_items.sort(key=lambda item: item.relevance_score, reverse=True)
    return feed_items[:limit]
