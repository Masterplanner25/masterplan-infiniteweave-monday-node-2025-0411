from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from typing import List, Optional
from datetime import datetime

# ✅ Import the Mongo setup
from db.mongo_setup import get_mongo_db
# ✅ Import the Data Models
from db.models.social_models import SocialProfile, SocialPost, FeedItem, TrustTier

# ✅ NEW: Import the Memory Scribe Bridge
# This allows us to "teleport" data from the Social Layer (Mongo) to the Memory Layer (SQL/Symbolic)
from bridge.bridge import create_memory_node

router = APIRouter(prefix="/social", tags=["Social Layer"])

# --- 1. IDENTITY ENDPOINTS (The "Anti-Resume") ------------------------------

@router.post("/profile", response_model=SocialProfile)
def upsert_profile(
    profile_data: SocialProfile, 
    db: Database = Depends(get_mongo_db)
):
    """
    Create or Update a user's social profile.
    Uses 'username' as the unique key.
    """
    profiles = db["profiles"]
    
    existing = profiles.find_one({"username": profile_data.username})
    
    if existing:
        update_data = profile_data.dict(exclude={"id", "joined_at"})
        update_data["updated_at"] = datetime.utcnow()
        profiles.update_one({"username": profile_data.username}, {"$set": update_data})
        return {**existing, **update_data}
    else:
        new_profile = profile_data.dict()
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
def create_post(post: SocialPost, db: Database = Depends(get_mongo_db)):
    """
    Publish a new update to the network AND log it to the Memory Scribe.
    """
    posts = db["posts"]
    post_data = post.dict()
    
    # 1. Save to Social Layer (MongoDB)
    posts.insert_one(post_data)
    
    # 2. 🧠 Awaken the Memory Scribe (Bridge to AI Memory)
    try:
        # We create a symbolic node representing this thought/update
        create_memory_node(
            title=f"Social Broadcast: @{post.author_username}",
            content=post.content,
            tags=["social", "broadcast", post.trust_tier_required] + post.tags
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
        
        # "Proof of Visibility" Relevance Scoring (Placeholder Logic)
        relevance = 1.0 
        if post_obj.trust_tier_required == TrustTier.INNER_CIRCLE:
            relevance = 2.0 
            
        feed_items.append(FeedItem(
            post=post_obj,
            relevance_score=relevance,
            reason="Network Activity"
        ))
        
    return feed_items