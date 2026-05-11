"""
node_registry.py â€” Runtime external node registration.

Supports two node types:

  webhook   â€” The node POSTs state to an external HTTP endpoint and expects
              a node-contract-compliant JSON response.  The DB session and
              all internal context keys are stripped before the request so
              nothing internal leaks outside the boundary.

  plugin    â€” Dynamically imports a Python function from the restricted
              plugins/nodes/ directory.  Path traversal is blocked.  The
              import happens once at registration time; any ImportError or
              AttributeError is surfaced as a 422 before the node enters
              NODE_REGISTRY.

Node contract (both types must honour):
  fn(state: dict, context: dict) -> {
      "status": "SUCCESS" | "RETRY" | "FAILURE" | "WAIT",
      "output_patch": {...},   # optional
      "error": "...",          # on FAILURE
  }

Thread safety: _node_lock protects writes to NODE_REGISTRY and _DYNAMIC_NODE_META.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_node_lock = threading.Lock()

# Serialisable metadata for every dynamically registered node.
_DYNAMIC_NODE_META: dict[str, dict] = {}

# Valid values accepted in a node response's "status" field.
_VALID_STATUSES = frozenset(["SUCCESS", "RETRY", "FAILURE", "WAIT"])

# Maximum seconds to wait for a webhook response.
_WEBHOOK_MAX_TIMEOUT = 30

# Plugins are restricted to this directory (relative to this file's parent).
_PLUGINS_DIR = Path(__file__).parent.parent / "plugins" / "nodes"


# ---------------------------------------------------------------------------
# Webhook node factory
# ---------------------------------------------------------------------------

def _make_webhook_node(
    name: str,
    url: str,
    timeout_seconds: int,
    secret: str | None,
) -> Callable:
    """
    Return a node function that dispatches to an external HTTP endpoint.

    Request body (JSON):
        {
            "node_name": "<name>",
            "user_id":   "<str or null>",
            "flow_name": "<str or null>",
            "state":     {...}   # full node state â€” no DB objects
        }

    Expected response (JSON):
        {
            "status":       "SUCCESS" | "RETRY" | "FAILURE" | "WAIT",
            "output_patch": {...},   # optional
            "error":        "...",   # optional, included on FAILURE
            "wait_for":     "...",   # optional, included on WAIT
        }

    If the request times out, the network is unavailable, or the response
    does not match the contract, the node returns FAILURE so the flow engine
    can handle it via its normal retry / failure path.

    When a secret is provided, the request body is HMAC-SHA256 signed and
    the signature is sent as the X-AINDY-Signature header so the receiver
    can authenticate the call:
        X-AINDY-Signature: sha256=<hex_digest>
    """
    def webhook_node(state: dict, context: dict) -> dict:
        try:
            import urllib.request

            # Build a safe, serialisable payload â€” strip everything that
            # cannot cross a network boundary (db session, callables, etc.)
            safe_state = {
                k: v for k, v in state.items()
                if not callable(v) and k != "db"
            }
            body_dict = {
                "node_name": name,
                "user_id": str(context.get("user_id") or ""),
                "flow_name": str(context.get("flow_name") or context.get("workflow_type") or ""),
                "state": safe_state,
            }
            body_bytes = json.dumps(body_dict, default=str).encode("utf-8")

            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "User-Agent": "AINDY-NodeDispatcher/1.0",
            }
            if secret:
                sig = hmac.new(
                    secret.encode("utf-8"), body_bytes, hashlib.sha256
                ).hexdigest()
                headers["X-AINDY-Signature"] = f"sha256={sig}"

            req = urllib.request.Request(
                url, data=body_bytes, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")

            response = json.loads(raw)

        except Exception as exc:
            logger.warning(
                "[node_registry] webhook node %r failed: %s", name, exc
            )
            return {"status": "FAILURE", "error": f"webhook error: {exc}"}

        # Validate response contract
        status = response.get("status", "")
        if status not in _VALID_STATUSES:
            return {
                "status": "FAILURE",
                "error": f"webhook returned invalid status {status!r}",
            }

        result: dict[str, Any] = {"status": status}
        if "output_patch" in response:
            result["output_patch"] = response["output_patch"]
        if "error" in response:
            result["error"] = response["error"]
        if "wait_for" in response:
            result["wait_for"] = response["wait_for"]
        return result

    webhook_node.__name__ = name
    webhook_node.__qualname__ = f"webhook_node[{name}]"
    return webhook_node


# ---------------------------------------------------------------------------
# Plugin node loader
# ---------------------------------------------------------------------------

def _load_plugin_node(handler: str) -> Callable:
    """
    Import and return a plugin node function.

    handler format:  "module_name:function_name"
                     "subpackage.module:function_name"

    All imports are restricted to the plugins/nodes/ directory.
    Path traversal sequences (..) are rejected.

    Raises ValueError with a clear message on any import or validation error.
    """
    if ":" not in handler:
        raise ValueError(
            f"plugin handler must be 'module:function', got {handler!r}"
        )

    module_part, func_name = handler.rsplit(":", 1)

    # Block path traversal
    if ".." in module_part or module_part.startswith("."):
        raise ValueError(f"plugin handler contains illegal path component: {handler!r}")

    # Ensure plugins directory exists
    if not _PLUGINS_DIR.is_dir():
        _PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        (_PLUGINS_DIR / "__init__.py").touch()

    # Add plugins/nodes to sys.path once so relative imports work
    plugins_str = str(_PLUGINS_DIR)
    if plugins_str not in sys.path:
        sys.path.insert(0, plugins_str)

    try:
        module = importlib.import_module(module_part)
    except ImportError as exc:
        raise ValueError(f"cannot import plugin module {module_part!r}: {exc}") from exc

    # Verify the module actually lives under the plugins directory
    module_file = getattr(module, "__file__", None)
    if module_file:
        try:
            Path(module_file).resolve().relative_to(_PLUGINS_DIR.resolve())
        except ValueError:
            raise ValueError(
                f"plugin module {module_part!r} resolves outside the plugins directory"
            )

    fn = getattr(module, func_name, None)
    if fn is None:
        raise ValueError(
            f"function {func_name!r} not found in plugin module {module_part!r}"
        )
    if not callable(fn):
        raise ValueError(
            f"{module_part}:{func_name} is not callable"
        )
    return fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_external_node(
    name: str,
    node_type: str,
    handler: str,
    *,
    timeout_seconds: int = 10,
    secret: str | None = None,
    user_id: str | None = None,
    overwrite: bool = False,
    db: Session | None = None,
) -> dict[str, Any]:
    """
    Validate, build, and register an external node at runtime.

    If *db* is provided the registration is also persisted to the
    dynamic_nodes table so it survives server restarts.  Pass db=None
    when called from the startup loader (already reading from DB).

    Args:
        name:             Node name (key in NODE_REGISTRY).
        node_type:        "webhook" or "plugin".
        handler:          Webhook URL or "module:function" plugin path.
        timeout_seconds:  Webhook-only. Clamped to [1, _WEBHOOK_MAX_TIMEOUT].
        secret:           Webhook-only. HMAC-SHA256 signing secret.
        user_id:          Creator user ID for audit metadata.
        overwrite:        Replace an existing dynamic node with the same name.
        db:               Optional DB session for persistence.

    Returns the stored metadata dict.
    Raises ValueError(str) on validation or import failure.
    """
    from AINDY.runtime.flow_engine import NODE_REGISTRY, register_node

    # â”€â”€ Validate inputs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not name or not name.strip():
        raise ValueError("name must be a non-empty string")
    if node_type not in ("webhook", "plugin"):
        raise ValueError(f"type must be 'webhook' or 'plugin', got {node_type!r}")
    if not handler or not handler.strip():
        raise ValueError("handler must be a non-empty string")

    if node_type == "webhook":
        if not (handler.startswith("http://") or handler.startswith("https://")):
            raise ValueError(
                f"webhook handler must be an http:// or https:// URL, got {handler!r}"
            )
        timeout_seconds = max(1, min(int(timeout_seconds), _WEBHOOK_MAX_TIMEOUT))

    # â”€â”€ Build the node function â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if node_type == "webhook":
        node_fn = _make_webhook_node(name, handler, timeout_seconds, secret)
    else:
        node_fn = _load_plugin_node(handler)  # raises ValueError on failure

    # â”€â”€ Register (thread-safe) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    with _node_lock:
        if name in NODE_REGISTRY and not overwrite:
            raise ValueError(
                f"node {name!r} already exists in NODE_REGISTRY; set overwrite=true to replace"
            )

        # Use the engine's decorator machinery so the node participates in
        # policy enforcement and memory injection exactly like a static node.
        register_node(name)(node_fn)

        meta: dict[str, Any] = {
            "name": name,
            "type": node_type,
            "handler": handler,
            "timeout_seconds": timeout_seconds if node_type == "webhook" else None,
            "signed": secret is not None if node_type == "webhook" else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": user_id,
            "dynamic": True,
        }
        _DYNAMIC_NODE_META[name] = meta

    if db is not None:
        _persist_node(name, node_type, handler, secret=secret,
                      timeout_seconds=timeout_seconds, user_id=user_id,
                      overwrite=overwrite, db=db)

    logger.info(
        "platform: dynamic node registered: %s (type=%s)", name, node_type
    )
    return meta


def _persist_node(
    name: str,
    node_type: str,
    handler: str,
    *,
    secret: str | None,
    timeout_seconds: int,
    user_id: str | None,
    overwrite: bool,
    db: Session,
) -> None:
    """Upsert the node config into the dynamic_nodes table."""
    from AINDY.db.models.dynamic_node import DynamicNode

    if node_type == "webhook":
        handler_config: dict[str, Any] = {"url": handler, "timeout_seconds": timeout_seconds}
    else:
        handler_config = {"handler": handler}

    now = datetime.now(timezone.utc)

    try:
        existing = db.query(DynamicNode).filter(DynamicNode.name == name).first()
        if existing:
            existing.node_type = node_type
            existing.handler_config = handler_config
            existing.secret = secret
            existing.is_active = True
            existing.updated_at = now
        else:
            db.add(DynamicNode(
                id=uuid.uuid4(),
                name=name,
                node_type=node_type,
                handler_config=handler_config,
                secret=secret,
                created_by=str(user_id) if user_id else None,
                created_at=now,
                updated_at=now,
                is_active=True,
            ))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("platform: failed to persist node %r: %s", name, exc)


def list_dynamic_nodes() -> list[dict[str, Any]]:
    """Return a snapshot of all dynamically registered node metadata."""
    return list(_DYNAMIC_NODE_META.values())


def get_dynamic_node(name: str) -> dict[str, Any] | None:
    """Return metadata for one dynamic node, or None if not found."""
    return _DYNAMIC_NODE_META.get(name)


def delete_dynamic_node(name: str, *, db: Session | None = None) -> bool:
    """
    Remove a dynamic node from NODE_REGISTRY and _DYNAMIC_NODE_META.

    If *db* is provided, soft-deletes the row in dynamic_nodes (is_active=False).

    Returns True if removed, False if not found in _DYNAMIC_NODE_META.
    Static (startup-registered) nodes cannot be deleted via this function.
    """
    from AINDY.runtime.flow_engine import NODE_REGISTRY

    with _node_lock:
        if name not in _DYNAMIC_NODE_META:
            return False
        NODE_REGISTRY.pop(name, None)
        _DYNAMIC_NODE_META.pop(name, None)

    if db is not None:
        try:
            from AINDY.db.models.dynamic_node import DynamicNode
            row = db.query(DynamicNode).filter(DynamicNode.name == name).first()
            if row:
                row.is_active = False
                row.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("platform: failed to soft-delete node %r: %s", name, exc)

    logger.info("platform: dynamic node deleted: %s", name)
    return True

