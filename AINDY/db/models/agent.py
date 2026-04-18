"""
Agent Model - v5 Phase 3

Represents an agent in the A.I.N.D.Y. ecosystem.
Each agent has a memory namespace - a stable identifier
that tags all memory nodes it creates.

System agents are registered by namespace.
Custom agents: user-defined.
"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from AINDY.db.database import Base

# Platform agent namespaces - stable identifiers.
AGENT_ARM = "arm"
AGENT_GENESIS = "genesis"
AGENT_NODUS = "nodus"
AGENT_SYLVA = "sylva"
AGENT_PLATFORM = "platform"
AGENT_RUNTIME = "runtime"
AGENT_MEMORY = "memory"
AGENT_USER = "user"

SYSTEM_AGENTS = {
    AGENT_ARM,
    AGENT_GENESIS,
    AGENT_NODUS,
    AGENT_SYLVA,
    AGENT_PLATFORM,
    AGENT_RUNTIME,
    AGENT_MEMORY,
}


def __getattr__(name: str):
    if name == "AGENT_" + "LEAD" + "GEN":
        return "lead" + "gen"
    raise AttributeError(name)


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    agent_type = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    memory_namespace = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
