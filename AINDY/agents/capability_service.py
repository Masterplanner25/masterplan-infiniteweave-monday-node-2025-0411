"""
Capability service for scoped agent execution.

Responsibilities:
  - load app-registered capability definitions
  - persist capability catalogue / mappings best-effort
  - mint per-run execution tokens with allowed capabilities
  - validate tokens and enforce capability checks fail-closed
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from AINDY.agents.tool_registry import TOOL_REGISTRY
from AINDY.platform_layer.user_ids import parse_user_id, require_user_id

logger = logging.getLogger(__name__)

TOKEN_TTL_HOURS = 24
DEFAULT_AGENT_TYPE = "default"

RISK_POLICY = {
    "low": "auto_allowed",
    "medium": "requires_approval",
    "high": "gated",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_tool_list(value: Any) -> list[str]:
    _ensure_capabilities_loaded()
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, str) and item in TOOL_REGISTRY})


def _normalize_capability_list(value: Any) -> list[str]:
    definitions = _get_capability_definitions()
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, str) and item in definitions})


def _ensure_capabilities_loaded() -> None:
    try:
        from AINDY.platform_layer.registry import load_plugins

        load_plugins()
    except Exception as exc:
        logger.debug("capability plugin load skipped: %s", exc)


def _get_capability_definitions() -> dict[str, dict[str, Any]]:
    _ensure_capabilities_loaded()
    try:
        from AINDY.platform_layer.registry import get_capability_definitions

        return get_capability_definitions()
    except Exception as exc:
        logger.warning("[CapabilityService] capability definition lookup failed: %s", exc)
        return {}


def _get_capabilities_for_tool(tool_name: str) -> list[str]:
    _ensure_capabilities_loaded()
    try:
        from AINDY.platform_layer.registry import get_capabilities_for_tool

        definitions = _get_capability_definitions()
        return [
            capability
            for capability in get_capabilities_for_tool(tool_name)
            if capability in definitions
        ]
    except Exception as exc:
        logger.warning("[CapabilityService] tool capability lookup failed: %s", exc)
        return []


def _get_capabilities_for_agent(agent_type: str) -> list[str]:
    _ensure_capabilities_loaded()
    try:
        from AINDY.platform_layer.registry import get_capabilities_for_agent

        definitions = _get_capability_definitions()
        capabilities = get_capabilities_for_agent(agent_type)
        if not capabilities and agent_type != DEFAULT_AGENT_TYPE:
            capabilities = get_capabilities_for_agent(DEFAULT_AGENT_TYPE)
        return [
            capability
            for capability in capabilities
            if capability in definitions
        ]
    except Exception as exc:
        logger.warning("[CapabilityService] agent capability lookup failed: %s", exc)
        return []


def _get_restricted_tools() -> set[str]:
    _ensure_capabilities_loaded()
    try:
        from AINDY.platform_layer.registry import get_restricted_tools

        return get_restricted_tools()
    except Exception as exc:
        logger.warning("[CapabilityService] restricted tool lookup failed: %s", exc)
        return set()


def get_policy_for_risk(risk_level: str) -> str:
    return RISK_POLICY.get(str(risk_level or "").lower(), "gated")


def get_tool_required_capability(tool_name: str) -> Optional[str]:
    capabilities = _get_capabilities_for_tool(tool_name)
    return capabilities[0] if capabilities else None


def get_plan_required_capabilities(plan: Optional[dict], agent_type: str = DEFAULT_AGENT_TYPE) -> list[str]:
    capabilities = set(_get_capabilities_for_agent(agent_type))
    for step in (plan or {}).get("steps", []):
        tool_name = step.get("tool")
        if not isinstance(tool_name, str):
            continue
        tool_capabilities = _get_capabilities_for_tool(tool_name)
        if not tool_capabilities:
            return []
        capabilities.update(tool_capabilities)
    return sorted(capabilities)


def _token_hash(
    run_id: str,
    user_id: str,
    execution_token: str,
    issued_at: str,
    expires_at: str,
    approval_mode: str,
    granted_tools: list[str],
    allowed_capabilities: list[str],
) -> str:
    payload = "|".join(
        [
            str(run_id),
            str(user_id),
            str(execution_token),
            issued_at,
            expires_at,
            approval_mode,
            ",".join(sorted(granted_tools)),
            ",".join(sorted(allowed_capabilities)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_trust(user_id: str, db) -> Optional[Any]:
    try:
        from apps.agent.models.agent_run import AgentTrustSettings

        return (
            db.query(AgentTrustSettings)
            .filter(AgentTrustSettings.user_id == require_user_id(user_id))
            .first()
        )
    except Exception as exc:
        logger.warning("[CapabilityService] Failed to load trust settings: %s", exc)
        return None


def sync_capability_catalog(db) -> None:
    """Best-effort seed of the capability table."""
    try:
        from AINDY.db.models.capability import Capability

        definitions = _get_capability_definitions()
        existing = {
            row.name: row
            for row in db.query(Capability).all()
        }
        changed = False
        for name, meta in definitions.items():
            row = existing.get(name)
            if row is None:
                db.add(
                    Capability(
                        name=name,
                        description=meta["description"],
                        risk_level=meta["risk_level"],
                    )
                )
                changed = True
            elif row.description != meta["description"] or row.risk_level != meta["risk_level"]:
                row.description = meta["description"]
                row.risk_level = meta["risk_level"]
                changed = True
        if changed:
            db.commit()
    except Exception as exc:
        logger.warning("[CapabilityService] sync_capability_catalog failed: %s", exc)


def _get_capability_rows(db) -> dict[str, Any]:
    try:
        from AINDY.db.models.capability import Capability

        sync_capability_catalog(db)
        return {row.name: row for row in db.query(Capability).all()}
    except Exception as exc:
        logger.warning("[CapabilityService] _get_capability_rows failed: %s", exc)
        return {}


def create_run_capability_mappings(
    run_id: str,
    agent_type: str,
    capability_names: list[str],
    db,
) -> None:
    """Best-effort persistence of run and agent-type capability mappings."""
    try:
        from AINDY.db.models.capability import AgentCapabilityMapping

        rows = _get_capability_rows(db)
        if not rows:
            return

        run_uuid = parse_user_id(run_id)

        existing = db.query(AgentCapabilityMapping).all()
        existing_keys = {
            (str(row.capability_id), str(row.agent_type or ""), str(row.agent_run_id or ""))
            for row in existing
        }

        for capability_name in capability_names:
            capability_row = rows.get(capability_name)
            if not capability_row:
                continue

            type_key = (str(capability_row.id), str(agent_type or ""), "")
            if agent_type and type_key not in existing_keys:
                db.add(
                    AgentCapabilityMapping(
                        capability_id=capability_row.id,
                        agent_type=agent_type,
                    )
                )
                existing_keys.add(type_key)

            run_key = (str(capability_row.id), "", str(run_id))
            if run_id and run_key not in existing_keys:
                db.add(
                    AgentCapabilityMapping(
                        capability_id=capability_row.id,
                        agent_run_id=run_uuid or run_id,
                    )
                )
                existing_keys.add(run_key)

        db.flush()
    except Exception as exc:
        logger.warning("[CapabilityService] create_run_capability_mappings failed: %s", exc)


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

        restricted_tools = _get_restricted_tools()
        explicit = _normalize_tool_list(getattr(trust, "allowed_auto_grant_tools", None))
        if explicit:
            return [
                tool_name
                for tool_name in explicit
                if tool_name not in restricted_tools
                and get_policy_for_risk(TOOL_REGISTRY.get(tool_name, {}).get("risk")) == "auto_allowed"
            ]

        allowed = []
        for tool_name, meta in TOOL_REGISTRY.items():
            risk = meta.get("risk")
            if tool_name in restricted_tools:
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
    auto:   only low-risk planned tools in the user's allowlist may be granted
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
        for tool_name in unique_tools:
            if tool_name not in allowed:
                return []
            if get_policy_for_risk(TOOL_REGISTRY[tool_name]["risk"]) != "auto_allowed":
                return []
        return unique_tools
    except Exception as exc:
        logger.warning("[CapabilityService] get_grantable_tools failed: %s", exc)
        return []


def mint_token(
    run_id: str,
    user_id: str,
    plan: Optional[dict],
    db,
    approval_mode: str,
    agent_type: str = DEFAULT_AGENT_TYPE,
) -> Optional[dict]:
    """
    Mint a scoped execution token for a run.

    The token contains:
      - execution_token: opaque UUID
      - granted_tools: legacy per-tool allowlist
      - allowed_capabilities: canonical capability claims
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

        allowed_capabilities = get_plan_required_capabilities(plan, agent_type=agent_type)
        if not allowed_capabilities:
            return None
        if approval_mode == "auto":
            tool_risks = [TOOL_REGISTRY[t]["risk"] for t in granted_tools]
            if any(get_policy_for_risk(risk) != "auto_allowed" for risk in tool_risks):
                return None

        create_run_capability_mappings(
            run_id=run_id,
            agent_type=agent_type,
            capability_names=allowed_capabilities,
            db=db,
        )

        execution_token = str(uuid.uuid4())
        issued_at = _now_utc()
        expires_at = issued_at + timedelta(hours=TOKEN_TTL_HOURS)
        issued_at_s = issued_at.isoformat()
        expires_at_s = expires_at.isoformat()

        return {
            "run_id": str(run_id),
            "user_id": str(user_id),
            "agent_type": agent_type or DEFAULT_AGENT_TYPE,
            "execution_token": execution_token,
            "issued_at": issued_at_s,
            "expires_at": expires_at_s,
            "granted_tools": granted_tools,
            "allowed_capabilities": allowed_capabilities,
            "approval_mode": approval_mode,
            "token_hash": _token_hash(
                run_id=str(run_id),
                user_id=str(user_id),
                execution_token=execution_token,
                issued_at=issued_at_s,
                expires_at=expires_at_s,
                approval_mode=approval_mode,
                granted_tools=granted_tools,
                allowed_capabilities=allowed_capabilities,
            ),
        }
    except Exception as exc:
        logger.warning("[CapabilityService] mint_token failed: %s", exc)
        return None


