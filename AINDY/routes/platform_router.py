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

Nodus script execution
  POST   /platform/nodus/run          — execute an inline Nodus script via flow engine
  POST   /platform/nodus/upload       — upload and register a named Nodus script
  GET    /platform/nodus/scripts      — list uploaded scripts

Nodus flow execution
  POST   /platform/nodus/flow         — compile a Nodus flow script and optionally run it

Nodus scheduled execution
  POST   /platform/nodus/schedule     — create a cron-scheduled Nodus job
  GET    /platform/nodus/schedule     — list the caller's scheduled jobs
  DELETE /platform/nodus/schedule/{id} — cancel a scheduled job

Nodus execution trace
  GET    /platform/nodus/trace/{id}   — full host-function call trace for an execution

Tenant resource visibility (OS layer)
  GET    /platform/tenants/{id}/usage — active executions, resource usage, quota limits

SDK syscall dispatch
  POST   /platform/syscall             — execute any registered syscall by name (SDK entry point)

Stability contract
  — Simple edges only (node_name → [next_node_name]) are supported via API.
  — Condition functions cannot be serialised over HTTP; use startup-registered flows.
  — All business logic routes through run_flow() per the HARD EXECUTION BOUNDARY.
  — Registry CRUD (flows/nodes) calls runtime.flow_registry directly (infra ops).
  — Nodus scripts are sandboxed: no imports, eval, exec, filesystem or network access.
"""
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import get_current_user

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


class NodusRunRequest(BaseModel):
    script: Optional[str] = Field(
        None,
        description="Inline Nodus source code.  Mutually exclusive with script_name.",
    )
    script_name: Optional[str] = Field(
        None,
        description="Name of a previously uploaded script (POST /platform/nodus/upload).",
    )
    input: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input payload exposed as the `input_payload` global inside the script.",
    )
    error_policy: str = Field(
        "fail",
        description=(
            "'fail' (default) — script error is returned as nodus_status='failure' in the response. "
            "'retry' — the flow engine retries up to max_retries before surfacing the error."
        ),
    )

    @model_validator(mode="after")
    def _require_source(self) -> "NodusRunRequest":
        if not self.script and not self.script_name:
            raise ValueError(
                "Provide either 'script' (inline source) or 'script_name' (uploaded script name)"
            )
        if self.script and self.script_name:
            raise ValueError("Provide 'script' or 'script_name', not both")
        if self.error_policy not in ("fail", "retry"):
            raise ValueError("error_policy must be 'fail' or 'retry'")
        return self


class NodusScriptUpload(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-\.]+$",
        description="Unique script name — alphanumeric, hyphens, underscores, dots.",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Nodus source code.  Subject to the same sandbox restrictions as inline scripts.",
    )
    description: Optional[str] = Field(None, max_length=512)
    overwrite: bool = Field(False, description="Replace an existing script with the same name.")


class NodusFlowRequest(BaseModel):
    flow_name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description=(
            "Logical name for the compiled flow.  Used as the FLOW_REGISTRY key "
            "when ``register=true``."
        ),
    )
    script: str = Field(
        ...,
        min_length=1,
        description=(
            "Nodus source code that defines flow routing via ``flow.step()``. "
            "Example: ``flow.step('fetch_data')\\nflow.step('analyze', when='ready')``"
        ),
    )
    input: Dict[str, Any] = Field(
        default_factory=dict,
        description="Initial state passed to the compiled flow when ``run=true``.",
    )
    register: bool = Field(
        False,
        description=(
            "When true, registers the compiled flow in FLOW_REGISTRY so it can "
            "be executed later via POST /platform/flows/{name}/run."
        ),
    )
    run: bool = Field(
        True,
        description="When true (default), executes the compiled flow immediately.",
    )


class NodusScheduleRequest(BaseModel):
    script: Optional[str] = Field(
        None,
        description="Inline Nodus source code.  Mutually exclusive with script_name.",
    )
    script_name: Optional[str] = Field(
        None,
        description=(
            "Name of a previously uploaded script (POST /platform/nodus/upload).  "
            "The script content is copied at creation time so the job is "
            "self-contained and independent of the script registry."
        ),
    )
    cron: str = Field(
        ...,
        description=(
            "Standard 5-field cron expression (UTC). "
            "Examples: '0 10 * * *' (daily 10:00), '*/15 * * * *' (every 15 min), "
            "'0 9 * * 1-5' (weekdays 09:00)."
        ),
    )
    input: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input payload exposed as ``input_payload`` global inside the script.",
    )
    job_name: Optional[str] = Field(
        None,
        max_length=256,
        description="Human-readable label for this job (optional).",
    )
    error_policy: str = Field(
        "fail",
        description=(
            "'fail' (default) — script errors end the run immediately. "
            "'retry' — the flow engine retries the nodus.execute node up to "
            "max_retries times with exponential back-off."
        ),
    )
    max_retries: int = Field(
        3,
        ge=1,
        le=10,
        description="Maximum retries when error_policy='retry'.",
    )

    @model_validator(mode="after")
    def _require_source(self) -> "NodusScheduleRequest":
        if not self.script and not self.script_name:
            raise ValueError(
                "Provide either 'script' (inline source) or "
                "'script_name' (uploaded script name)"
            )
        if self.script and self.script_name:
            raise ValueError("Provide 'script' or 'script_name', not both")
        if self.error_policy not in ("fail", "retry"):
            raise ValueError("error_policy must be 'fail' or 'retry'")
        return self


# ---------------------------------------------------------------------------
# Nodus script registry  (in-memory; survives within a server process)
# ---------------------------------------------------------------------------

_script_lock = threading.Lock()
_NODUS_SCRIPT_REGISTRY: Dict[str, Dict[str, Any]] = {}

# Uploaded scripts are also persisted to this directory so they survive a
# process restart (best-effort; directory created on first upload).
_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts" / "nodus"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_flow_platform(flow_name: str, state: dict, db: Session, user_id: str | None) -> dict:
    from AINDY.runtime.flow_engine import run_flow
    from AINDY.core.execution_gate import flow_result_to_envelope
    result = run_flow(flow_name, state, db=db, user_id=user_id)
    if result.get("status") == "FAILED":
        error = result.get("error", "")
        if error.startswith("HTTP_"):
            parts = error.split(":", 1)
            code = int(parts[0].replace("HTTP_", ""))
            msg = parts[1] if len(parts) > 1 else error
            raise HTTPException(status_code=code, detail=msg)
        raise HTTPException(status_code=500, detail=error or f"{flow_name} failed")
    # Embed execution_envelope so callers get the canonical shape alongside the
    # full flow result (status, data, run_id, trace_id remain unchanged).
    result.setdefault("execution_envelope", flow_result_to_envelope(result))
    return result


def _ensure_nodus_flow_registered() -> None:
    """
    Register NODUS_SCRIPT_FLOW into FLOW_REGISTRY on first call.

    Also imports nodus_adapter to ensure the flow nodes (nodus.execute,
    nodus_record_outcome, nodus_handle_error) are in NODE_REGISTRY.
    Thread-safe; idempotent.
    """
    from AINDY.runtime.nodus_execution_service import ensure_nodus_script_flow_registered

    ensure_nodus_script_flow_registered()


def _run_nodus_script(
    *,
    script: str,
    input_payload: dict,
    error_policy: str,
    db: Session,
    user_id: str,
) -> dict:
    """
    Execute a Nodus script via PersistentFlowRunner(NODUS_SCRIPT_FLOW).

    Returns the raw flow result dict — caller is responsible for formatting.
    Never raises on script-level failures (those become nodus_status="failure"
    in the returned state).  May raise HTTPException on infrastructure failure
    (VM not installed, DB unreachable, etc.).
    """
    from AINDY.runtime.nodus_execution_service import run_nodus_script_via_flow

    return run_nodus_script_via_flow(
        script=script,
        input_payload=input_payload,
        error_policy=error_policy,
        db=db,
        user_id=user_id,
    )


def _format_nodus_response(flow_result: dict) -> dict:
    """
    Extract Nodus-specific fields from a NODUS_SCRIPT_FLOW result and return
    a clean, stable API response.

    Fields
    ------
    status              "SUCCESS" | "FAILED"  — flow-level outcome
    trace_id            str — correlates all events from this execution
    run_id              str — identifies the FlowRun row
    nodus_status        "success" | "failure" — script-level outcome
    output_state        dict — set_state() mutations made inside the script
    events              list — emit() calls made inside the script
    memory_writes       list — remember() calls made inside the script
    events_emitted      int
    memory_writes_count int
    error               str | None — script error message (if nodus_status="failure")
    """
    from AINDY.runtime.nodus_execution_service import format_nodus_flow_result

    return format_nodus_flow_result(flow_result)


def _validate_nodus_source(source: str, field: str = "script") -> None:
    """
    Run nodus_security sandbox checks.  Raises HTTPException(422) on violation.
    """
    from AINDY.runtime.nodus_security import NodusSecurityError, validate_nodus_source
    try:
        validate_nodus_source(source)
    except NodusSecurityError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "nodus_security_violation", "message": str(exc), "field": field},
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/flows",
    status_code=201,
    summary="Create Dynamic Flow",
    description="Registers a dynamic flow from the posted flow definition. Returns the persisted flow metadata used by the platform registry.",
    response_model=None,
)
@limiter.limit("30/minute")
def create_flow(
    request: Request,
    body: FlowDefinition,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Register a new dynamic flow into the live FLOW_REGISTRY.

    No application restart required.  Thread-safe.  Persisted to DB.
    All listed nodes must already exist in NODE_REGISTRY.
    """
    from AINDY.runtime.flow_registry import register_dynamic_flow

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


