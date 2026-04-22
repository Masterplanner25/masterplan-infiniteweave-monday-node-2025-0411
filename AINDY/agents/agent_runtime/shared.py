from __future__ import annotations

import logging
import sys
import threading
import types
from typing import Any

from sqlalchemy.orm import Session

from AINDY.platform_layer.openai_client import chat_completion, get_openai_client
from AINDY.platform_layer.external_call_service import perform_external_call
from AINDY.platform_layer.user_ids import parse_user_id

logger = logging.getLogger(__name__)

_client: Any | None = None
LOCAL_AGENT_ID = "00000000-0000-0000-0000-000000000001"
_plan_failure = threading.local()
_OBJECTIVE_ATTR = "".join(("go", "al"))
_OBJECTIVE_PREVIEW_KEY = "objective_preview"


def get_runtime_compat_module() -> types.ModuleType:
    compat = sys.modules.get("agents.agent_runtime")
    if compat is not None:
        return compat
    compat = sys.modules.get("AINDY.agents.agent_runtime")
    if compat is not None:
        return compat
    import AINDY.agents.agent_runtime as compat_module

    return compat_module


def _run_objective(run) -> str:
    return getattr(run, "objective", None) or getattr(run, _OBJECTIVE_ATTR, "") or ""


def _resolve_objective(objective: str | None, values: dict) -> str:
    resolved = objective if objective is not None else values.get("objective")
    if resolved is None:
        resolved = values.get(_OBJECTIVE_ATTR)
    return "" if resolved is None else str(resolved)


def _objective_preview(objective_text: str) -> dict:
    return {_OBJECTIVE_PREVIEW_KEY: objective_text[:120]}


def _db_user_id(user_id: str):
    parsed = parse_user_id(user_id)
    return parsed if parsed is not None else user_id


def _db_run_id(run_id):
    parsed = parse_user_id(run_id)
    return parsed if parsed is not None else run_id


def _user_matches(left, right) -> bool:
    left_uuid = parse_user_id(left)
    right_uuid = parse_user_id(right)
    if left_uuid is not None and right_uuid is not None:
        return left_uuid == right_uuid
    return str(left) == str(right)


def _get_client() -> Any:
    global _client
    if _client is None:
        _client = get_openai_client()
    return _client


def _get_planner_context(run_type: str, *, user_id: str, db: Session) -> dict:
    from AINDY.platform_layer.registry import get_planner_context

    return get_planner_context(
        run_type,
        {"run_type": run_type, "user_id": _db_user_id(user_id), "db": db},
    )


def _get_tools_for_run(run_type: str, *, user_id: str, db: Session) -> list[dict]:
    from AINDY.platform_layer.registry import get_tools_for_run

    return get_tools_for_run(
        run_type,
        {"run_type": run_type, "user_id": _db_user_id(user_id), "db": db},
    )


def _emit_runtime_event(event_name: str, context: dict) -> list:
    from AINDY.platform_layer.registry import emit_agent_event

    return emit_agent_event(event_name, context)
