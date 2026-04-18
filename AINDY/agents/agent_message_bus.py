from __future__ import annotations

from typing import Any

from AINDY.core.execution_signal_helper import queue_system_event


MESSAGE_TYPES = {
    "operation_request",
    "operation_result",
    "memory_share",
    "coordination_signal",
}


def publish_message(
    *,
    db,
    message_type: str,
    sender_agent_id: str,
    recipient_agent_id: str | None = None,
    user_id: str | None = None,
    trace_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str | None:
    if message_type not in MESSAGE_TYPES:
        raise ValueError(f"Unsupported message_type: {message_type}")
    return str(
        queue_system_event(
            db=db,
            event_type=f"agent.message.{message_type}",
            user_id=user_id,
            trace_id=trace_id,
            source="coordination",
            agent_id=sender_agent_id,
            payload={
                "message_type": message_type,
                "sender_agent_id": sender_agent_id,
                "recipient_agent_id": recipient_agent_id,
                **(payload or {}),
            },
            required=True,
        )
    )


def publish_operation_request(
    *,
    db,
    sender_agent_id: str,
    recipient_agent_id: str,
    operation: dict[str, Any],
    user_id: str | None = None,
    trace_id: str | None = None,
) -> str | None:
    return publish_message(
        db=db,
        message_type="operation_request",
        sender_agent_id=sender_agent_id,
        recipient_agent_id=recipient_agent_id,
        user_id=user_id,
        trace_id=trace_id,
        payload={"operation": operation},
    )


def publish_operation_result(
    *,
    db,
    sender_agent_id: str,
    recipient_agent_id: str | None,
    result: dict[str, Any],
    user_id: str | None = None,
    trace_id: str | None = None,
) -> str | None:
    return publish_message(
        db=db,
        message_type="operation_result",
        sender_agent_id=sender_agent_id,
        recipient_agent_id=recipient_agent_id,
        user_id=user_id,
        trace_id=trace_id,
        payload={"result": result},
    )


def publish_memory_share(
    *,
    db,
    sender_agent_id: str,
    recipient_agent_id: str | None,
    memory_node_id: str,
    user_id: str | None = None,
    trace_id: str | None = None,
) -> str | None:
    return publish_message(
        db=db,
        message_type="memory_share",
        sender_agent_id=sender_agent_id,
        recipient_agent_id=recipient_agent_id,
        user_id=user_id,
        trace_id=trace_id,
        payload={"memory_node_id": memory_node_id},
    )