@router.get(
    "/flows",
    summary="List Dynamic Flows",
    description="Returns all dynamically registered platform flows. The response includes flow metadata currently available in the live registry.",
    response_model=None,
)
@limiter.limit("60/minute")
def list_flows(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """List all dynamically registered platform flows."""
    from AINDY.runtime.flow_registry import list_dynamic_flows
    return {"flows": list_dynamic_flows()}


@router.get(
    "/flows/{name}",
    summary="Get Dynamic Flow",
    description="Looks up a dynamic flow by its name path parameter. Returns the stored flow definition for that registered flow.",
    response_model=None,
)
@limiter.limit("60/minute")
def get_flow(
    request: Request,
    name: str,
    current_user: dict = Depends(get_current_user),
):
    """Return the definition of a dynamic flow."""
    from AINDY.runtime.flow_registry import get_dynamic_flow
    meta = get_dynamic_flow(name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Flow {name!r} not found")
    return meta


@router.post(
    "/flows/{name}/run",
    summary="Run Registered Flow",
    description="Executes the named flow using the request state payload. Returns the full execution result for that flow run.",
    response_model=None,
)
@limiter.limit("30/minute")
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
    from AINDY.runtime.flow_engine import FLOW_REGISTRY

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


@router.delete(
    "/flows/{name}",
    status_code=204,
    summary="Delete Dynamic Flow",
    description="Removes the named dynamic flow from the platform registry. Returns no body when the flow is deleted successfully.",
    response_model=None,
)
@limiter.limit("30/minute")
def delete_flow(
    request: Request,
    name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Remove a dynamically registered flow from the live FLOW_REGISTRY.

    Static (startup-registered) flows cannot be deleted via this endpoint.
    Returns 204 on success, 404 if not found or not a dynamic flow.
    """
    from AINDY.runtime.flow_registry import delete_dynamic_flow
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

@router.post(
    "/nodes/register",
    status_code=201,
    summary="Register Dynamic Node",
    description="Registers a webhook or plugin node from the posted node definition. Returns the persisted node metadata for the new registry entry.",
    response_model=None,
)
@limiter.limit("30/minute")
def register_node(
    request: Request,
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
    from AINDY.platform_layer.node_registry import register_external_node

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


@router.get(
    "/nodes",
    summary="List Dynamic Nodes",
    description="Returns all dynamically registered platform nodes. The response includes each node definition currently available in the live registry.",
    response_model=None,
)
@limiter.limit("60/minute")
def list_nodes(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """List all dynamically registered platform nodes."""
    from AINDY.platform_layer.node_registry import list_dynamic_nodes
    return {"nodes": list_dynamic_nodes()}


@router.get(
    "/nodes/{name}",
    summary="Get Dynamic Node",
    description="Looks up a dynamic node by its name path parameter. Returns the stored node metadata for that registry entry.",
    response_model=None,
)
@limiter.limit("60/minute")
def get_node(
    request: Request,
    name: str,
    current_user: dict = Depends(get_current_user),
):
    """Return the metadata for a dynamic node."""
    from AINDY.platform_layer.node_registry import get_dynamic_node
    meta = get_dynamic_node(name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Node {name!r} not found")
    return meta


@router.delete(
    "/nodes/{name}",
    status_code=204,
    summary="Delete Dynamic Node",
    description="Removes the named dynamic node from the platform registry. Returns no body when the node is deleted successfully.",
    response_model=None,
)
@limiter.limit("30/minute")
def delete_node(
    request: Request,
    name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Remove a dynamically registered node from NODE_REGISTRY.

    Static (startup-registered) nodes cannot be deleted via this endpoint.
    """
    from AINDY.platform_layer.node_registry import delete_dynamic_node
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

@router.post(
    "/webhooks",
    status_code=201,
    summary="Create Webhook Subscription",
    description="Creates a webhook subscription from the posted event type and callback URL. Returns the stored subscription metadata for the new webhook.",
    response_model=None,
)
@limiter.limit("30/minute")
def create_webhook(
    request: Request,
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
    from AINDY.platform_layer.event_service import subscribe_webhook

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


@router.get(
    "/webhooks",
    summary="List Webhook Subscriptions",
    description="Returns all active webhook subscriptions owned by the caller. The response includes subscription metadata and delivery settings.",
    response_model=None,
)
@limiter.limit("60/minute")
def list_webhook_subscriptions(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """List all webhook subscriptions for the current user."""
    from AINDY.platform_layer.event_service import list_webhooks
    user_id = str(current_user["sub"])
    return {"webhooks": list_webhooks(user_id=user_id)}


@router.get(
    "/webhooks/{subscription_id}",
    summary="Get Webhook Subscription",
    description="Looks up a webhook subscription by its subscription ID path parameter. Returns the stored metadata for that subscription.",
    response_model=None,
)
@limiter.limit("60/minute")
def get_webhook_subscription(
    request: Request,
    subscription_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return details for a single webhook subscription."""
    from AINDY.platform_layer.event_service import get_webhook
    meta = get_webhook(subscription_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id!r} not found")
    # Ownership check — users can only inspect their own subscriptions
    if meta.get("created_by") != str(current_user["sub"]):
        raise HTTPException(status_code=404, detail=f"Subscription {subscription_id!r} not found")
    return meta


@router.delete(
    "/webhooks/{subscription_id}",
    status_code=204,
    summary="Delete Webhook Subscription",
    description="Cancels the webhook subscription identified by the path parameter. Returns no body when the subscription is deleted successfully.",
    response_model=None,
)
@limiter.limit("30/minute")
def delete_webhook_subscription(
    request: Request,
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cancel a webhook subscription."""
    from AINDY.platform_layer.event_service import get_webhook, unsubscribe_webhook
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

@router.post(
    "/keys",
    status_code=201,
    summary="Create Platform Key",
    description="Creates a scoped platform API key from the posted name, scopes, and optional expiry. Returns key metadata plus the plaintext key exactly once.",
    response_model=None,
)
@limiter.limit("10/minute")
def create_key(
    request: Request,
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
    from AINDY.auth.api_key_auth import Scopes
    from AINDY.platform_layer.api_key_service import create_api_key
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


@router.get(
    "/keys",
    summary="List Platform Keys",
    description="Returns all platform API keys owned by the caller. The response includes key metadata, scopes, and usage details without the plaintext key.",
    response_model=None,
)
@limiter.limit("60/minute")
def list_keys(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all API keys owned by the current user (no plaintext, shows prefix/scopes/stats)."""
    from AINDY.platform_layer.api_key_service import list_api_keys
    user_id = str(current_user["sub"])
    return {"keys": list_api_keys(user_id=user_id, db=db)}


@router.get(
    "/keys/{key_id}",
    summary="Get Platform Key",
    description="Looks up a platform API key by its key ID path parameter. Returns the stored metadata for that key without the plaintext value.",
    response_model=None,
)
@limiter.limit("60/minute")
def get_key(
    request: Request,
    key_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return metadata for a single API key.  Ownership-enforced."""
    from AINDY.platform_layer.api_key_service import get_api_key
    user_id = str(current_user["sub"])
    meta = get_api_key(key_id=key_id, user_id=user_id, db=db)
    if not meta:
        raise HTTPException(status_code=404, detail=f"API key {key_id!r} not found")
    return meta


@router.delete(
    "/keys/{key_id}",
    status_code=204,
    summary="Delete Platform Key",
    description="Revokes the platform API key identified by the path parameter. Returns no body when the key is deleted successfully.",
    response_model=None,
)
@limiter.limit("30/minute")
def revoke_key(
    request: Request,
    key_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Revoke an API key.  Sets revoked_at and deactivates the key immediately.

    Returns 204 on success, 404 if not found or not owned by the current user.
    """
    from AINDY.platform_layer.api_key_service import revoke_api_key
    user_id = str(current_user["sub"])
    revoked = revoke_api_key(key_id=key_id, user_id=user_id, db=db)
    if not revoked:
        raise HTTPException(status_code=404, detail=f"API key {key_id!r} not found")
    return None


# ---------------------------------------------------------------------------
# Nodus script execution endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/nodus/run",
    summary="Run Nodus Script",
    description="Executes either inline Nodus source or an uploaded script name with the posted input payload. Returns the Nodus execution result and output state.",
    response_model=None,
)
@limiter.limit("30/minute")
def run_nodus_script(
    request: Request,
    body: NodusRunRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Execute a Nodus script via the flow engine.

    The script is sandboxed — no imports, eval, exec, filesystem, or network
    access are permitted.  Violations are rejected with HTTP 422 before the VM
    is even started.

    **Inline execution** (`script` field):
    ```json
    {
      "script": "let result = input_payload[\\"value\\"] * 2\\nset_state(\\"result\\", result)\\nemit(\\"doubled\\", {value: result})",
      "input": {"value": 21},
      "error_policy": "fail"
    }
    ```

    **Named script execution** (`script_name` field — must be uploaded first):
    ```json
    { "script_name": "my_processor", "input": {"objective": "Q2 growth"} }
    ```

    **Response**
    ```json
    {
      "status":              "SUCCESS",
      "trace_id":            "<uuid>",
      "run_id":              "<uuid>",
      "nodus_status":        "success",
      "output_state":        {"result": 42},
      "events":              [{"event_type": "doubled", "payload": {"value": 42}}],
      "memory_writes":       [],
      "events_emitted":      1,
      "memory_writes_count": 0,
      "error":               null
    }
    ```

    **error_policy**
    - `"fail"` (default) — script errors are returned as `nodus_status="failure"` with
      the error message in `error`.  The HTTP status is always 200.
    - `"retry"` — the flow engine retries up to `max_retries` (3) times before treating
      the failure as final.  Useful for transient VM errors.
    """
    user_id = str(current_user["sub"])

    # Resolve source — inline script or named upload
    if body.script:
        script_source = body.script
        _validate_nodus_source(script_source, field="script")
    else:
        with _script_lock:
            record = _NODUS_SCRIPT_REGISTRY.get(body.script_name)  # type: ignore[arg-type]
        if not record:
            # Try restoring from disk before giving up
            disk_path = _SCRIPTS_DIR / f"{body.script_name}.nodus"
            if disk_path.exists():
                script_source = disk_path.read_text(encoding="utf-8")
                with _script_lock:
                    _NODUS_SCRIPT_REGISTRY[body.script_name] = {  # type: ignore[index]
                        "name": body.script_name,
                        "content": script_source,
                        "restored_from_disk": True,
                        "uploaded_at": None,
                        "uploaded_by": None,
                    }
            else:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "script_not_found",
                        "message": (
                            f"Script {body.script_name!r} not found. "
                            "Upload it first via POST /platform/nodus/upload."
                        ),
                    },
                )
        else:
            script_source = record["content"]

    def handler(_ctx):
        from AINDY.core.execution_gate import flow_result_to_envelope
        flow_result = _run_nodus_script(
            script=script_source,
            input_payload=body.input,
            error_policy=body.error_policy,
            db=db,
            user_id=user_id,
        )
        formatted = _format_nodus_response(flow_result)
        formatted.setdefault("execution_envelope", flow_result_to_envelope(flow_result))
        return formatted

    return execute_with_pipeline_sync(
        request=request,
        route_name="platform.nodus.run",
        handler=handler,
        user_id=user_id,
        input_payload={
            "script_name": body.script_name,
            "has_inline_script": bool(body.script),
            "error_policy": body.error_policy,
            **body.input,
        },
        metadata={"db": db},
    )


@router.post(
    "/nodus/upload",
    status_code=201,
    summary="Upload Nodus Script",
    description="Stores a named Nodus script from the posted script content. Returns the registered script metadata for future executions.",
    response_model=None,
)
@limiter.limit("30/minute")
def upload_nodus_script(
    request: Request,
    body: NodusScriptUpload,
    current_user: dict = Depends(get_current_user),
):
    """
    Upload and register a named Nodus script for repeated execution.

    The script is validated against the same sandbox rules as inline scripts
    (no imports, eval, exec, filesystem, or network access).

    After upload, execute it with:
    ```json
    POST /platform/nodus/run
    {"script_name": "<name>", "input": {...}}
    ```

    Scripts are persisted to `scripts/nodus/<name>.nodus` on disk and kept
    in memory for the lifetime of the server process.  Set `overwrite=true`
    to replace an existing script with the same name.

    **Response**
    ```json
    {
      "name":        "my_processor",
      "description": "Processes goals",
      "size_bytes":  128,
      "uploaded_at": "2026-03-31T12:00:00Z",
      "uploaded_by": "<user_id>"
    }
    ```
    """
    user_id = str(current_user["sub"])
    _validate_nodus_source(body.content, field="content")

    with _script_lock:
        if body.name in _NODUS_SCRIPT_REGISTRY and not body.overwrite:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "script_already_exists",
                    "message": (
                        f"Script {body.name!r} already exists. "
                        "Set overwrite=true to replace it."
                    ),
                },
            )

        # Persist to disk (best-effort; in-memory registry is the source of truth)
        try:
            _SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            script_path = _SCRIPTS_DIR / f"{body.name}.nodus"
            script_path.write_text(body.content, encoding="utf-8")
        except OSError:
            # Non-fatal — the script is still usable from the in-memory registry
            pass

        now = datetime.now(timezone.utc).isoformat()
        meta: Dict[str, Any] = {
            "name": body.name,
            "content": body.content,
            "description": body.description,
            "size_bytes": len(body.content.encode("utf-8")),
            "uploaded_at": now,
            "uploaded_by": user_id,
        }
        _NODUS_SCRIPT_REGISTRY[body.name] = meta

    return {
        "name": meta["name"],
        "description": meta["description"],
        "size_bytes": meta["size_bytes"],
        "uploaded_at": meta["uploaded_at"],
        "uploaded_by": meta["uploaded_by"],
    }


@router.get(
    "/nodus/scripts",
    summary="List Nodus Scripts",
    description="Returns the uploaded Nodus scripts currently available to the platform. The response includes script metadata without the full source body.",
    response_model=None,
)
@limiter.limit("60/minute")
def list_nodus_scripts(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    List all uploaded Nodus scripts.

    Returns metadata only — the script content is not included to keep the
    response compact.  Scripts are listed in upload order (most recent first).

    **Response**
    ```json
    {
      "count": 2,
      "scripts": [
        {
          "name":        "my_processor",
          "description": "Processes goals",
          "size_bytes":  128,
          "uploaded_at": "2026-03-31T12:00:00Z",
          "uploaded_by": "<user_id>"
        }
      ]
    }
    ```

    To also discover scripts that were written to disk before this process
    started, the endpoint performs a one-time scan of `scripts/nodus/` on
    first call and imports any `.nodus` files not yet in memory.
    """
    # Lazy disk scan — import any on-disk scripts not yet in the in-memory registry
    if _SCRIPTS_DIR.exists():
        with _script_lock:
            for script_path in _SCRIPTS_DIR.glob("*.nodus"):
                name = script_path.stem
                if name not in _NODUS_SCRIPT_REGISTRY:
                    try:
                        content = script_path.read_text(encoding="utf-8")
                        _NODUS_SCRIPT_REGISTRY[name] = {
                            "name": name,
                            "content": content,
                            "description": None,
                            "size_bytes": len(content.encode("utf-8")),
                            "uploaded_at": None,
                            "uploaded_by": None,
                        }
                    except OSError:
                        pass

    with _script_lock:
        scripts = [
            {
                "name": m["name"],
                "description": m.get("description"),
                "size_bytes": m.get("size_bytes", 0),
                "uploaded_at": m.get("uploaded_at"),
                "uploaded_by": m.get("uploaded_by"),
            }
            for m in reversed(list(_NODUS_SCRIPT_REGISTRY.values()))
        ]

    return {"count": len(scripts), "scripts": scripts}


# ---------------------------------------------------------------------------
# Nodus flow endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/nodus/flow",
    summary="Compile Nodus Flow",
    description="Compiles the posted Nodus flow source and can optionally run or register it. Returns the compiled flow details or execution result for that request.",
    response_model=None,
)
@limiter.limit("30/minute")
def compile_and_run_nodus_flow(
    request: Request,
    body: NodusFlowRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Compile a Nodus flow script and optionally register / execute it.

    The script uses the ``flow.*`` API to declare nodes and conditional edges:

    ```nodus
    flow.step("fetch_data")
    flow.step("analyze", when="data_ready")   # skipped when state["data_ready"] is falsy
    flow.step("summarize")
    ```

    All referenced node names must already be registered in ``NODE_REGISTRY``
    (via POST /platform/nodes/register or startup registration).

    **Response**
    ```json
    {
      "flow_name":  "market_analysis",
      "compiled":   true,
      "start":      "fetch_data",
      "nodes":      ["fetch_data", "analyze", "summarize"],
      "end":        ["summarize"],
      "registered": false,
      "run_result": {
        "status":   "SUCCESS",
        "run_id":   "<uuid>",
        "trace_id": "<uuid>",
        "error":    null
      }
    }
    ```

    Set ``run=false`` to compile only (no execution).
    Set ``register=true`` to persist the compiled flow in ``FLOW_REGISTRY``
    for later execution via POST /platform/flows/{name}/run.

    **Stability note:** Condition closures produced by ``when=`` edges live
    in-memory only.  Registered flows survive the process lifetime but are
    not restored from DB on restart — re-POST to re-register after a restart.
    """
    user_id = str(current_user["sub"])
    _validate_nodus_source(body.script, field="script")

    def handler(_ctx):
        from AINDY.runtime.nodus_flow_compiler import compile_nodus_flow
        from AINDY.runtime.flow_engine import PersistentFlowRunner, register_flow
        from AINDY.utils.uuid_utils import normalize_uuid

        # Compile the Nodus flow script → flow dict
        try:
            compiled_flow = compile_nodus_flow(body.script, body.flow_name)
        except (ValueError, RuntimeError) as exc:
            # Return a structured error response rather than raising so
            # the pipeline still records the attempt.
            return {
                "flow_name": body.flow_name,
                "compiled": False,
                "error": str(exc),
            }

        response: Dict[str, Any] = {
            "flow_name": body.flow_name,
            "compiled": True,
            "start": compiled_flow["start"],
            "nodes": list(compiled_flow["edges"].keys()),
            "end": compiled_flow["end"],
            "registered": False,
        }

        if body.register:
            register_flow(body.flow_name, compiled_flow)
            response["registered"] = True

        if body.run:
            import uuid as _uuid
            from AINDY.core.execution_gate import require_execution_unit, flow_result_to_envelope
            uid = normalize_uuid(user_id) if user_id else None
            # EU gate: create BEFORE the runner starts so the execution is
            # always DB-tracked, even if the process dies mid-run.
            _eu_correlation = str(_uuid.uuid4())
            _pre_eu = require_execution_unit(
                db=db,
                eu_type="flow",
                user_id=user_id or "",
                source_type="nodus_flow_run",
                source_id=_eu_correlation,
                correlation_id=_eu_correlation,
                extra={"flow_name": body.flow_name, "workflow_type": "nodus_flow"},
            )
            runner = PersistentFlowRunner(
                flow=compiled_flow,
                db=db,
                user_id=uid,
                workflow_type="nodus_flow",
            )
            result = runner.start(
                initial_state=dict(body.input),
                flow_name=body.flow_name,
            )
            # Finalize EU: link to the FlowRun and set terminal status.
            try:
                if _pre_eu is not None:
                    from AINDY.core.execution_unit_service import ExecutionUnitService
                    _eus = ExecutionUnitService(db)
                    if result.get("run_id"):
                        _eus.link_flow_run(_pre_eu.id, result["run_id"])
                    _eus.update_status(
                        _pre_eu.id,
                        "completed" if result.get("status") == "SUCCESS" else "failed",
                    )
            except Exception:
                pass
            response["run_result"] = {
                "status": result.get("status"),
                "run_id": result.get("run_id"),
                "trace_id": result.get("trace_id"),
                "error": result.get("error"),
                "execution_envelope": flow_result_to_envelope(result),
            }

        return response

    return execute_with_pipeline_sync(
        request=request,
        route_name="platform.nodus.flow",
        handler=handler,
        user_id=user_id,
        input_payload={"flow_name": body.flow_name, "run": body.run, "register": body.register},
        metadata={"db": db},
    )


# ---------------------------------------------------------------------------
# Nodus scheduled execution endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/nodus/schedule",
    status_code=201,
    summary="Create Nodus Schedule",
    description="Creates a scheduled Nodus job from the posted script source or script name and cron settings. Returns the persisted schedule metadata for the new job.",
    response_model=None,
)
@limiter.limit("30/minute")
def create_nodus_schedule(
    request: Request,
    body: NodusScheduleRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a cron-scheduled Nodus job.

    The script is executed on every cron tick by the APScheduler leader
    instance via ``PersistentFlowRunner(NODUS_SCRIPT_FLOW)``, giving the
    script access to memory, event, and WAIT/RESUME primitives.

    **Request**
    ```json
    {
      "script":       "set_state('ts', input_payload['now'])",
      "cron":         "0 9 * * 1-5",
      "input":        {"now": "injected_at_runtime"},
      "job_name":     "weekday_morning_snapshot",
      "error_policy": "fail",
      "max_retries":  3
    }
    ```

    **Cron syntax** — standard 5-field UTC cron:

    | Field | Range | Special |
    |-------|-------|---------|
    | min   | 0-59  | , - * / |
    | hour  | 0-23  | , - * / |
    | dom   | 1-31  | , - * / |
    | month | 1-12  | , - * / |
    | dow   | 0-6   | , - * / |

    Common patterns:
    - `"0 10 * * *"` — daily at 10:00 UTC
    - `"*/15 * * * *"` — every 15 minutes
    - `"0 9 * * 1-5"` — weekdays at 09:00 UTC

    **Response**
    ```json
    {
      "id":              "<uuid>",
      "job_name":        "weekday_morning_snapshot",
      "cron_expression": "0 9 * * 1-5",
      "next_run_at":     "2026-04-02T09:00:00+00:00",
      "error_policy":    "fail",
      "max_retries":     3,
      "is_active":       true,
      "created_at":      "2026-04-01T12:00:00+00:00"
    }
    ```

    **Leader election:** Only the A.I.N.D.Y. instance holding the
    background execution DB lease executes scheduled jobs.  All other instances
    skip the tick silently.
    """
    user_id = str(current_user["sub"])

    # Validate security sandbox before anything else
    if body.script:
        _validate_nodus_source(body.script, field="script")
        script_source = body.script
    else:
        # Resolve script_name → content; copy into the job for self-containment
        with _script_lock:
            record = _NODUS_SCRIPT_REGISTRY.get(body.script_name)  # type: ignore[arg-type]
        if not record:
            disk_path = _SCRIPTS_DIR / f"{body.script_name}.nodus"
            if disk_path.exists():
                script_source = disk_path.read_text(encoding="utf-8")
            else:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "script_not_found",
                        "message": (
                            f"Script {body.script_name!r} not found. "
                            "Upload it first via POST /platform/nodus/upload."
                        ),
                    },
                )
        else:
            script_source = record["content"]
        _validate_nodus_source(script_source, field="script_name")

    from AINDY.runtime.nodus_schedule_service import create_nodus_scheduled_job

    try:
        meta = create_nodus_scheduled_job(
            db=db,
            script=script_source,
            cron_expression=body.cron,
            user_id=user_id,
            job_name=body.job_name,
            script_name=body.script_name,
            input_payload=body.input,
            error_policy=body.error_policy,
            max_retries=body.max_retries,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})

    return meta


@router.get(
    "/nodus/schedule",
    summary="List Nodus Schedules",
    description="Returns all active scheduled Nodus jobs owned by the caller. The response includes job metadata and recent run details.",
    response_model=None,
)
@limiter.limit("60/minute")
def list_nodus_schedules(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List all active Nodus scheduled jobs owned by the current user.

    **Response**
    ```json
    {
      "count": 1,
      "jobs": [
        {
          "id":              "<uuid>",
          "job_name":        "weekday_morning_snapshot",
          "cron_expression": "0 9 * * 1-5",
          "error_policy":    "fail",
          "max_retries":     3,
          "is_active":       true,
          "last_run_at":     null,
          "last_run_status": null,
          "last_run_log_id": null,
          "next_run_at":     null,
          "created_at":      "2026-04-01T12:00:00+00:00"
        }
      ]
    }
    ```
    """
    from AINDY.runtime.nodus_schedule_service import list_nodus_scheduled_jobs

    user_id = str(current_user["sub"])
    jobs = list_nodus_scheduled_jobs(db=db, user_id=user_id)
    return {"count": len(jobs), "jobs": jobs}


@router.delete(
    "/nodus/schedule/{job_id}",
    status_code=204,
    summary="Delete Nodus Schedule",
    description="Cancels the scheduled Nodus job identified by the path parameter. Returns no body when the job is deleted successfully.",
    response_model=None,
)
@limiter.limit("30/minute")
def delete_nodus_schedule(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Cancel a scheduled Nodus job.

    Sets ``is_active=False`` (soft-delete) and removes the job from
    APScheduler immediately.  The job's execution history is preserved.

    Returns 204 on success, 404 if not found or not owned by the caller.
    """
    from AINDY.runtime.nodus_schedule_service import delete_nodus_scheduled_job

    user_id = str(current_user["sub"])
    removed = delete_nodus_scheduled_job(db=db, job_id=job_id, user_id=user_id)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"Scheduled job {job_id!r} not found",
        )
    return None


# ---------------------------------------------------------------------------
# Nodus execution trace endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/nodus/trace/{trace_id}",
    summary="Get Nodus Trace",
    description="Returns host-function trace events for the provided trace ID path parameter. The response includes ordered trace steps and a summary for that execution.",
    response_model=None,
)
@limiter.limit("60/minute")
def get_nodus_trace(
    request: Request,
    trace_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    limit: int = 500,
):
    """
    Return the full host-function call trace for a Nodus execution.

    ``trace_id`` equals the ``execution_unit_id`` / ``run_id`` returned by
    POST /platform/nodus/run (in the ``trace_id`` response field).

    **Response**
    ```json
    {
      "trace_id":            "<uuid>",
      "execution_unit_id":   "<uuid>",
      "count":               3,
      "steps": [
        {
          "id":              "<uuid>",
          "sequence":        1,
          "fn_name":         "recall",
          "args_summary":    ["goals"],
          "result_summary":  {"keys": ["id", "content"], "size": 2},
          "duration_ms":     12,
          "status":          "ok",
          "error":           null,
          "timestamp":       "2026-04-01T12:00:00.123456+00:00"
        }
      ],
      "summary": {
        "total_calls":      3,
        "total_duration_ms": 25,
        "fn_counts":        {"recall": 1, "set_state": 2},
        "error_count":      0,
        "fn_names":         ["recall", "set_state"]
      }
    }
    ```

    Returns 404 if no trace events are found for the given ``trace_id``
    (execution did not call any host functions, or belongs to another user).

    **Ownership:** only events belonging to the authenticated user are returned.
    """
    from AINDY.runtime.nodus_trace_service import query_nodus_trace

    user_id = str(current_user["sub"])
    result = query_nodus_trace(db=db, trace_id=trace_id, user_id=user_id, limit=limit)
    if result["count"] == 0:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "trace_not_found",
                "message": (
                    f"No trace events found for trace_id {trace_id!r}. "
                    "The execution may not have called any host functions, "
                    "may belong to another user, or may not exist."
                ),
            },
        )
    return result


# ── Tenant resource usage (OS layer) ─────────────────────────────────────────


@router.get(
    "/tenants/{tenant_id}/usage",
    summary="Get Tenant Usage",
    description="Returns resource usage and quota data for the tenant ID in the path. The response includes execution counts, scheduler stats, and quota limits.",
    response_model=None,
)
@limiter.limit("60/minute")
def get_tenant_usage(
    request: Request,
    tenant_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return resource usage and quota information for a tenant.

    **Ownership enforcement:** callers may only query their own tenant_id.
    Attempting to query another tenant's usage returns 403.

    **Response fields:**
    ```json
    {
      "tenant_id":            "...",
      "active_executions":    2,
      "execution_count":      14,
      "total_cpu_time_ms":    12500,
      "peak_memory_bytes":    0,
      "total_syscalls":       47,
      "scheduler": {
        "queues":             {"high": 0, "normal": 1, "low": 0},
        "waiting":            0,
        "total_enqueued":     12,
        "total_dispatched":   11,
        "total_dropped":      0
      },
      "quota_limits": {
        "max_cpu_time_ms":             30000,
        "max_memory_bytes":            268435456,
        "max_syscalls_per_execution":  100,
        "max_concurrent_executions":   5
      }
    }
    ```
    """
    caller_id = str(current_user["sub"])
    if caller_id != tenant_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "TENANT_VIOLATION",
                "message": f"Caller {caller_id!r} is not authorised to view usage for tenant {tenant_id!r}",
            },
        )

    from AINDY.kernel.resource_manager import get_resource_manager
    from AINDY.kernel.scheduler_engine import get_scheduler_engine

    rm = get_resource_manager()
    se = get_scheduler_engine()

    summary = rm.get_tenant_summary(tenant_id)
    summary["scheduler"] = se.stats()
    return summary


# ── Memory Address Space (MAS) endpoints ─────────────────────────────────────


@router.get(
    "/memory",
    summary="List Memory Path",
    description="Queries memory nodes under the provided MAS path with optional query and tags filters. Returns matching nodes, the count, and the normalized path.",
    response_model=None,
)
@limiter.limit("60/minute")
def list_memory_path(
    request: Request,
    path: str,
    limit: int = 50,
    query: Optional[str] = None,
    tags: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List memory nodes at a MAS path.

    **path** examples:
    - ``/memory/user-123/entities/*``  — one level under entities
    - ``/memory/user-123/entities/**`` — all descendants of entities
    - ``/memory/user-123/entities/pending/abc`` — exact node

    Optionally filter by **query** (keyword) and **tags** (comma-separated).
    """
    from AINDY.memory.memory_address_space import validate_tenant_path, normalize_path
    from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

    user_id = str(current_user["sub"])
    try:
        norm = normalize_path(path)
        validate_tenant_path(norm, user_id)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})

    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    dao = MemoryNodeDAO(db)
    nodes = dao.query_path(
        path_expr=norm,
        query=query,
        tags=tag_list,
        user_id=user_id,
        limit=limit,
    )
    return {"nodes": nodes, "count": len(nodes), "path": norm}


@router.get(
    "/memory/tree",
    summary="Get Memory Tree",
    description="Builds a hierarchical memory tree under the provided MAS path. Returns the tree structure, node count, and normalized path.",
    response_model=None,
)
@limiter.limit("60/minute")
def memory_tree(
    request: Request,
    path: str,
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a hierarchical tree of memory nodes under a path prefix."""
    from AINDY.memory.memory_address_space import (
        validate_tenant_path, normalize_path, is_exact,
        wildcard_prefix, build_tree,
    )
    from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

    user_id = str(current_user["sub"])
    try:
        norm = normalize_path(path)
        validate_tenant_path(norm, user_id)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})

    dao = MemoryNodeDAO(db)
    prefix = norm if is_exact(norm) else wildcard_prefix(norm)
    nodes = dao.walk_path(prefix, user_id=user_id, limit=limit)
    tree = build_tree(nodes)
    return {"tree": tree, "node_count": len(nodes), "path": norm}


@router.get(
    "/memory/trace",
    summary="Get Memory Trace",
    description="Follows the causal chain for the exact memory path passed in the query string. Returns the traced chain, its depth, and the normalized path.",
    response_model=None,
)
@limiter.limit("60/minute")
def memory_trace(
    request: Request,
    path: str,
    depth: int = 5,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Follow the causal chain from the memory node at an exact path."""
    from AINDY.memory.memory_address_space import validate_tenant_path, normalize_path
    from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

    user_id = str(current_user["sub"])
    try:
        norm = normalize_path(path)
        validate_tenant_path(norm, user_id)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})

    dao = MemoryNodeDAO(db)
    chain = dao.causal_trace(path=norm, depth=min(depth, 20), user_id=user_id)
    if not chain:
        raise HTTPException(status_code=404, detail={"error": "No node found at path"})
    return {"chain": chain, "depth": len(chain), "path": norm}


# ── Syscall versioning introspection ──────────────────────────────────────────


@router.get(
    "/syscalls",
    summary="List Syscalls",
    description="Returns syscall registry metadata, optionally filtered by the version query parameter. The response includes versions, syscall specs, and a total count.",
    response_model=None,
)
@limiter.limit("60/minute")
def list_syscalls(
    request: Request,
    version: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Return available syscall versions, names, schemas, and deprecation status.

    Optionally filter by **version** (e.g. ``?version=v1``).

    **Response shape**::

        {
          "versions": ["v1", "v2"],
          "syscalls": {
            "v1": {
              "memory.read": {
                "full_name": "sys.v1.memory.read",
                "capability": "memory.read",
                "description": "...",
                "stable": true,
                "deprecated": false,
                "input_schema": {...},
                "output_schema": {...},
                "replacement": null
              },
              ...
            }
          },
          "total_count": 9
        }
    """
    from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY
    from AINDY.kernel.syscall_versioning import SyscallSpec

    versioned = SYSCALL_REGISTRY.versioned
    available_versions = SYSCALL_REGISTRY.versions()

    if version:
        if version not in versioned:
            raise HTTPException(
                status_code=404,
                detail={"error": f"Unknown syscall version: {version!r}"},
            )
        versioned = {version: versioned[version]}

    result: dict[str, dict] = {}
    total = 0
    for ver, actions in versioned.items():
        result[ver] = {}
        for action, entry in sorted(actions.items()):
            spec = SyscallSpec(
                name=action,
                version=ver,
                capability=entry.capability,
                description=entry.description,
                input_schema=entry.input_schema,
                output_schema=entry.output_schema,
                stable=entry.stable,
                deprecated=entry.deprecated,
                deprecated_since=entry.deprecated_since,
                replacement=entry.replacement,
            )
            result[ver][action] = spec.to_dict()
            total += 1

    return {
        "versions": available_versions if not version else [version],
        "syscalls": result,
        "total_count": total,
    }


# ── SDK syscall dispatch ───────────────────────────────────────────────────────


class SyscallDispatchRequest(BaseModel):
    """Request body for POST /platform/syscall."""

    name: str = Field(
        ...,
        description="Fully-qualified syscall name — sys.v{N}.{domain}.{action}",
        examples=["sys.v1.memory.read"],
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Syscall-specific arguments.",
    )


@router.post(
    "/syscall",
    summary="Dispatch Syscall",
    description="Executes the posted syscall name with its payload through the platform dispatcher. Returns the standard syscall execution envelope for that call.",
    response_model=None,
)
@limiter.limit("30/minute")
def dispatch_syscall(
    request: Request,
    body: SyscallDispatchRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Execute any registered syscall by name.

    This is the primary SDK entry point. It maps directly to
    ``SyscallDispatcher.dispatch()`` — the same pipeline used internally
    by Nodus scripts and flow nodes.

    **Request**::

        {
            "name":    "sys.v1.memory.read",
            "payload": {"query": "authentication flow", "limit": 5}
        }

    **Response** — standard syscall envelope::

        {
            "status":            "success" | "error",
            "data":              dict,
            "version":           "v1",
            "warning":           null,
            "trace_id":          str,
            "execution_unit_id": str,
            "syscall":           str,
            "duration_ms":       int,
            "error":             null
        }

    Error codes:
    - ``422`` — malformed syscall name or payload fails input schema validation.
    - ``403`` — caller's API key lacks the required capability.
    - ``429`` — execution unit has exceeded its resource quota.
    - The dispatcher itself never raises; all errors are returned in the envelope.
      HTTP-level errors (4xx) are raised by this route for missing syscalls,
      capability violations, and validation failures so SDK error mapping works.
    """
    from AINDY.kernel.syscall_dispatcher import get_dispatcher, make_syscall_ctx_from_tool
    from AINDY.kernel.syscall_registry import DEFAULT_NODUS_CAPABILITIES

    user_id = str(current_user.get("user_id") or current_user.get("sub") or "")

    # For platform API key callers, restrict capabilities to what the key was granted.
    # JWT users retain the full default capability set.
    if current_user.get("auth_type") == "api_key":
        api_key_scopes = current_user.get("api_key_scopes") or []
        # Intersect granted scopes with the default capability set so unknown
        # scope strings from the key don't expand the capability surface.
        capabilities = [s for s in api_key_scopes if s in DEFAULT_NODUS_CAPABILITIES]
    else:
        capabilities = list(DEFAULT_NODUS_CAPABILITIES)

    # Build a SyscallContext from the authenticated principal.
    # The execution_unit_id is a fresh UUID for this HTTP call.
    ctx = make_syscall_ctx_from_tool(
        user_id=user_id,
        capabilities=capabilities,
    )

    result = get_dispatcher().dispatch(body.name, body.payload, ctx)

    # Surface structured failures as HTTP errors so the SDK can map them.
    if result["status"] == "error":
        msg = result.get("error", "syscall error")
        if "Permission denied" in msg or "capability" in msg:
            raise HTTPException(status_code=403, detail={"error": msg})
        if "Input validation failed" in msg:
            raise HTTPException(status_code=422, detail={"error": msg})
        if "quota" in msg.lower() or "QUOTA" in msg:
            raise HTTPException(status_code=429, detail={"error": msg})
        if "Unknown syscall" in msg:
            raise HTTPException(status_code=404, detail={"error": msg})

    return result

