from __future__ import annotations

import os
import sys
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from memory.nodus_memory_bridge import create_nodus_bridge
from runtime.nodus_security import (
    ALLOWED_OPERATION_CAPABILITIES,
    NodusSecurityError,
    authorize_nodus_execution,
)
from utils.user_ids import require_user_id


def execute_nodus_task_payload(
    *,
    task_name: str,
    task_code: str,
    db: Session,
    user_id: str,
    session_tags: Optional[list[str]] = None,
    allowed_operations: Optional[list[str]] = None,
    execution_id: Optional[str] = None,
    capability_token: Optional[dict] = None,
    logger=None,
) -> dict[str, Any]:
    normalized_user_id = str(require_user_id(user_id))
    bridge = create_nodus_bridge(
        db=db,
        user_id=normalized_user_id,
        session_tags=session_tags,
    )

    try:
        security_context = authorize_nodus_execution(
            task_code=task_code,
            allowed_operations=allowed_operations,
            capability_token=capability_token,
            execution_id=execution_id,
            user_id=normalized_user_id,
        )

        nodus_path = os.environ.get(
            "NODUS_SOURCE_PATH",
            r"C:\dev\Coding Language\src",
        )
        if nodus_path not in sys.path:
            sys.path.insert(0, nodus_path)

        from nodus.runtime.embedding import NodusRuntime

        from db.dao.memory_node_dao import MemoryNodeDAO
        from runtime.memory import MemoryOrchestrator
        from runtime.memory.memory_feedback import MemoryFeedbackEngine
        from bridge import create_memory_node

        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        feedback_engine = MemoryFeedbackEngine()

        memory_context = orchestrator.get_context(
            user_id=normalized_user_id,
            query=task_name or "",
            task_type="nodus_execution",
            db=db,
            max_tokens=800,
            metadata={
                "tags": session_tags or [],
                "node_types": [],
                "limit": 3,
            },
        )

        runtime = NodusRuntime()
        available_operations = {
            "recall": (bridge.recall, (0, 1, 2, 3, 4)),
            "recall_tool": (bridge.recall_tool, (0, 1, 2, 3)),
            "remember": (bridge.remember, (1, 2, 3, 4, 5)),
            "suggest": (bridge.get_suggestions, (0, 1, 2, 3)),
            "record_outcome": (bridge.record_outcome, 2),
            "recall_from": (bridge.recall_from, (1, 2, 3, 4)),
            "recall_all": (bridge.recall_all_agents, (0, 1, 2, 3)),
            "share": (bridge.share, 1),
        }
        for operation_name in security_context["allowed_operations"]:
            fn, arity = available_operations[operation_name]
            runtime.register_function(operation_name, fn, arity=arity)

        result = runtime.run_source(
            task_code,
            filename=f"<nodus:{task_name}>",
            initial_globals={
                "memory_context": memory_context.formatted,
                "memory_ids": memory_context.ids,
                "allowed_operations": security_context["allowed_operations"],
            },
            host_globals={
                "memory_context": memory_context.formatted,
                "memory_ids": memory_context.ids,
                "allowed_operations": security_context["allowed_operations"],
            },
        )

        try:
            create_memory_node(
                content=f"Nodus task '{task_name}' executed: {result.get('stdout', '')[:500]}",
                source="nodus_task",
                tags=(session_tags or []) + ["nodus", "task_execution"],
                user_id=normalized_user_id,
                db=db,
                node_type="outcome",
            )
        except Exception as exc:
            if logger:
                logger.warning("nodus_memory_capture_failed task=%s user=%s: %s", task_name, normalized_user_id, exc)

        try:
            success_score = 1.0 if result.get("ok") else 0.0
            feedback_engine.record_usage(
                memory_ids=memory_context.ids,
                success_score=success_score,
                db=db,
            )
        except Exception as exc:
            if logger:
                logger.warning(
                    "nodus_feedback_failed task=%s user=%s memory_ids=%s: %s",
                    task_name,
                    normalized_user_id,
                    memory_context.ids,
                    exc,
                )

        return {
            "task_name": task_name,
            "status": "executed" if result.get("ok") else "failed",
            "memory_bridge": "restricted",
            "session_tags": session_tags,
            "allowed_operations": security_context["allowed_operations"],
            "required_capabilities": security_context["required_capabilities"],
            "restricted_operations": security_context["restricted_operations"],
            "result": result,
        }

    except ImportError:
        return {
            "task_name": task_name,
            "status": "bridge_ready",
            "message": (
                "Nodus runtime not found. Memory Bridge is available for "
                "direct API calls."
            ),
            "allowed_operations": allowed_operations or sorted(ALLOWED_OPERATION_CAPABILITIES.keys()),
            "available_operations": [
                "POST /memory/recall/v3",
                "POST /memory/suggest",
                "POST /memory/nodes/{id}/feedback",
            ],
        }
    except NodusSecurityError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "nodus_security_violation",
                "message": str(exc),
            },
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "nodus_execute_failed", "message": "Task execution failed", "details": str(exc)},
        ) from exc

