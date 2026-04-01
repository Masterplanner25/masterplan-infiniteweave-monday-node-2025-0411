"""
db/models/dynamic_flow.py — Persisted dynamic flow registrations.

Stores the definition of every flow registered via POST /platform/flows.
On server startup the platform loader reads all active rows and re-registers
each one into FLOW_REGISTRY so the runtime survives restarts.

definition_json schema:
    {
        "nodes": ["node_a", "node_b"],
        "edges": {"node_a": ["node_b"]},
        "start": "node_a",
        "end":   ["node_b"]
    }

Deletion is soft — is_active=False — so the audit trail is preserved.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID

from db.database import Base


class DynamicFlow(Base):
    __tablename__ = "dynamic_flows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(256), nullable=False, unique=True, index=True)

    # Full flow definition — nodes list + edges dict + start + end list
    definition_json = Column(JSON, nullable=False)

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

    # Soft-delete: False means the flow was removed via DELETE /platform/flows/{name}
    is_active = Column(Boolean, nullable=False, default=True)
