"""
auth/api_key_auth.py — Platform API key authentication and scope enforcement.

Overview
--------
A.I.N.D.Y. supports two authentication principals:

  1. JWT user (existing) — Bearer token from /auth/login.
     Issued to human users.  Carries full trust; no scope restrictions.
     All existing routes using get_current_user() are unchanged.

  2. Platform API key (new) — X-Platform-Key: aindy_<token>.
     Issued to external systems / integrations.
     Trust is scoped to the capabilities explicitly granted at key creation.

Scope constants (Scopes class)
-------------------------------
  flow.read       — list/get flows and their definitions
  flow.execute    — run any registered flow via POST /platform/flows/{name}/run
  memory.read     — read memory nodes, recall, search
  memory.write    — create/update/delete memory nodes
  agent.run       — create and monitor agent runs
  webhook.manage  — create/delete webhook subscriptions
  platform.admin  — full platform access (implies all scopes)

How to protect a route with a scope
-------------------------------------
  @router.post("/platform/flows/{name}/run")
  def run_flow(
      ...
      _principal: AuthPrincipal = Depends(require_scope("flow.execute")),
  ):
      ...

  The dependency accepts EITHER a valid JWT Bearer token OR a Platform API key
  that includes the required scope.  Existing JWT routes need no changes.

Backward compatibility
-----------------------
  get_current_user()  — unchanged; used by all existing routes.
  verify_api_key()    — unchanged; used by service-to-service routes (watcher etc.).
  New require_scope() is purely additive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from db.database import get_db

# ---------------------------------------------------------------------------
# Scope constants
# ---------------------------------------------------------------------------

class Scopes:
    FLOW_READ        = "flow.read"
    FLOW_EXECUTE     = "flow.execute"
    MEMORY_READ      = "memory.read"
    MEMORY_WRITE     = "memory.write"
    AGENT_RUN        = "agent.run"
    WEBHOOK_MANAGE   = "webhook.manage"
    PLATFORM_ADMIN   = "platform.admin"

    # Ordered list used for validation and documentation
    ALL: list[str] = [
        FLOW_READ,
        FLOW_EXECUTE,
        MEMORY_READ,
        MEMORY_WRITE,
        AGENT_RUN,
        WEBHOOK_MANAGE,
        PLATFORM_ADMIN,
    ]


# ---------------------------------------------------------------------------
# Principal dataclass (returned by both auth paths)
# ---------------------------------------------------------------------------

@dataclass
class AuthPrincipal:
    """
    Resolved authentication identity.

    For JWT users:    auth_type="jwt",     scopes=["*"] (unrestricted)
    For API keys:     auth_type="api_key", scopes=[<granted scopes>]
    """
    user_id: str
    auth_type: str          # "jwt" | "api_key"
    scopes: list[str] = field(default_factory=list)
    key_id: str | None = None     # API key UUID, populated for api_key auth
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        if self.auth_type == "jwt":
            return True   # JWT users carry full trust
        return scope in self.scopes or Scopes.PLATFORM_ADMIN in self.scopes


# ---------------------------------------------------------------------------
# Header extractors
# ---------------------------------------------------------------------------

_PLATFORM_KEY_HEADER = "X-Platform-Key"
_platform_key_header = APIKeyHeader(name=_PLATFORM_KEY_HEADER, auto_error=False)
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Core dependency
# ---------------------------------------------------------------------------

def get_authenticated_principal(
    bearer: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
    platform_key: str | None = Security(_platform_key_header),
    db: Session = Depends(get_db),
) -> AuthPrincipal:
    """
    Resolve the calling principal from either a JWT Bearer token or a
    Platform API key.  Raises 401 if neither is present or valid.

    JWT path:      identical to get_current_user() — no behavior change.
    API key path:  looks up the hashed key, checks active/not-expired/not-revoked,
                   updates last_used_at, returns an AuthPrincipal with the stored scopes.
    """
    if platform_key:
        return _resolve_api_key(platform_key, db)
    if bearer:
        return _resolve_jwt(bearer.credentials)
    raise HTTPException(
        status_code=401,
        detail="Authentication required (Bearer token or X-Platform-Key header)",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _resolve_jwt(token: str) -> AuthPrincipal:
    from services.auth_service import decode_access_token
    payload = decode_access_token(token)
    return AuthPrincipal(
        user_id=str(payload.get("sub", "")),
        auth_type="jwt",
        scopes=["*"],
        metadata={"jwt_payload": payload},
    )


def _resolve_api_key(raw_key: str, db: Session) -> AuthPrincipal:
    from services.api_key_service import hash_key, touch_last_used
    from db.models.api_key import PlatformAPIKey

    key_hash = hash_key(raw_key)
    record = db.query(PlatformAPIKey).filter(
        PlatformAPIKey.key_hash == key_hash
    ).first()

    if record is None or not record.is_valid():
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked API key",
        )

    # Non-blocking update — if it fails the request still succeeds
    try:
        touch_last_used(record, db)
    except Exception:
        pass

    return AuthPrincipal(
        user_id=str(record.user_id),
        auth_type="api_key",
        scopes=list(record.scopes or []),
        key_id=str(record.id),
        metadata={"key_name": record.name, "key_prefix": record.key_prefix},
    )


# ---------------------------------------------------------------------------
# Scope-enforcement dependency factory
# ---------------------------------------------------------------------------

def require_scope(scope: str):
    """
    FastAPI dependency factory that enforces a required capability scope.

    Accepts both JWT Bearer tokens (unrestricted) and Platform API keys
    (must include the specified scope or platform.admin).

    Usage:
        @router.post("/platform/flows/{name}/run")
        def run_flow(..., _: AuthPrincipal = Depends(require_scope("flow.execute"))):
            ...
    """
    def _dependency(
        principal: AuthPrincipal = Depends(get_authenticated_principal),
    ) -> AuthPrincipal:
        if not principal.has_scope(scope):
            raise HTTPException(
                status_code=403,
                detail=f"Scope {scope!r} required. Granted scopes: {principal.scopes}",
            )
        return principal
    # Give the dependency a meaningful name for OpenAPI docs
    _dependency.__name__ = f"require_scope_{scope.replace('.', '_')}"
    return _dependency
