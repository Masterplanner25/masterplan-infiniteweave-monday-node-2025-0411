from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ExecutionRegistry:
    def __init__(self):
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, handler: Callable[..., Any]) -> None:
        self._handlers[name] = handler

    def execute(self, *, workflow: str, payload: dict, user_id: str, db):
        handler = self._handlers.get(workflow)
        if handler is None:
            logger.info("[ExecutionRegistry] no handler for %s; returning payload", workflow)
            return {"workflow": workflow, "input": payload}
        return handler(payload, user_id, db)


REGISTRY = ExecutionRegistry()


# ── Flow Engine re-exports ────────────────────────────────────────────────────
# NODE_REGISTRY and FLOW_REGISTRY are the canonical registries as of
# Flow Engine Phase B. Exported here for backwards-compatibility.

from AINDY.runtime.flow_engine import (  # noqa: F401, E402
    NODE_REGISTRY,
    FLOW_REGISTRY,
    register_node,
    register_flow,
)