def validate_token(token: Optional[dict], run_id: str, user_id: str) -> dict:
    """
    Validate token structure, scope, expiry, and integrity hash.
    """
    try:
        if not isinstance(token, dict):
            return {
                "ok": False,
                "error": "missing capability token",
                "granted_tools": [],
                "allowed_capabilities": [],
            }

        token_run_id = str(token.get("run_id", ""))
        token_user_id = str(token.get("user_id", ""))
        execution_token = str(token.get("execution_token", ""))
        issued_at = token.get("issued_at")
        expires_at = token.get("expires_at")
        approval_mode = token.get("approval_mode")
        agent_type = str(token.get("agent_type") or DEFAULT_AGENT_TYPE)
        granted_tools = _normalize_tool_list(token.get("granted_tools"))
        allowed_capabilities = _normalize_capability_list(token.get("allowed_capabilities"))
        token_hash = token.get("token_hash")

        if token_run_id != str(run_id):
            return {"ok": False, "error": "token run mismatch", "granted_tools": [], "allowed_capabilities": []}
        if token_user_id != str(user_id):
            return {"ok": False, "error": "token user mismatch", "granted_tools": [], "allowed_capabilities": []}
        if not execution_token:
            return {"ok": False, "error": "missing execution token", "granted_tools": [], "allowed_capabilities": []}
        if approval_mode not in {"manual", "auto"}:
            return {"ok": False, "error": "invalid approval mode", "granted_tools": [], "allowed_capabilities": []}
        if not issued_at or not expires_at or token_hash is None:
            return {"ok": False, "error": "incomplete capability token", "granted_tools": [], "allowed_capabilities": []}

        try:
            expires_at_dt = datetime.fromisoformat(str(expires_at))
        except Exception:
            return {"ok": False, "error": "invalid token expiry", "granted_tools": [], "allowed_capabilities": []}

        if expires_at_dt.tzinfo is None:
            expires_at_dt = expires_at_dt.replace(tzinfo=timezone.utc)
        if expires_at_dt <= _now_utc():
            return {"ok": False, "error": "capability token expired", "granted_tools": [], "allowed_capabilities": []}

        expected_hash = _token_hash(
            run_id=str(run_id),
            user_id=str(user_id),
            execution_token=execution_token,
            issued_at=str(issued_at),
            expires_at=str(expires_at),
            approval_mode=approval_mode,
            granted_tools=granted_tools,
            allowed_capabilities=allowed_capabilities,
        )
        if expected_hash != token_hash:
            return {"ok": False, "error": "capability token hash mismatch", "granted_tools": [], "allowed_capabilities": []}

        return {
            "ok": True,
            "error": None,
            "granted_tools": granted_tools,
            "allowed_capabilities": allowed_capabilities,
            "execution_token": execution_token,
            "agent_type": agent_type,
        }
    except Exception as exc:
        logger.warning("[CapabilityService] validate_token failed: %s", exc)
        return {"ok": False, "error": "token validation failed", "granted_tools": [], "allowed_capabilities": []}


