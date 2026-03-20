"""
Agent Model - v5 Phase 3

Represents an agent in the A.I.N.D.Y. ecosystem.
Each agent has a memory namespace - a stable identifier
that tags all memory nodes it creates.

System agents: ARM, Genesis, Nodus, LeadGen, SYLVA
Custom agents: user-defined (future)
"""
from sqlalchemy import Column, String, Text, Boolean, DateTime
from sqlalchemy.sql import func

from db.database import Base

# System agent namespaces - stable identifiers
AGENT_ARM = "arm"
AGENT_GENESIS = "genesis"
AGENT_NODUS = "nodus"
AGENT_LEADGEN = "leadgen"
AGENT_SYLVA = "sylva"
AGENT_USER = "user"  # manually created by user

SYSTEM_AGENTS = {
    AGENT_ARM,
    AGENT_GENESIS,
    AGENT_NODUS,
    AGENT_LEADGEN,
    AGENT_SYLVA,
}


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    agent_type = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    owner_user_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    memory_namespace = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
