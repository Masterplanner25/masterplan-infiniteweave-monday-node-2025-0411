"""Bridge domain bootstrap."""
from __future__ import annotations


def register() -> None:
    _register_router()
    _register_response_adapters()
    _register_async_jobs()
    _register_flow_results()


def _register_router() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.bridge.routes.bridge_router import router as bridge_router
    register_router(bridge_router)


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from apps._adapters import (
        raw_json_adapter,
        raw_canonical_adapter,
        memory_execute_adapter,
        memory_completion_adapter,
    )

    register_response_adapter("bridge", raw_json_adapter)
    register_response_adapter("memory", raw_json_adapter)
    register_response_adapter("memory.execute", memory_execute_adapter)
    register_response_adapter("memory.execute.complete", memory_completion_adapter)
    register_response_adapter("memory.nodus.execute", raw_canonical_adapter)


def _register_async_jobs() -> None:
    from AINDY.platform_layer.async_job_service import register_async_job
    register_async_job("memory.nodus.execute")(_job_memory_nodus_execute)


def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result

    result_keys = {
        "memory_node_create": "memory_node_create_result",
        "memory_node_get": "memory_node_get_result",
        "memory_node_update": "memory_node_update_result",
        "memory_node_history": "memory_node_history_result",
        "memory_node_links": "memory_node_links_result",
        "memory_nodes_search_tags": "memory_nodes_search_tags_result",
        "memory_link_create": "memory_link_create_result",
        "memory_node_traverse": "memory_node_traverse_result",
        "memory_nodes_expand": "memory_nodes_expand_result",
        "memory_nodes_search_similar": "memory_nodes_search_similar_result",
        "memory_recall": "memory_recall_result",
        "memory_recall_v3": "memory_recall_v3_result",
        "memory_recall_federated": "memory_recall_federated_result",
        "memory_agents_list": "memory_agents_list_result",
        "memory_node_share": "memory_node_share_result",
        "memory_agent_recall": "memory_agent_recall_result",
        "memory_node_feedback": "memory_node_feedback_result",
        "memory_node_performance": "memory_node_performance_result",
        "memory_suggest": "memory_suggest_result",
    }
    for flow_name, result_key in result_keys.items():
        register_flow_result(flow_name, result_key=result_key)


def _job_memory_nodus_execute(payload: dict, db):
    from AINDY.runtime.nodus_execution_service import execute_nodus_task_payload
    return execute_nodus_task_payload(
        task_name=payload["task_name"],
        task_code=payload["task_code"],
        db=db,
        user_id=payload["user_id"],
        session_tags=payload.get("session_tags"),
        allowed_operations=payload.get("allowed_operations"),
        execution_id=payload.get("execution_id"),
        capability_token=payload.get("capability_token"),
    )
