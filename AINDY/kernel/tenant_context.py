"""
Tenant Context — A.I.N.D.Y. OS Isolation Layer

Every execution in A.I.N.D.Y. runs inside a TenantContext. This module
defines the tenant isolation boundary and enforces the invariant that:

  - Memory access is namespaced to the tenant
  - Cross-tenant reads raise PermissionError
  - Every ExecutionUnit carries a tenant_id

Tenant model
------------
A.I.N.D.Y. uses a single-user-per-tenant model: tenant_id == user_id.
This is explicit in TenantContext to allow future multi-user tenants
without changing the isolation contract.

Memory path contract
--------------------
All memory operations must be scoped to:

    /memory/{tenant_id}/...

Callers that violate this raise TENANT_VIOLATION.

Usage
-----
    from AINDY.kernel.tenant_context import TenantContext, build_tenant_context

    ctx = build_tenant_context(user_id="user-123", capability_scope=["memory.read"])
    ctx.assert_memory_path(f"/memory/{ctx.tenant_id}/node-abc")  # OK
    ctx.assert_memory_path("/memory/other-tenant/node-xyz")       # PermissionError
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Structured error code returned in RESOURCE_LIMIT_EXCEEDED and TENANT_VIOLATION
TENANT_VIOLATION = "TENANT_VIOLATION"
RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"


@dataclass(frozen=True)
class TenantContext:
    """Immutable tenant isolation context.

    Attributes:
        tenant_id:        The tenant's unique identifier (== user_id in A.I.N.D.Y.).
        user_id:          Authenticated user ID within the tenant.
        namespace:        Canonical tenant namespace prefix: "tenant:{tenant_id}".
        capability_scope: Explicit list of granted capabilities for this context.
    """

    tenant_id: str
    user_id: str
    namespace: str
    capability_scope: list[str] = field(default_factory=list)

    # ── Memory path enforcement ───────────────────────────────────────────────

    def memory_prefix(self) -> str:
        """Return the canonical memory namespace prefix for this tenant."""
        return f"/memory/{self.tenant_id}/"

    def validate_memory_path(self, path: str) -> bool:
        """Return True if *path* is within this tenant's memory namespace."""
        return path.startswith(self.memory_prefix())

    def assert_memory_path(self, path: str) -> None:
        """Raise PermissionError if *path* is outside the tenant namespace.

        Args:
            path: Memory path to validate (e.g. "/memory/{tenant_id}/node-abc").

        Raises:
            PermissionError: TENANT_VIOLATION — path belongs to another tenant.
        """
        if not self.validate_memory_path(path):
            raise PermissionError(
                f"{TENANT_VIOLATION}: memory path {path!r} is outside "
                f"tenant namespace {self.memory_prefix()!r}"
            )

    # ── Cross-tenant guard ────────────────────────────────────────────────────

    def assert_same_tenant(self, other_tenant_id: str) -> None:
        """Raise PermissionError if *other_tenant_id* differs from this tenant.

        Args:
            other_tenant_id: The tenant_id of the resource being accessed.

        Raises:
            PermissionError: TENANT_VIOLATION — cross-tenant access attempted.
        """
        if str(other_tenant_id) != str(self.tenant_id):
            raise PermissionError(
                f"{TENANT_VIOLATION}: tenant {self.tenant_id!r} attempted to "
                f"access resource owned by tenant {other_tenant_id!r}"
            )

    # ── Capability check ──────────────────────────────────────────────────────

    def has_capability(self, cap: str) -> bool:
        """Return True if *cap* is in this context's capability_scope."""
        return cap in self.capability_scope

    def assert_capability(self, cap: str) -> None:
        """Raise PermissionError if *cap* is not in capability_scope.

        Raises:
            PermissionError: TENANT_VIOLATION — capability not granted.
        """
        if not self.has_capability(cap):
            raise PermissionError(
                f"{TENANT_VIOLATION}: tenant {self.tenant_id!r} does not have "
                f"capability {cap!r}; granted: {self.capability_scope}"
            )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"TenantContext(tenant_id={self.tenant_id!r}, "
            f"namespace={self.namespace!r}, "
            f"caps={len(self.capability_scope)})"
        )


# ── Builder helpers ───────────────────────────────────────────────────────────

def build_tenant_context(
    user_id: str,
    capability_scope: list[str] | None = None,
    tenant_id: str | None = None,
) -> TenantContext:
    """Build a TenantContext for the given user.

    In A.I.N.D.Y.'s single-user-per-tenant model, tenant_id defaults to
    user_id when not explicitly supplied.

    Args:
        user_id:          Authenticated user ID.
        capability_scope: Granted capabilities. Defaults to [].
        tenant_id:        Explicit tenant override. Defaults to user_id.

    Returns:
        A frozen TenantContext ready for use in execution.
    """
    resolved_tenant = str(tenant_id or user_id or "")
    resolved_user = str(user_id or "")
    return TenantContext(
        tenant_id=resolved_tenant,
        user_id=resolved_user,
        namespace=f"tenant:{resolved_tenant}",
        capability_scope=list(capability_scope or []),
    )


def tenant_context_from_syscall_context(syscall_ctx) -> TenantContext:
    """Derive a TenantContext from an existing SyscallContext.

    Args:
        syscall_ctx: A ``SyscallContext`` instance (kernel.syscall_registry).

    Returns:
        TenantContext with tenant_id == syscall_ctx.user_id.
    """
    return build_tenant_context(
        user_id=str(syscall_ctx.user_id or ""),
        capability_scope=list(getattr(syscall_ctx, "capabilities", []) or []),
    )
