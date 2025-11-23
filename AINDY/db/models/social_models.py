from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

# --- ENUMS & CONSTANTS -------------------------------------------------------
class TrustTier:
    INNER_CIRCLE = "inner"   # High trust, full access
    COLLAB = "collab"        # Working relationship
    OBSERVER = "observer"    # Public follower
    SYSTEM = "system"        # AI Agents / System Nodes

# --- 1. IDENTITY: The Living Profile -----------------------------------------
class SocialProfile(BaseModel):
    """
    Represents the user's identity in the social layer.
    Unlike LinkedIn, this focuses on 'Current Velocity' (metrics) over 'Past History' (resume).
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    tagline: Optional[str] = None
    bio: Optional[str] = None
    
    # 🧠 The "Anti-LinkedIn" Differentiator: Verified Metrics
    # Instead of "Skills", we show "Velocity".
    metrics_snapshot: Dict[str, float] = Field(default_factory=lambda: {
        "twr_score": 0.0,          # Time-to-Wealth Ratio
        "trust_score": 50.0,       # Base trust level
        "execution_velocity": 0.0  # Tasks completed / time
    })
    
    tags: List[str] = []           # e.g., "AI Builder", "Solo Dev"
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# --- 2. CONTENT: The Knowledge Feed -----------------------------------------
class SocialPost(BaseModel):
    """
    A unit of content. Could be a text update, a project log, or an AI insight.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    author_id: str
    author_username: str  # Denormalized for faster feed rendering
    
    content: str
    media_url: Optional[str] = None
    
    # 🏷️ Semantic Routing
    tags: List[str] = []
    
    # 🛡️ Privacy & Visibility Logic
    trust_tier_required: str = TrustTier.OBSERVER
    
    # 📊 Engagement (Flattened visibility model)
    likes: int = 0
    boosts: int = 0
    comments_count: int = 0
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # AI Analysis Hook (for future "Memory Scribe" integration)
    ai_context: Optional[Dict[str, Any]] = None

# --- 3. RELATIONSHIPS: The Trust Graph --------------------------------------
class Connection(BaseModel):
    """
    Replaces 'Degrees of Connection'.
    Defines a directional relationship with a specific trust weight.
    """
    source_id: str
    target_id: str
    tier: str = TrustTier.OBSERVER
    context: Optional[str] = None  # e.g., "Worked on Alpha Project"
    created_at: datetime = Field(default_factory=datetime.utcnow)

# --- 4. FEED LOGIC: What the User Sees --------------------------------------
class FeedItem(BaseModel):
    """
    A composed object for the frontend feed.
    Combines the post with the viewer's context (e.g., "Why am I seeing this?")
    """
    post: SocialPost
    relevance_score: float
    reason: str  # e.g., "High Trust Connection" or "Trending in #AI"