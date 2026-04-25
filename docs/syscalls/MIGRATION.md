# Syscall Migration Guide

## Overview
Syscalls are versioned as `sys.{version}.{name}`. `v1` is the current stable surface. Breaking changes require a new version prefix rather than mutating the existing ABI in place.

## What Is a Breaking Change
Requires a version bump:
- Removing a required input field.
- Changing output shape within an existing version.
- Removing a syscall.
- Renaming a syscall.

Does not require a version bump:
- Adding new optional input fields.
- Additive documentation or introspection metadata.
- Adding new syscalls alongside existing ones.

## Deprecation Process
A syscall starts as stable, may later be marked deprecated, and may name a replacement through `replacement` and `deprecated_since` in `SyscallSpec`. The dispatcher still executes deprecated syscalls, logs a warning, and returns the warning in the standard envelope’s `warning` field. The warning format is:

```text
Syscall 'sys.v1.example.action' is deprecated since v1 — use 'sys.v2.example.action' instead.
```

Removal belongs in the next breaking version, not the current one.

## Calling a Syscall: Three Patterns

### Pattern 1: Via the Python SDK
```python
from AINDY.sdk.aindy_sdk import AINDYClient

client = AINDYClient(
    base_url="http://localhost:8000",
    api_key="aindy_your_platform_key",
)

result = client.syscalls.call(
    "sys.v1.memory.read",
    {"query": "authentication flow", "limit": 5},
)
```

You can also introspect the live surface:

```python
registry = client.syscalls.list(version="v1")
```

### Pattern 2: Via SyscallDispatcher (internal domain caller)
```python
from AINDY.kernel.syscall_dispatcher import SyscallContext, get_dispatcher

ctx = SyscallContext(
    execution_unit_id="run-123",
    user_id="user-456",
    capabilities=["memory.read"],
    trace_id="run-123",
)
result = get_dispatcher().dispatch("sys.v1.memory.read", {"query": "auth"}, ctx)
```

Required `SyscallContext` fields are `execution_unit_id`, `user_id`, `capabilities`, and `trace_id`. `memory_context` and `metadata` are optional; internal callers often pass shared DB state through `metadata`, as shown in [masterplan_guard.py](/C:/dev/masterplan-infiniteweave-monday-node-2025-0411/apps/analytics/services/masterplan_guard.py:1).

### Pattern 3: Via the HTTP API
```http
POST /platform/syscall
X-Platform-Key: aindy_...
Content-Type: application/json

{
  "name": "sys.v1.memory.read",
  "payload": {"path": "/memory/demo/**"}
}
```

The HTTP handler dispatches the syscall and returns the standard envelope. `GET /platform/syscalls` exposes the live ABI inventory.

## Migrating from v1 to v2 (Template)

### Why This Version Was Introduced
[Describe the breaking change and what it enables.]

### Changed Syscalls
| Old Name | New Name | What Changed | Migration Steps |
|---|---|---|---|
| `[sys.v1.example.action]` | `[sys.v2.example.action]` | `[Breaking change summary]` | `[Update payload fields, output parsing, and capability usage.]` |

### Deprecated v1 Syscalls
| Syscall | Deprecated Since | Replacement |
|---|---|---|
| `[sys.v1.example.action]` | `[v1 / date]` | `[sys.v2.example.action]` |

### Timeline
- v1 deprecated: `[date]`
- v1 removed: `[date + N months, per release policy]`

### Updating Your Code
1. Update the SDK version that understands the new syscall names.
2. Replace direct `client.syscalls.call("sys.v1...")` calls with `sys.v2...`.
3. Update any `SyscallDispatcher` internal calls to the new fully-qualified names.
4. Update any `POST /platform/syscall` callers to send the new `name` value and revised payload.
5. Re-run `GET /platform/syscalls` against the target environment and confirm the expected version is present.
6. Watch for deprecation warnings in dispatcher responses and logs during rollout.

## Rollback Policy
`SYSCALL_VERSION_FALLBACK` is `False`. Unknown versions do not silently fall back to `LATEST_STABLE_VERSION`; the dispatcher returns an error. In practice, callers that send an unsupported version should expect an error like:

```text
Unknown syscall version: 'v2'; available versions: ['v1']
```

The fallback behavior is therefore explicit rollback: keep calling the older supported version until the target runtime exposes the new one.
