"""
db/models/dynamic_node.py — Persisted dynamic node registrations.

Stores every node registered via POST /platform/nodes/register.
On startup the platform loader reads all active rows and rebuilds each
node function (webhook factory or plugin import) then registers it into
NODE_REGISTRY.

handler_config schema:
    webhook:  {"url": "https://...", "timeout_seconds": 10}
    plugin:   {"handler": "my_module:my_function"}

The signing secret for webhook nodes is stored in the separate `secret`
column (plaintext) because it is an *outgoing* signing credential — the
value is needed to sign delivery requests, not just to verify one.

Deletion is soft — is_active=False.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSON, UUID

from AINDY.db.database import Base


class DynamicNode(Base):
    __tablename__ = "dynamic_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(256), nullable=False, unique=True, index=True)

    # "webhook" | "plugin"
    node_type = Column(String(32), nullable=False)

    # Type-specific config — no secrets here
    handler_config = Column(JSON, nullable=False)

    # Webhook-only outgoing signing secret.  Stored plaintext because it is
    # used to sign every outgoing delivery request.
    secret = Column(String(512), nullable=True)

    created_by = Column(String(256), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    is_active = Column(Boolean, nullable=False, default=True)
