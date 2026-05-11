"""
Syscall Versioning and ABI Stability — A.I.N.D.Y.

Provides the machinery for versioned syscall dispatch:
  - ABI version constants
  - Name parsing  (sys.v1.memory.read → ("v1", "memory.read"))
  - Input / output schema validation
  - SyscallSpec  — serialisable ABI contract per syscall
  - Fallback policy constants

This module has NO imports from the rest of the A.I.N.D.Y. codebase
so it can be used by syscall_registry.py without circular-import risk.

ABI Stability rules
-------------------
1. Required input fields MAY NOT be removed within the same version.
2. New fields MUST be optional (no new required fields in same version).
3. Output shape MUST remain consistent within a version.
4. Breaking changes MUST use a new version ("sys.v2.*").
5. Deprecated syscalls MUST emit a warning and point to a replacement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── Stable ABI versions ───────────────────────────────────────────────────────

#: Versions that are considered stable and may be used in production.
ABI_VERSIONS: frozenset[str] = frozenset({"v1"})

#: Latest stable version string (used for fallback resolution).
LATEST_STABLE_VERSION: str = "v1"

#: When True, unknown versions fall back to LATEST_STABLE_VERSION.
#: When False (default), an unknown version returns an error.
SYSCALL_VERSION_FALLBACK: bool = False

#: Prefix all syscall names must start with.
SYSCALL_PREFIX: str = "sys."


# ── SyscallSpec ───────────────────────────────────────────────────────────────

@dataclass
class SyscallSpec:
    """Serialisable ABI contract for a single syscall.

    Used for introspection (GET /platform/syscalls) and documentation.
    The dispatcher reads ``deprecated`` and ``replacement`` at runtime.

    Attributes:
        name:            Short action name, e.g. ``"memory.read"``.
        version:         ABI version string, e.g. ``"v1"``.
        full_name:       Fully-qualified syscall name (derived).
        capability:      Required capability string.
        description:     Human-readable description.
        input_schema:    Lightweight schema for input validation.
        output_schema:   Lightweight schema for output validation.
        stable:          If False, this syscall is experimental.
        deprecated:      If True, emit warning and suggest replacement.
        deprecated_since: Version string when deprecation was introduced.
        replacement:     Full syscall name to use instead (if deprecated).
    """
    name: str
    version: str
    capability: str = ""
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    stable: bool = True
    deprecated: bool = False
    deprecated_since: str | None = None
    replacement: str | None = None

    @property
    def full_name(self) -> str:
        return f"sys.{self.version}.{self.name}"

    def deprecation_message(self) -> str | None:
        """Return a deprecation warning string, or None if not deprecated."""
        if not self.deprecated:
            return None
        parts = [f"Syscall '{self.full_name}' is deprecated"]
        if self.deprecated_since:
            parts.append(f"since {self.deprecated_since}")
        if self.replacement:
            parts.append(f"— use '{self.replacement}' instead")
        return " ".join(parts) + "."

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for the API response."""
        return {
            "full_name": self.full_name,
            "name": self.name,
            "version": self.version,
            "capability": self.capability,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "stable": self.stable,
            "deprecated": self.deprecated,
            "deprecated_since": self.deprecated_since,
            "replacement": self.replacement,
        }


# ── Name parsing ──────────────────────────────────────────────────────────────

def parse_syscall_name(name: str) -> tuple[str, str]:
    """Parse a fully-qualified syscall name into (version, action).

    Example:
        >>> parse_syscall_name("sys.v1.memory.read")
        ('v1', 'memory.read')

    Args:
        name: Fully-qualified syscall name — must start with "sys.".

    Returns:
        (version, action) tuple where action may contain dots.

    Raises:
        ValueError: If the name is malformed.
    """
    if not name.startswith(SYSCALL_PREFIX):
        raise ValueError(
            f"Syscall name must start with {SYSCALL_PREFIX!r}, got: {name!r}"
        )
    rest = name[len(SYSCALL_PREFIX):]  # "v1.memory.read"
    dot_idx = rest.find(".")
    if dot_idx == -1:
        raise ValueError(
            f"Cannot parse version from {name!r}: missing version segment"
        )
    version = rest[:dot_idx]   # "v1"
    action = rest[dot_idx + 1:]  # "memory.read"
    if not version:
        raise ValueError(f"Empty version segment in {name!r}")
    if not action:
        raise ValueError(f"Empty action segment in {name!r}")
    return version, action


# ── Schema validation ─────────────────────────────────────────────────────────

#: Maps JSON-schema-style type names to Python types.
_SCHEMA_TYPE_MAP: dict[str, type] = {
    "string": str, "str": str,
    "int": int, "integer": int,
    "float": float, "number": float,
    "bool": bool, "boolean": bool,
    "list": list, "array": list,
    "dict": dict, "object": dict,
}


def validate_payload(schema: dict, payload: dict) -> list[str]:
    """Validate *payload* against a lightweight schema.

    Schema format::

        {
            "required": ["field1", "field2"],   # required field names
            "properties": {
                "field1": {"type": "string"},    # type check (optional)
                "field2": {"type": "int"},
            }
        }

    Supported types: string/str, int/integer, float/number,
    bool/boolean, list/array, dict/object.

    Args:
        schema:  Schema dict.  Empty dict → no validation, always ok.
        payload: The dict to validate.

    Returns:
        List of error strings.  Empty list means valid.
    """
    if not schema:
        return []

    errors: list[str] = []
    required: list[str] = schema.get("required") or []
    properties: dict = schema.get("properties") or {}

    # Required field check
    for fname in required:
        if fname not in payload or payload[fname] is None:
            errors.append(f"Missing required field: {fname!r}")

    # Type check (only fields that are present)
    for fname, spec in properties.items():
        if fname not in payload:
            continue  # optional fields are fine if absent
        expected_type_name = spec.get("type")
        if not expected_type_name:
            continue
        py_type = _SCHEMA_TYPE_MAP.get(expected_type_name)
        if py_type is None:
            continue  # unknown type — skip silently
        actual = payload[fname]
        if not isinstance(actual, py_type):
            errors.append(
                f"Field {fname!r}: expected type {expected_type_name!r}, "
                f"got {type(actual).__name__!r}"
            )

    return errors


def validate_input(schema: dict, payload: dict) -> list[str]:
    """Alias for validate_payload — validates handler input."""
    return validate_payload(schema, payload)


def validate_output(schema: dict, data: dict) -> list[str]:
    """Validate handler output dict against an output schema.

    Same schema format as validate_input.  Uses required fields to confirm
    the handler returned the expected keys.
    """
    return validate_payload(schema, data)


# ── Version resolution ────────────────────────────────────────────────────────

def resolve_version(
    requested: str,
    available: frozenset[str],
    fallback: bool = SYSCALL_VERSION_FALLBACK,
) -> str | None:
    """Return the version to use for a dispatch request.

    Args:
        requested:  Version parsed from the syscall name (e.g. "v1").
        available:  Set of versions that have entries in the registry.
        fallback:   If True and *requested* is unknown, return latest stable.

    Returns:
        The version string to use, or None if the version is unresolvable.
    """
    if requested in available:
        return requested
    if fallback:
        # Fall back to the highest stable version
        stable_candidates = sorted(ABI_VERSIONS & available, reverse=True)
        return stable_candidates[0] if stable_candidates else None
    return None
