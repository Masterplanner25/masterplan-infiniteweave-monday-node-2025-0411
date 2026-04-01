"""
services/api_key_service.py — Platform API key management.

Key generation and hashing
---------------------------
  generate_key()     — returns (raw_key, key_hash) — raw key is NEVER stored.
  hash_key(raw_key)  — SHA-256 hex digest used as the DB lookup token.

Key lifecycle
--------------
  create_api_key()   — inserts a new PlatformAPIKey record; returns (record, raw_key).
                       The raw key is returned exactly once and never retrievable again.
  revoke_api_key()   — sets revoked_at to now(); ownership-checked.
  list_api_keys()    — returns safe public metadata (no hash, no plaintext).
  touch_last_used()  — non-blocking last_used_at stamp called from auth path.

Scopes are free-form strings validated against auth.api_key_auth.Scopes.ALL by the
caller (platform_router.py) before calling create_api_key().
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

_KEY_PREFIX = "aindy_"
_KEY_TOKEN_BYTES = 32  # 32 bytes → 43-char url-safe base64 (without padding)


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def hash_key(raw_key: str) -> str:
    """Return the SHA-256 hex digest of *raw_key*."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_key() -> tuple[str, str]:
    """
    Generate a new platform API key.

    Returns (raw_key, key_hash).
    raw_key  — the plaintext key to deliver to the caller (aindy_<token>).
    key_hash — SHA-256 hex digest to store in the database.
    """
    token = secrets.token_urlsafe(_KEY_TOKEN_BYTES)
    raw_key = f"{_KEY_PREFIX}{token}"
    return raw_key, hash_key(raw_key)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_api_key(
    user_id: str,
    name: str,
    scopes: list[str],
    db: Session,
    *,
    expires_at: Optional[datetime] = None,
) -> tuple["PlatformAPIKey", str]:
    """
    Create and persist a new API key for *user_id*.

    Returns (record, raw_key).  *raw_key* is the only time the plaintext key
    is available — it is not stored and cannot be recovered later.
    """
    from db.models.api_key import PlatformAPIKey

    raw_key, key_hash = generate_key()
    key_prefix = raw_key[:16]  # first 16 chars (aindy_ + ~10) — safe to display

    record = PlatformAPIKey(
        id=uuid.uuid4(),
        user_id=uuid.UUID(str(user_id)),
        name=name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=list(scopes),
        is_active=True,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, raw_key


def revoke_api_key(key_id: str, user_id: str, db: Session) -> bool:
    """
    Revoke the API key identified by *key_id*.

    Ownership-checked: only the owning user may revoke.
    Returns True if revoked, False if not found / not owned.
    """
    from db.models.api_key import PlatformAPIKey

    record = db.query(PlatformAPIKey).filter(
        PlatformAPIKey.id == uuid.UUID(key_id),
        PlatformAPIKey.user_id == uuid.UUID(user_id),
    ).first()

    if record is None:
        return False

    record.revoked_at = datetime.now(timezone.utc)
    record.is_active = False
    db.commit()
    return True


def list_api_keys(user_id: str, db: Session) -> list[dict]:
    """Return public metadata for all keys owned by *user_id* (no hash / plaintext)."""
    from db.models.api_key import PlatformAPIKey

    records = db.query(PlatformAPIKey).filter(
        PlatformAPIKey.user_id == uuid.UUID(user_id),
    ).order_by(PlatformAPIKey.created_at.desc()).all()

    return [_public_meta(r) for r in records]


def get_api_key(key_id: str, user_id: str, db: Session) -> dict | None:
    """Return public metadata for a single key, or None if not found / not owned."""
    from db.models.api_key import PlatformAPIKey

    record = db.query(PlatformAPIKey).filter(
        PlatformAPIKey.id == uuid.UUID(key_id),
        PlatformAPIKey.user_id == uuid.UUID(user_id),
    ).first()

    return _public_meta(record) if record else None


def touch_last_used(record: "PlatformAPIKey", db: Session) -> None:
    """Stamp last_used_at on *record*.  Called from the auth hot-path; must be fast."""
    record.last_used_at = datetime.now(timezone.utc)
    db.commit()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _public_meta(record: "PlatformAPIKey") -> dict:
    return {
        "id": str(record.id),
        "name": record.name,
        "key_prefix": record.key_prefix,
        "scopes": list(record.scopes or []),
        "is_active": record.is_active,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "revoked_at": record.revoked_at.isoformat() if record.revoked_at else None,
        "last_used_at": record.last_used_at.isoformat() if record.last_used_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
