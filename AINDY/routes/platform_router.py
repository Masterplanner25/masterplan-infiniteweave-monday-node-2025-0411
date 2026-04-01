"""
platform_router.py — A.I.N.D.Y. stable Platform API layer.

Layer: /platform  (runtime infrastructure — breaking changes require version bump)

This router carries its own /platform prefix and is mounted without an additional
prefix in main.py.  All endpoints here are part of the stable platform contract
intended for external integrations, tooling, and CI/CD pipelines.

Flow management
  POST   /platform/flows              — register a dynamic flow (no restart required)
  GET    /platform/flows              — list all dynamic flows
  GET    /platform/flows/{name}       — get a flow definition
  POST   /platform/flows/{name}/run   — execute any registered flow by name
  DELETE /platform/flows/{name}       — remove a dynamic flow

Node management
  POST   /platform/nodes/register     — register a webhook or plugin node
  GET    /platform/nodes              — list all dynamic nodes
  GET    /platform/nodes/{name}       — get a node definition
  DELETE /platform/nodes/{name}       — remove a dynamic node

Webhook subscriptions
  POST   /platform/webhooks           — subscribe to a SystemEvent type
  GET    /platform/webhooks           — list active subscriptions
  GET    /platform/webhooks/{id}      — get subscription details
  DELETE /platform/webhooks/{id}      — cancel a subscription

API key management
  POST   /platform/keys               — create a scoped API key (plaintext returned once)
  GET    /platform/keys               — list caller's keys (prefix/scopes/stats)
  GET    /platform/keys/{id}          — get single key metadata
  DELETE /platform/keys/{id}          — revoke a key

Stability contract
  — Simple edges only (node_name → [next_node_name]) are supported via API.
  — Condition functions cannot be serialised over HTTP; use startup-registered flows.
  — All business logic routes through run_flow() per the HARD EXECUTION BOUNDARY.
  — Registry CRUD (flows/nodes) calls services.flow_registry directly (infra ops).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.execution_helper import execute_with_pipeline_sync
from db.database import get_db
from services.auth_service import get_current_user

router = APIRouter(
    prefix="/platform",
    tags=["Platform"],
    dependencies=[Depends(get_current_user)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class FlowDefinition(BaseModel):
    name: str = Field(..., description="Unique flow name — used as the key in run_flow()")
    nodes: List[str] = Field(..., min_length=1, description="Node names — all must exist in NODE_REGISTRY")
    edges: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Simple edges: {source_node: [target_node, ...]}",
    )
    start: str = Field(..., description="Entry-point node name")
    end: List[str] = Field(..., min_length=1, description="Terminal node names")
    overwrite: bool = Field(False, description="Replace an existing dynamic flow with the same name")


class FlowRunRequest(BaseModel):
    state: Dict[str, Any] = Field(default_factory=dict, description="Initial state passed to the flow")


class NodeRegistration(BaseModel):
    name: str = Field(..., description="Unique node name — used as the key in NODE_REGISTRY")
    type: str = Field(..., description="'webhook' or 'plugin'")
    handler: str = Field(
        ...,
        description=(
            "For webhook: https://... URL that receives POST {node_name, user_id, flow_name, state} "
            "and returns {status, output_patch}. "
            "For plugin: 'module:function' path relative to plugins/nodes/ directory."
        ),
    )
    timeout_seconds: int = Field(
        10,
        ge=1,
        le=30,
        description="Webhook only — max seconds to wait for a response",
    )
    secret: Optional[str] = Field(
        None,
        description="Webhook only — HMAC-SHA256 signing secret sent as X-AINDY-Signature header",
    )
    overwrite: bool = Field(False, description="Replace an existing dynamic node with the same name")


class WebhookSubscription(BaseModel):
    event_type: str = Field(
        ...,
        description=(
            "SystemEvent type to subscribe to. "
            "Supports exact match ('execution.completed'), "
            "prefix wildcard ('execution.*'), "
            "or global wildcard ('*')."
        ),
    )
    callback_url: str = Field(..., description="https:// URL that receives POST {event_id, event_type, payload, ...}")
    secret: Optional[str] = Field(
        None,
        description="Optional HMAC-SHA256 signing secret — delivered as X-AINDY-Signature: sha256=<hex>",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_flow_platform(flow_name: str, state: dict, db: Session, user_id: str | None) -> dict:
    from services.flow_engine import run_flow
    result = run_flow(flow_name, state, db=db, user_id=user_id)
    if result.get("status") == "FAILED":
        error = result.get("error", "")
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail=msg)
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")
    # Return full execution envelope for dynamic flows — caller sees status, data,
    # run_id, trace_id.  _extract_execution_result returns the full final state for
    # unknown flow names, which is the most useful response for dynamic callers.
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/flows", status_code=201)
def create_flow(
    body: FlowDefinition,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Register a new dynamic flow into the live FLOW_REGISTRY.

    No application restart required.  Thread-safe.  Persisted to DB.
    All listed nodes must already exist in NODE_REGISTRY.
    """
    from services.flow_registry import register_dynamic_flow

    user_id = str(current_user["sub"])
    try:
        meta = register_dynamic_flow(
            name=body.name,
            nodes=body.nodes,
            edges=body.edges,
            start=body.start,
            end=body.end,
            user_id=user_id,
            overwrite=body.overwrite,
            db=db,
        )
    except ValueError as exc:
        errors = exc.args[0]
        raise HTTPException(
            status_code=422,
            detail={"errors": errors if isinstance(errors, list) else [str(errors)]},
        )
    return meta


