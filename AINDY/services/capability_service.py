"""
Capability service — Sprint N+10 Agentics Phase 4.

Implements the bounded-authority layer for agent runs:
  - derive which tools may be auto-granted
  - mint per-run capability tokens
  - validate stored tokens
  - enforce per-step tool authorization

All functions are fail-closed and never raise.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from services.agent_tools import TOOL_REGISTRY

logger = logging.getLogger(__name__)

TOKEN_TTL_HOURS = 24
DISALLOWED_AUTO_GRANT_TOOLS = {"genesis.message"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_tool_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item in TOOL_REGISTRY:
            result.append(item)
    return sorted(set(result))


def _token_hash(
    run_id: str,
    user_id: str,
    issued_at: str,
    expires_at: str,
    approval_mode: str,
    granted_tools: list[str],
) -> str:
    payload = "|".join(
        [
            str(run_id),
            str(user_id),
            issued_at,
            expires_at,
            approval_mode,
            ",".join(sorted(granted_tools)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_trust(user_id: str, db) -> Optional[Any]:
    try:
        from db.models.agent_run import AgentTrustSettings

        return (
            db.query(AgentTrustSettings)
            .filter(AgentTrustSettings.user_id == user_id)
            .first()
        )
    except Exception as exc:
        logger.warning("[CapabilityService] Failed to load trust settings: %s", exc)
        return None


def get_auto_grantable_tools(user_id: str, db) -> list[str]:
    """
    Return the explicit auto-grant allowlist for a user.

    Preferred source is AgentTrustSettings.allowed_auto_grant_tools.
    If absent, falls back to the deprecated low/medium booleans.
    High-risk tools are never auto-grantable.
    """
    try:
        trust = _get_trust(user_id=user_id, db=db)
        if not trust:
            return []

        explicit = _normalize_tool_list(getattr(trust, "allowed_auto_grant_tools", None))
        if explicit:
            return [
                tool_name
                for tool_name in explicit
                if tool_name not in DISALLOWED_AUTO_GRANT_TOOLS
                and TOOL_REGISTRY.get(tool_name, {}).get("risk") in {"low", "medium"}
            ]

        allowed = []
        for tool_name, meta in TOOL_REGISTRY.items():
            risk = meta.get("risk")
            if tool_name in DISALLOWED_AUTO_GRANT_TOOLS:
                continue
            if risk == "low" and getattr(trust, "auto_execute_low", False):
                allowed.append(tool_name)
            elif risk == "medium" and getattr(trust, "auto_execute_medium", False):
                allowed.append(tool_name)
        return sorted(allowed)
    except Exception as exc:
        logger.warning("[CapabilityService] get_auto_grantable_tools failed: %s", exc)
        return []


def get_grantable_tools(
    plan: Optional[dict],
    user_id: str,
    db,
    approval_mode: str,
) -> list[str]:
    """
    Return the set of tools that may be granted for a specific run.

    manual: any known tool in the plan may be granted
    auto:   every planned tool must be in the user's auto-grant allowlist
    """
    try:
        steps = (plan or {}).get("steps", [])
        plan_tools = []
        for step in steps:
            tool_name = step.get("tool")
            if not isinstance(tool_name, str) or tool_name not in TOOL_REGISTRY:
                return []
            plan_tools.append(tool_name)

        unique_tools = sorted(set(plan_tools))
        if approval_mode == "manual":
            return unique_tools

        allowed = set(get_auto_grantable_tools(user_id=user_id, db=db))
        if all(tool_name in allowed for tool_name in unique_tools):
            return unique_tools
        return []
    except Exception as exc:
        logger.warning("[CapabilityService] get_grantable_tools failed: %s", exc)
        return []


def mint_token(
    run_id: str,
    user_id: str,
    plan: Optional[dict],
    db,
    approval_mode: str,
) -> Optional[dict]:
    """
    Mint a 24-hour capability token scoped to the tools in this run's plan.

    Returns None when the plan contains non-grantable tools.
    """
    try:
        step_count = len((plan or {}).get("steps", []))
        granted_tools = get_grantable_tools(
            plan=plan,
            user_id=user_id,
            db=db,
            approval_mode=approval_mode,
        )
        if not granted_tools and step_count > 0:
            return None

        issued_at = _utcnow()
        expires_at = issued_at + timedelta(hours=TOKEN_TTL_HOURS)
        issued_at_s = issued_at.isoformat()
        expires_at_s = expires_at.isoformat()

        return {
            "run_id": str(run_id),
            "user_id": str(user_id),
            "issued_at": issued_at_s,
            "expires_at": expires_at_s,
            "granted_tools": granted_tools,
            "approval_mode": approval_mode,
            "token_hash": _token_hash(
                run_id=str(run_id),
                user_id=str(user_id),
                issued_at=issued_at_s,
                expires_at=expires_at_s,
                approval_mode=approval_mode,
                granted_tools=granted_tools,
            ),
        }
    except Exception as exc:
        logger.warning("[CapabilityService] mint_token failed: %s", exc)
        return None


def validate_token(token: Optional[dict], run_id: str, user_id: str) -> dict:
    """
    Validate token structure, scope, expiry, and integrity hash.

    Returns {"ok": bool, "error": str|None, "granted_tools": list[str]}.
    """
    try:
        if not isinstance(token, dict):
            return {"ok": False, "error": "missing capability token", "granted_tools": []}

        token_run_id = str(token.get("run_id", ""))
        token_user_id = str(token.get("user_id", ""))
        issued_at = token.get("issued_at")
        expires_at = token.get("expires_at")
        approval_mode = token.get("approval_mode")
        granted_tools = _normalize_tool_list(token.get("granted_tools"))
        token_hash = token.get("token_hash")

        if token_run_id != str(run_id):
            return {"ok": False, "error": "token run mismatch", "granted_tools": []}
        if token_user_id != str(user_id):
            return {"ok": False, "error": "token user mismatch", "granted_tools": []}
        if approval_mode not in {"manual", "auto"}:
            return {"ok": False, "error": "invalid approval mode", "granted_tools": []}
        if not issued_at or not expires_at or token_hash is None:
            return {"ok": False, "error": "incomplete capability token", "granted_tools": []}

        try:
            expires_at_dt = datetime.fromisoformat(str(expires_at))
        except Exception:
            return {"ok": False, "error": "invalid token expiry", "granted_tools": []}

        if expires_at_dt.tzinfo is None:
            expires_at_dt = expires_at_dt.replace(tzinfo=timezone.utc)
        if expires_at_dt <= _utcnow():
            return {"ok": False, "error": "capability token expired", "granted_tools": []}

        expected_hash = _token_hash(
            run_id=str(run_id),
            user_id=str(user_id),
            issued_at=str(issued_at),
            expires_at=str(expires_at),
            approval_mode=approval_mode,
            granted_tools=granted_tools,
        )
        if expected_hash != token_hash:
            return {"ok": False, "error": "capability token hash mismatch", "granted_tools": []}

        return {"ok": True, "error": None, "granted_tools": granted_tools}
    except Exception as exc:
        logger.warning("[CapabilityService] validate_token failed: %s", exc)
        return {"ok": False, "error": "token validation failed", "granted_tools": []}


def check_tool_capability(
    token: Optional[dict],
    run_id: str,
    user_id: str,
    tool_name: str,
) -> dict:
    """
    Enforce that a token is valid and explicitly grants the requested tool.
    """
    try:
        validation = validate_token(token=token, run_id=run_id, user_id=user_id)
        if not validation["ok"]:
            return {
                "ok": False,
                "error": validation["error"],
                "granted_tools": validation.get("granted_tools", []),
            }

        if tool_name not in validation["granted_tools"]:
            return {
                "ok": False,
                "error": f"tool '{tool_name}' not granted by capability token",
                "granted_tools": validation["granted_tools"],
            }

        return {
            "ok": True,
            "error": None,
            "granted_tools": validation["granted_tools"],
        }
    except Exception as exc:
        logger.warning("[CapabilityService] check_tool_capability failed: %s", exc)
        return {"ok": False, "error": "capability check failed", "granted_tools": []}
