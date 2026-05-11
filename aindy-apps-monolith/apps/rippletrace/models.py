"""Rippletrace app ORM models."""

from apps.rippletrace.drop import DropPointDB, PingDB
from apps.rippletrace.playbook import PlaybookDB
from apps.rippletrace.ripple_edge import RippleEdge
from apps.rippletrace.strategy import StrategyDB

__all__ = [
    "DropPointDB",
    "PingDB",
    "PlaybookDB",
    "RippleEdge",
    "StrategyDB",
]


def register_models() -> None:
    return None
