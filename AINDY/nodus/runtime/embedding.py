"""Compatibility shim for ``nodus.runtime.embedding`` imports.

Tests patch ``nodus.runtime.embedding.NodusRuntime`` directly. The real VM
implementation is external to this repo, so this module provides a stable local
namespace for those patches without changing the existing runtime architecture.
"""

from __future__ import annotations


class NodusRuntime:
    """Placeholder VM entrypoint used for patching in tests.

    The production adapter still expects the external Nodus runtime interface
    (`register_function`, `run_source`, etc.). When that implementation is not
    installed, instantiating this placeholder fails with a clear error instead of
    a ``ModuleNotFoundError`` on import.
    """

    def __init__(self, *args, **kwargs):
        raise ImportError(
            "nodus.runtime.embedding.NodusRuntime is a compatibility shim. "
            "Install the real Nodus runtime or patch this class in tests."
        )
