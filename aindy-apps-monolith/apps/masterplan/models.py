"""Masterplan app ORM models."""

from apps.masterplan.goal_state import GoalState
from apps.masterplan.goals import Goal
from apps.masterplan.masterplan import GenesisSessionDB, MasterPlan

__all__ = [
    "GenesisSessionDB",
    "Goal",
    "GoalState",
    "MasterPlan",
]


def register_models() -> None:
    return None
