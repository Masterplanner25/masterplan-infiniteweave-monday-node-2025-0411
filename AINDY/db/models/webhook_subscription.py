"""
db/models/webhook_subscription.py — Persisted webhook subscriptions.

Stores every subscription created via POST /platform/webhooks.
On startup the platform loader reads all active rows and re-loads them
into the in-memory _SUBSCRIPTIONS dict in event_service.py, restoring
the same subscription IDs so any client that stored a subscription_id
continues to work after a restart.

The `id` column doubles as the subscription_id returned to callers — the
event_service generates the UUID and this model stores it verbatim.

`secret` is the HMAC-SHA256 signing secret for outgoing delivery requests.
Stored plaintext because it is an *outgoing* credential (needed to sign),
not an inbound credential (where hashing would be appropriate).

Deletion is soft — is_active=False.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from db.database import Base


class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"

    # This ID is the public subscription_id returned to API callers.
    id = Column(UUID(as_uuid=True), primary_key=True)

    # Subscription pattern — exact, prefix wildcard, or global wildcard
    event_type = Column(String(256), nullable=False, index=True)

    # External URL that receives POST payloads
    callback_url = Column(String(2048), nullable=False)

    # Outgoing HMAC-SHA256 signing secret.  Null when not configured.
    secret = Column(String(512), nullable=True)

    created_by = Column(String(256), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Soft-delete: False means subscription was cancelled via DELETE /platform/webhooks/{id}
    is_active = Column(Boolean, nullable=False, default=True)
