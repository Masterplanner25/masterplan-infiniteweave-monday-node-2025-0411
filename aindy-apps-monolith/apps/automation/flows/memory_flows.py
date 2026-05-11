"""
Memory flow nodes for the AINDY automation layer.
Node functions must follow the contract:
  fn(state: dict, context: dict) -> dict
  Returns one of: SUCCESS / RETRY / FAILURE / WAIT envelope.
All domain imports must be DEFERRED (inside function body).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register() -> None:
    """Compatibility shim for memory nodes that now live in platform runtime."""
    return None
