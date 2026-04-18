"""Automation app ORM models."""

from apps.automation.automation_log import AutomationLog
from apps.automation.bridge_user_event import BridgeUserEvent
from apps.automation.infinity_loop import LoopAdjustment, UserFeedback
from apps.automation.learning_record import LearningRecordDB
from apps.automation.learning_threshold import LearningThresholdDB

__all__ = [
    "AutomationLog",
    "BridgeUserEvent",
    "LearningRecordDB",
    "LearningThresholdDB",
    "LoopAdjustment",
    "UserFeedback",
]


def register_models() -> None:
    return None
