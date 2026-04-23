from __future__ import annotations

from datetime import datetime

from AINDY.watcher.constants import VALID_ACTIVITY_TYPES, VALID_SIGNAL_TYPES, parse_timestamp


def get_valid_signal_types() -> frozenset[str]:
    return VALID_SIGNAL_TYPES


def get_valid_activity_types() -> frozenset[str]:
    return VALID_ACTIVITY_TYPES


def parse_signal_timestamp(timestamp: str) -> datetime:
    return parse_timestamp(timestamp)


__all__ = [
    "get_valid_activity_types",
    "get_valid_signal_types",
    "parse_signal_timestamp",
]
