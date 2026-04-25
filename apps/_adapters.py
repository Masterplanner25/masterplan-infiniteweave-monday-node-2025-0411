"""
Deprecated: import from AINDY.platform_layer.response_adapters instead.

This shim exists for backward compatibility during migration.
"""
from __future__ import annotations

# MIGRATION: This file is a shim. Delete after confirming no remaining callers.
# All callers should import from AINDY.platform_layer.response_adapters.
from AINDY.platform_layer.response_adapters import (  # noqa: F401
    legacy_envelope_adapter,
    memory_completion_adapter,
    memory_execute_adapter,
    raw_canonical_adapter,
    raw_json_adapter,
)

__all__ = [
    "raw_json_adapter",
    "legacy_envelope_adapter",
    "raw_canonical_adapter",
    "memory_execute_adapter",
    "memory_completion_adapter",
]
