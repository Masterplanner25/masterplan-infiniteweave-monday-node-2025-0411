"""
db/models/api_key.py — Platform API key model.

Stores hashed API keys with scoped capabilities.
Plaintext key is generated once and never persisted — only the SHA-256 hash
is stored so a database breach cannot expose live credentials.

Key format: aindy_<43-char url-safe base64 random token>
Example:     aindy_X7kB3mQpRvL9...
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from AINDY.db.database import Base


class PlatformAPIKey(Base):
    __tablename__ = "platform_api_keys"

    # ── Identity ───────────────────────────────────────────────────────────────
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Ownership ──────────────────────────────────────────────────────────────
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Key material ───────────────────────────────────────────────────────────
    name = Column(String(128), nullable=False)
    # First 12 chars of the raw key (safe to display in listings)
    key_prefix = Column(String(16), nullable=False)
    # SHA-256 hex digest of the full key — used for lookup
    key_hash = Column(String(64), nullable=False, unique=True, index=True)

    # ── Capabilities ───────────────────────────────────────────────────────────
    # Stored as a PostgreSQL text[] array for fast ANY() lookups.
    # Use ARRAY(String) — compatible with standard pg driver.
    scopes = Column(ARRAY(String), nullable=False, default=list)

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    is_active = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # ── Timestamps ─────────────────────────────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="api_keys")

    def is_valid(self) -> bool:
        """True if the key is active, not revoked, and not expired."""
        if not self.is_active or self.revoked_at is not None:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True
