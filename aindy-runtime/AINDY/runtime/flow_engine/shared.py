import logging
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from AINDY.config import settings
from AINDY.core.execution_envelope import error as execution_error
from AINDY.core.execution_envelope import success as execution_success
from AINDY.core.execution_signal_helper import queue_memory_capture, queue_system_event
from AINDY.core.retry_policy import resolve_retry_policy as _resolve_retry_policy
from AINDY.core.system_event_service import emit_error_event
from AINDY.core.system_event_types import SystemEventTypes
from AINDY.platform_layer.registry import emit_event
from AINDY.platform_layer.trace_context import ensure_trace_id
from AINDY.platform_layer.trace_context import get_trace_id
from AINDY.platform_layer.trace_context import reset_parent_event_id
from AINDY.platform_layer.trace_context import reset_trace_id
from AINDY.platform_layer.trace_context import set_parent_event_id
from AINDY.platform_layer.trace_context import set_trace_id
from AINDY.platform_layer.user_ids import parse_user_id
from AINDY.utils.uuid_utils import normalize_uuid

emit_system_event = queue_system_event

logger = logging.getLogger(__name__)


def _default_wait_deadline(timeout_minutes: int | None = None) -> datetime:
    minutes = (
        timeout_minutes
        if timeout_minutes is not None
        else settings.FLOW_WAIT_TIMEOUT_MINUTES
    )
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)