def check_execution_capability(
    token: Optional[dict],
    run_id: str,
    user_id: str,
    capability_name: str,
) -> dict:
    """Enforce that a token is valid and grants a named capability."""
    try:
        validation = validate_token(token=token, run_id=run_id, user_id=user_id)
        if not validation["ok"]:
            return {
                "ok": False,
                "error": validation["error"],
                "granted_tools": validation.get("granted_tools", []),
                "allowed_capabilities": validation.get("allowed_capabilities", []),
            }

        if capability_name not in validation["allowed_capabilities"]:
            return {
                "ok": False,
                "error": f"capability '{capability_name}' not granted by execution token",
                "granted_tools": validation["granted_tools"],
                "allowed_capabilities": validation["allowed_capabilities"],
            }

        return {
            "ok": True,
            "error": None,
            "granted_tools": validation["granted_tools"],
            "allowed_capabilities": validation["allowed_capabilities"],
        }
    except Exception as exc:
        logger.warning("[CapabilityService] check_execution_capability failed: %s", exc)
        return {
            "ok": False,
            "error": "capability check failed",
            "granted_tools": [],
            "allowed_capabilities": [],
        }


def check_tool_capability(
    token: Optional[dict],
    run_id: str,
    user_id: str,
    tool_name: str,
) -> dict:
    """
    Enforce that a token is valid and grants the requested tool's capability.
    """
    try:
        validation = validate_token(token=token, run_id=run_id, user_id=user_id)
        if not validation["ok"]:
            return {
                "ok": False,
                "error": validation["error"],
                "granted_tools": validation.get("granted_tools", []),
                "allowed_capabilities": validation.get("allowed_capabilities", []),
            }

        if tool_name not in validation["granted_tools"]:
            return {
                "ok": False,
                "error": f"tool '{tool_name}' not granted by capability token",
                "granted_tools": validation["granted_tools"],
                "allowed_capabilities": validation["allowed_capabilities"],
            }

        required_capabilities = _get_capabilities_for_tool(tool_name)
        for required_capability in required_capabilities:
            if required_capability not in validation["allowed_capabilities"]:
                return {
                    "ok": False,
                    "error": f"capability '{required_capability}' not granted by execution token",
                    "granted_tools": validation["granted_tools"],
                    "allowed_capabilities": validation["allowed_capabilities"],
                }

        agent_capabilities = _get_capabilities_for_agent(validation.get("agent_type") or DEFAULT_AGENT_TYPE)
        for required_capability in agent_capabilities:
            if required_capability not in validation["allowed_capabilities"]:
                return {
                    "ok": False,
                    "error": f"capability '{required_capability}' not granted by execution token",
                    "granted_tools": validation["granted_tools"],
                    "allowed_capabilities": validation["allowed_capabilities"],
                }

        if not required_capabilities and tool_name in TOOL_REGISTRY:
            return {
                "ok": False,
                "error": f"tool '{tool_name}' has no registered capability mapping",
                "granted_tools": validation["granted_tools"],
                "allowed_capabilities": validation["allowed_capabilities"],
            }

        return {
            "ok": True,
            "error": None,
            "granted_tools": validation["granted_tools"],
            "allowed_capabilities": validation["allowed_capabilities"],
        }
    except Exception as exc:
        logger.warning("[CapabilityService] check_tool_capability failed: %s", exc)
        return {
            "ok": False,
            "error": "capability check failed",
            "granted_tools": [],
            "allowed_capabilities": [],
        }
