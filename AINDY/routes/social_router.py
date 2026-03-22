from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from typing import List, Optional
import math
from datetime import datetime
from sqlalchemy.orm import Session

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

TRUST_TIER_WEIGHTS = {
    TrustTier.INNER_CIRCLE: 2.0,
    TrustTier.COLLAB: 1.5,
    TrustTier.OBSERVER: 1.0,
    TrustTier.SYSTEM: 1.2,
}


def _compute_visibility_score(post: SocialPost) -> float:
    trust_weight = TRUST_TIER_WEIGHTS.get(post.trust_tier_required, 1.0)
    engagement_total = max(post.likes, 0) + max(post.boosts, 0) * 2 + max(post.comments_count, 0)
    engagement_score = math.log1p(engagement_total) / 5.0
    return trust_weight * (1.0 + min(engagement_score, 1.0))

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
    existing_any = profiles.find_one({"username": profile_data.username})
    if existing_any and existing_any.get("user_id") != user_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify another user's profile",
        )

    existing = profiles.find_one({
        "username": profile_data.username,
        "user_id": user_id,
    })
    
    if existing:
        update_data = profile_data.dict(exclude={"id", "joined_at"})
        update_data["updated_at"] = datetime.utcnow()
        update_data["user_id"] = user_id
        profiles.update_one(
            {"username": profile_data.username, "user_id": user_id},
            {"$set": update_data},
        )
        return {**existing, **update_data}
    else:
        new_profile = profile_data.dict()
        new_profile["user_id"] = user_id
        profiles.insert_one(new_profile)
        return new_profile

@router.get("/profile/{username}", response_model=SocialProfile)
def get_profile(username: str, db: Database = Depends(get_mongo_db)):
    """
    Fetch a public profile.
    """
    profile = db["profiles"].find_one({"username": username})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
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
    
    # 1. Save to Social Layer (MongoDB)
    posts.insert_one(post_data)
    
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
        print(f"✅ [Scribe] Logged post by {post.author_username} to Memory Bridge.")
    except Exception as e:
        # We don't want to crash the post if the scribe fails, just log the error
        print(f"⚠️ [Scribe] Failed to capture memory: {e}")

    return post_data

@router.get("/feed", response_model=List[FeedItem])
def get_feed(limit: int = 20, trust_filter: Optional[str] = None, db: Database = Depends(get_mongo_db)):
    """
    Retrieve the main feed.
    """
    posts_collection = db["posts"]
    query = {}
    
    if trust_filter:
        query["trust_tier_required"] = trust_filter

    cursor = posts_collection.find(query).sort("created_at", -1).limit(limit)
    
    feed_items = []
    for post_doc in cursor:
        post_obj = SocialPost(**post_doc)
        
        relevance = _compute_visibility_score(post_obj)
        feed_items.append(FeedItem(
            post=post_obj,
            relevance_score=relevance,
            reason=f"Trust tier {post_obj.trust_tier_required}"
        ))

    feed_items.sort(key=lambda item: item.relevance_score, reverse=True)
    return feed_items