@router.get("/flows")
def list_flows(
    current_user: dict = Depends(get_current_user),
):
    """List all dynamically registered platform flows."""
    from services.flow_registry import list_dynamic_flows
    return {"flows": list_dynamic_flows()}


@router.get("/flows/{name}")
def get_flow(
    name: str,
    current_user: dict = Depends(get_current_user),
):
    """Return the definition of a dynamic flow."""
    from services.flow_registry import get_dynamic_flow
    meta = get_dynamic_flow(name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Flow {name!r} not found")
    return meta


@router.post("/flows/{name}/run")
def run_flow_endpoint(
    request: Request,
    name: str,
    body: FlowRunRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Execute any registered flow (dynamic or static) by name.

    Returns the full execution envelope:
      { "status": "SUCCESS"|"FAILED", "data": <final_state>, "run_id": ..., "trace_id": ... }
    """
    from services.flow_engine import FLOW_REGISTRY

    user_id = str(current_user["sub"])
    if name not in FLOW_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Flow {name!r} is not registered")

    def handler(_ctx):
        return _run_flow_platform(name, body.state, db, user_id)

    return execute_with_pipeline_sync(
        request=request,
        route_name=f"platform.flows.run",
        handler=handler,
        user_id=user_id,
        input_payload={"flow_name": name, **body.state},
        metadata={"db": db},
    )


@router.delete("/flows/{name}", status_code=204)
def delete_flow(
    name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Remove a dynamically registered flow from the live FLOW_REGISTRY.

    Static (startup-registered) flows cannot be deleted via this endpoint.
    Returns 204 on success, 404 if not found or not a dynamic flow.
    """
    from services.flow_registry import delete_dynamic_flow
    removed = delete_dynamic_flow(name, db=db)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"Flow {name!r} not found or is a static flow (only dynamic flows can be deleted)",
        )
    return None


# ---------------------------------------------------------------------------
# Node endpoints
# ---------------------------------------------------------------------------

@router.post("/nodes/register", status_code=201)
def register_node(
    body: NodeRegistration,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Register an external node into the live NODE_REGISTRY.

    Two types are supported:

    **webhook** — The node POSTs `{node_name, user_id, flow_name, state}` to
    the handler URL and expects `{status, output_patch}` back.  The DB session
    and all internal context keys are never exposed to the external service.
    Requests are optionally HMAC-signed (X-AINDY-Signature header).

    **plugin** — Imports `function` from `module` inside the `plugins/nodes/`
    directory.  The function must accept `(state, context)` and return a
    node-contract-compliant dict.  Path traversal is blocked.

    No application restart required.  Thread-safe.  Persisted to DB.
    """
    from services.node_registry import register_external_node

    user_id = str(current_user["sub"])
    try:
        meta = register_external_node(
            name=body.name,
            node_type=body.type,
            handler=body.handler,
            timeout_seconds=body.timeout_seconds,
            secret=body.secret,
            user_id=user_id,
            overwrite=body.overwrite,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})
    return meta


@router.get("/nodes")
def list_nodes(
    current_user: dict = Depends(get_current_user),
):
    """List all dynamically registered platform nodes."""
    from services.node_registry import list_dynamic_nodes
    return {"nodes": list_dynamic_nodes()}


@router.get("/nodes/{name}")
def get_node(
    name: str,
    current_user: dict = Depends(get_current_user),
):
    """Return the metadata for a dynamic node."""
    from services.node_registry import get_dynamic_node
    meta = get_dynamic_node(name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Node {name!r} not found")
    return meta


@router.delete("/nodes/{name}", status_code=204)
def delete_node(
    name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Remove a dynamically registered node from NODE_REGISTRY.

    Static (startup-registered) nodes cannot be deleted via this endpoint.
    """
    from services.node_registry import delete_dynamic_node
    removed = delete_dynamic_node(name, db=db)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"Node {name!r} not found or is a static node (only dynamic nodes can be deleted)",
        )
    return None


# ---------------------------------------------------------------------------
# Webhook subscription endpoints
# ---------------------------------------------------------------------------

@router.post("/webhooks", status_code=201)
def create_webhook(
    body: WebhookSubscription,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Subscribe to a SystemEvent type.

    A.I.N.D.Y. will POST a JSON payload to your callback_url whenever a
    matching event is emitted.  Delivery is asynchronous (background thread),
    retried up to 3 times with exponential back-off (1 s → 2 s → 4 s), and
    never blocks the originating request.

    **Payload sent to callback_url:**
    ```json
    {
      "event_id":               "<uuid>",
      "event_type":             "execution.completed",
      "timestamp":              "<iso8601>",
      "user_id":                "<uuid or null>",
      "trace_id":               "<str or null>",
      "source":                 "<str or null>",
      "payload":                {...},
      "aindy_subscription_id":  "<subscription uuid>"
    }
    ```

    When a `secret` is provided, the request is signed:
    `X-AINDY-Signature: sha256=<hex>` — compute `HMAC-SHA256(secret, body)`
    to verify authenticity.

    **Wildcard patterns:**
    - `"execution.*"` — all events starting with `"execution."`
    - `"*"`           — every SystemEvent
    """
    from services.event_service import subscribe_webhook

    user_id = str(current_user["sub"])
    try:
        meta = subscribe_webhook(
            event_type=body.event_type,
            callback_url=body.callback_url,
            secret=body.secret,
            user_id=user_id,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})
    return meta


@router.get("/webhooks")
def list_webhook_subscriptions(
    current_user: dict = Depends(get_current_user),
):
    """List all webhook subscriptions for the current user."""
    from services.event_service import list_webhooks
    user_id = str(current_user["sub"])
    return {"webhooks": list_webhooks(user_id=user_id)}


@router.get("/webhooks/{subscription_id}")
def get_webhook_subscription(
    subscription_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return details for a single webhook subscription."""
    from services.event_service import get_webhook
    meta = get_webhook(subscription_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id!r} not found")
    # Ownership check — users can only inspect their own subscriptions
    if meta.get("created_by") != str(current_user["sub"]):
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id!r} not found")
    return meta


@router.delete("/webhooks/{subscription_id}", status_code=204)
def delete_webhook_subscription(
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cancel a webhook subscription."""
    from services.event_service import get_webhook, unsubscribe_webhook
    meta = get_webhook(subscription_id)
    if not meta or meta.get("created_by") != str(current_user["sub"]):
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id!r} not found")
    unsubscribe_webhook(subscription_id, db=db)
    return None


# ---------------------------------------------------------------------------
# API key schemas
# ---------------------------------------------------------------------------

class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Human-readable label for this key")
    scopes: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "Capability scopes granted to this key. "
            "Valid values: flow.read, flow.execute, memory.read, memory.write, "
            "agent.run, webhook.manage, platform.admin"
        ),
    )
    expires_at: Optional[str] = Field(
        None,
        description="ISO 8601 expiry datetime (UTC).  Omit for non-expiring keys.",
    )


# ---------------------------------------------------------------------------
# API key endpoints
# ---------------------------------------------------------------------------

@router.post("/keys", status_code=201)
def create_key(
    body: APIKeyCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new platform API key for the authenticated user.

    **The plaintext key is returned exactly once in the response — it cannot
    be recovered later.  Store it immediately.**

    Response includes `key` (full plaintext) alongside the metadata record.
    Subsequent `GET /platform/keys` calls show only `key_prefix` (first 16 chars).
    """
    from auth.api_key_auth import Scopes
    from services.api_key_service import create_api_key
    from datetime import datetime, timezone

    user_id = str(current_user["sub"])

    # Validate requested scopes
    invalid = [s for s in body.scopes if s not in Scopes.ALL]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail={"error": f"Unknown scopes: {invalid}. Valid: {Scopes.ALL}"},
        )

    expires_at = None
    if body.expires_at:
        try:
            expires_at = datetime.fromisoformat(body.expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={"error": "expires_at must be a valid ISO 8601 datetime string"},
            )

    record, raw_key = create_api_key(
        user_id=user_id,
        name=body.name,
        scopes=body.scopes,
        db=db,
        expires_at=expires_at,
    )

    return {
        "key": raw_key,           # ← one-time plaintext delivery
        "id": str(record.id),
        "name": record.name,
        "key_prefix": record.key_prefix,
        "scopes": list(record.scopes or []),
        "is_active": record.is_active,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.get("/keys")
def list_keys(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all API keys owned by the current user (no plaintext, shows prefix/scopes/stats)."""
    from services.api_key_service import list_api_keys
    user_id = str(current_user["sub"])
    return {"keys": list_api_keys(user_id=user_id, db=db)}


@router.get("/keys/{key_id}")
def get_key(
    key_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return metadata for a single API key.  Ownership-enforced."""
    from services.api_key_service import get_api_key
    user_id = str(current_user["sub"])
    meta = get_api_key(key_id=key_id, user_id=user_id, db=db)
    if not meta:
        raise HTTPException(status_code=404, detail=f"API key {key_id!r} not found")
    return meta


@router.delete("/keys/{key_id}", status_code=204)
def revoke_key(
    key_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Revoke an API key.  Sets revoked_at and deactivates the key immediately.

    Returns 204 on success, 404 if not found or not owned by the current user.
    """
    from services.api_key_service import revoke_api_key
    user_id = str(current_user["sub"])
    revoked = revoke_api_key(key_id=key_id, user_id=user_id, db=db)
    if not revoked:
        raise HTTPException(status_code=404, detail=f"API key {key_id!r} not found")
    return None
