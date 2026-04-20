import logging

from AINDY.runtime.flow_engine import FLOW_REGISTRY, register_flow
from apps.automation.flows._flow_registration import (
    register_nodes,
    register_single_node_flows,
)

logger = logging.getLogger(__name__)


# -- Node functions -----------------------------------------------------------

def memory_node_create_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        dao = MemoryNodeDAO(db)
        result = dao.save(
            content=state.get("content"),
            source=state.get("source"),
            tags=state.get("tags", []),
            user_id=user_id,
            node_type=state.get("node_type"),
            extra=state.get("extra", {}),
        )
        return {"status": "SUCCESS", "output_patch": {"memory_node_create_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_node_get_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        dao = MemoryNodeDAO(db)
        node = dao.get_by_id(state.get("node_id"), user_id=user_id)
        if not node:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        if user_id is not None and str(node.get("user_id")) != str(user_id):
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_get_result": node}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_node_update_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        dao = MemoryNodeDAO(db)
        updated = dao.update(
            node_id=state.get("node_id"),
            user_id=user_id,
            content=state.get("content"),
            tags=state.get("tags"),
            node_type=state.get("node_type"),
            source=state.get("source"),
        )
        if not updated:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_update_result": dao._node_to_dict(updated)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_node_history_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        limit = state.get("limit", 20)
        dao = MemoryNodeDAO(db)
        history = dao.get_history(node_id=node_id, user_id=user_id, limit=limit)
        return {"status": "SUCCESS", "output_patch": {"memory_node_history_result": {"node_id": node_id, "history": history, "count": len(history)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_node_links_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        direction = state.get("direction", "both")
        if direction not in ("in", "out", "both"):
            return {"status": "FAILURE", "error": "HTTP_422:direction must be 'in', 'out', or 'both'"}
        dao = MemoryNodeDAO(db)
        if not dao.get_by_id(node_id, user_id=user_id):
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_links_result": {"nodes": dao.get_linked_nodes(node_id, direction=direction, user_id=user_id)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_nodes_search_tags_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        tags_str = state.get("tags", "")
        mode = state.get("mode", "AND")
        limit = state.get("limit", 50)
        if mode.upper() not in ("AND", "OR"):
            return {"status": "FAILURE", "error": "HTTP_422:mode must be 'AND' or 'OR'"}
        tag_list = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        dao = MemoryNodeDAO(db)
        return {"status": "SUCCESS", "output_patch": {"memory_nodes_search_tags_result": {"nodes": dao.get_by_tags(tag_list, limit=limit, mode=mode, user_id=user_id)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_link_create_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        dao = MemoryNodeDAO(db)
        source_id = state.get("source_id")
        target_id = state.get("target_id")
        if not dao.get_by_id(source_id, user_id=user_id):
            return {"status": "FAILURE", "error": "HTTP_404:Source node not found"}
        if not dao.get_by_id(target_id, user_id=user_id):
            return {"status": "FAILURE", "error": "HTTP_404:Target node not found"}
        try:
            result = dao.create_link(source_id, target_id, state.get("link_type", "related"), state.get("weight", 0.5), user_id=user_id)
        except ValueError as ve:
            return {"status": "FAILURE", "error": f"HTTP_422:Invalid memory link: {ve}"}
        return {"status": "SUCCESS", "output_patch": {"memory_link_create_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_node_traverse_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        max_depth = min(state.get("max_depth", 3), 5)
        dao = MemoryNodeDAO(db)
        result = dao.traverse(
            start_node_id=node_id,
            max_depth=max_depth,
            link_type=state.get("link_type"),
            user_id=user_id,
            min_strength=state.get("min_strength", 0.0),
        )
        if not result["found"]:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_traverse_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_nodes_expand_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_ids = state.get("node_ids", [])
        if len(node_ids) > 10:
            return {"status": "FAILURE", "error": "HTTP_400:Maximum 10 nodes per expansion request"}
        dao = MemoryNodeDAO(db)
        result = dao.expand(
            node_ids=node_ids,
            user_id=user_id,
            include_linked=state.get("include_linked", True),
            include_similar=state.get("include_similar", True),
            limit_per_node=state.get("limit_per_node", 3),
        )
        return {"status": "SUCCESS", "output_patch": {"memory_nodes_expand_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_nodes_search_similar_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.memory.embedding_service import generate_query_embedding

        db = context.get("db")
        user_id = str(context.get("user_id"))
        query = state.get("query", "")
        query_embedding = generate_query_embedding(query)
        dao = MemoryNodeDAO(db)
        results = dao.find_similar(
            query_embedding=query_embedding,
            limit=state.get("limit", 5),
            user_id=user_id,
            node_type=state.get("node_type"),
            min_similarity=state.get("min_similarity", 0.0),
        )
        return {"status": "SUCCESS", "output_patch": {"memory_nodes_search_similar_result": {"query": query, "results": results, "count": len(results)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_recall_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.runtime.memory import MemoryOrchestrator, memory_items_to_dicts

        db = context.get("db")
        user_id = str(context.get("user_id"))
        query = state.get("query")
        tags = state.get("tags")
        if not query and not tags:
            return {"status": "FAILURE", "error": "HTTP_400:Provide at least one of: query, tags"}
        metadata = {"tags": tags, "node_type": state.get("node_type"), "limit": state.get("limit", 5)}
        if state.get("node_type") is None:
            metadata["node_types"] = []
        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        context_obj = orchestrator.get_context(user_id=user_id, query=query or "", task_type="analysis", db=db, max_tokens=1200, metadata=metadata)
        results = memory_items_to_dicts(context_obj.items)
        return {"status": "SUCCESS", "output_patch": {"memory_recall_result": {"query": query, "tags": tags, "results": results, "count": len(results), "scoring_version": "v2", "formula": {"semantic": 0.40, "graph": 0.15, "recency": 0.15, "success_rate": 0.20, "usage_frequency": 0.10, "note": "adaptive_weight multiplier applied; tag_score adds up to +0.1"}}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_recall_v3_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.runtime.memory import MemoryOrchestrator, memory_items_to_dicts

        db = context.get("db")
        user_id = str(context.get("user_id"))
        query = state.get("query")
        tags = state.get("tags")
        if not query and not tags:
            return {"status": "FAILURE", "error": "HTTP_400:Provide at least one of: query, tags"}
        metadata = {"tags": tags, "node_type": state.get("node_type"), "limit": state.get("limit", 5)}
        if state.get("node_type") is None:
            metadata["node_types"] = []
        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        context_obj = orchestrator.get_context(user_id=user_id, query=query or "", task_type="analysis", db=db, max_tokens=1200, metadata=metadata)
        results = memory_items_to_dicts(context_obj.items)
        formula = {"semantic": 0.40, "graph": 0.15, "recency": 0.15, "success_rate": 0.20, "usage_frequency": 0.10, "note": "adaptive_weight multiplier applied; tag_score adds up to +0.1"}
        if state.get("expand_results") and context_obj.ids:
            dao = MemoryNodeDAO(db)
            expansion = dao.expand(node_ids=context_obj.ids[:3], user_id=user_id, include_linked=True, include_similar=True, limit_per_node=2)
            result = {"query": query, "tags": tags, "results": results, "expanded": expansion.get("expanded_nodes", []), "expansion_map": expansion.get("expansion_map", {}), "total_context_nodes": len(results) + len(expansion.get("expanded_nodes", [])), "scoring_version": "v2", "formula": formula}
        else:
            result = {"query": query, "tags": tags, "results": results, "count": len(results), "scoring_version": "v2", "formula": formula}
        return {"status": "SUCCESS", "output_patch": {"memory_recall_v3_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_recall_federated_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        query = state.get("query")
        tags = state.get("tags")
        if not query and not tags:
            return {"status": "FAILURE", "error": "HTTP_400:Provide at least one of: query, tags"}
        dao = MemoryNodeDAO(db)
        result = dao.recall_federated(query=query, tags=tags, agent_namespaces=state.get("agent_namespaces"), limit=state.get("limit", 5), user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"memory_recall_federated_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_agents_list_node(state, context):
    try:
        from AINDY.db.models.agent import Agent
        from AINDY.memory.memory_persistence import MemoryNodeModel
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        agents = db.query(Agent).filter(Agent.is_active.is_(True)).all()
        result_list = []
        for agent in agents:
            node_count = db.query(MemoryNodeModel).filter(MemoryNodeModel.source_agent == agent.memory_namespace, MemoryNodeModel.user_id == user_id).count()
            shared_count = db.query(MemoryNodeModel).filter(MemoryNodeModel.source_agent == agent.memory_namespace, MemoryNodeModel.user_id == user_id, MemoryNodeModel.is_shared.is_(True)).count()
            result_list.append({"id": agent.id, "name": agent.name, "agent_type": agent.agent_type, "description": agent.description, "memory_namespace": agent.memory_namespace, "is_active": agent.is_active, "memory_stats": {"total_nodes": node_count, "shared_nodes": shared_count, "private_nodes": node_count - shared_count}})
        return {"status": "SUCCESS", "output_patch": {"memory_agents_list_result": {"agents": result_list, "total": len(result_list)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_node_share_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        node_id = state.get("node_id")
        dao = MemoryNodeDAO(db)
        node = dao.share_memory(node_id=node_id, user_id=user_id)
        if not node:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_share_result": {"node_id": node_id, "is_shared": node.is_shared, "source_agent": node.source_agent, "message": "Memory node is now shared with all agents."}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_agent_recall_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        namespace = state.get("namespace", "")
        dao = MemoryNodeDAO(db)
        results = dao.recall_from_agent(agent_namespace=namespace, query=state.get("query"), limit=state.get("limit", 5), user_id=user_id, include_private=False)
        return {"status": "SUCCESS", "output_patch": {"memory_agent_recall_result": {"agent_namespace": namespace, "query": state.get("query"), "results": results, "count": len(results)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_node_feedback_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        outcome = state.get("outcome")
        dao = MemoryNodeDAO(db)
        node = dao.record_feedback(node_id=node_id, outcome=outcome, user_id=user_id)
        if not node:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_feedback_result": {"node_id": node_id, "outcome": outcome, "success_count": node.success_count, "failure_count": node.failure_count, "usage_count": node.usage_count, "adaptive_weight": node.weight, "success_rate": dao.get_success_rate(node), "message": {"success": "Weight boosted - memory reinforced", "failure": "Weight reduced - memory suppressed", "neutral": "Usage recorded - no weight change"}[outcome]}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_node_performance_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        dao = MemoryNodeDAO(db)
        node = dao._get_model_by_id(node_id, user_id=user_id)
        if not node:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        success_rate = dao.get_success_rate(node)
        usage_freq = dao.get_usage_frequency_score(node)
        graph_score = dao.get_graph_connectivity_score(node_id)
        total_feedback = (node.success_count or 0) + (node.failure_count or 0)
        return {"status": "SUCCESS", "output_patch": {"memory_node_performance_result": {"node_id": node_id, "content_preview": (node.content or "")[:100], "node_type": node.node_type, "performance": {"success_count": node.success_count or 0, "failure_count": node.failure_count or 0, "usage_count": node.usage_count or 0, "success_rate": round(success_rate, 3), "adaptive_weight": round(node.weight or 1.0, 3), "last_outcome": node.last_outcome, "last_used_at": node.last_used_at.isoformat() if node.last_used_at else None, "total_feedback_signals": total_feedback, "graph_connectivity": round(graph_score, 3), "usage_frequency_score": round(usage_freq, 3)}, "resonance_v2_preview": {"note": "Scores shown for this node in isolation. Actual resonance depends on query context.", "success_rate_component": round(success_rate * 0.20, 4), "usage_freq_component": round(usage_freq * 0.10, 4), "graph_component": round(graph_score * 0.15, 4), "adaptive_weight": round(node.weight or 1.0, 3)}}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_suggest_node(state, context):
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO

        db = context.get("db")
        user_id = str(context.get("user_id"))
        query = state.get("query")
        tags = state.get("tags")
        if not query and not tags:
            return {"status": "FAILURE", "error": "HTTP_400:Provide at least one of: query, tags"}
        dao = MemoryNodeDAO(db)
        result = dao.suggest(query=query, tags=tags, context=state.get("context"), user_id=user_id, limit=state.get("limit", 3))
        return {"status": "SUCCESS", "output_patch": {"memory_suggest_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def memory_nodus_execute_node(state, context):
    try:
        from AINDY.core.execution_envelope import success
        from AINDY.runtime.nodus_execution_service import execute_nodus_task_payload
        from AINDY.runtime.nodus_security import NodusSecurityError
        from AINDY.platform_layer.trace_context import ensure_trace_id
        from AINDY.platform_layer.user_ids import require_user_id

        db = context.get("db")
        user_id = str(require_user_id(context.get("user_id")))
        try:
            result = execute_nodus_task_payload(
                task_name=state.get("task_name"),
                task_code=state.get("task_code"),
                db=db,
                user_id=user_id,
                session_tags=state.get("session_tags", []),
                allowed_operations=state.get("allowed_operations"),
                execution_id=state.get("execution_id"),
                capability_token=state.get("capability_token"),
            )
            if isinstance(result, dict) and {"status", "result", "events", "next_action", "trace_id"}.issubset(result.keys()):
                return {"status": "SUCCESS", "output_patch": {"memory_nodus_execute_result": result}}
            return {"status": "SUCCESS", "output_patch": {"memory_nodus_execute_result": success(result, [], ensure_trace_id())}}
        except NodusSecurityError as exc:
            return {"status": "FAILURE", "error": f"HTTP_403:nodus_security_violation: {exc}"}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# -- Registration -------------------------------------------------------------

def register() -> None:
    register_nodes(
        {
            "memory_node_create_node": memory_node_create_node,
            "memory_node_get_node": memory_node_get_node,
            "memory_node_update_node": memory_node_update_node,
            "memory_node_history_node": memory_node_history_node,
            "memory_node_links_node": memory_node_links_node,
            "memory_nodes_search_tags_node": memory_nodes_search_tags_node,
            "memory_link_create_node": memory_link_create_node,
            "memory_node_traverse_node": memory_node_traverse_node,
            "memory_nodes_expand_node": memory_nodes_expand_node,
            "memory_nodes_search_similar_node": memory_nodes_search_similar_node,
            "memory_recall_node": memory_recall_node,
            "memory_recall_v3_node": memory_recall_v3_node,
            "memory_recall_federated_node": memory_recall_federated_node,
            "memory_agents_list_node": memory_agents_list_node,
            "memory_node_share_node": memory_node_share_node,
            "memory_agent_recall_node": memory_agent_recall_node,
            "memory_node_feedback_node": memory_node_feedback_node,
            "memory_node_performance_node": memory_node_performance_node,
            "memory_suggest_node": memory_suggest_node,
            "memory_nodus_execute_node": memory_nodus_execute_node,
        }
    )
    register_single_node_flows(
        {
            "memory_node_create": "memory_node_create_node",
            "memory_node_get": "memory_node_get_node",
            "memory_node_update": "memory_node_update_node",
            "memory_node_history": "memory_node_history_node",
            "memory_node_links": "memory_node_links_node",
            "memory_nodes_search_tags": "memory_nodes_search_tags_node",
            "memory_link_create": "memory_link_create_node",
            "memory_node_traverse": "memory_node_traverse_node",
            "memory_nodes_expand": "memory_nodes_expand_node",
            "memory_nodes_search_similar": "memory_nodes_search_similar_node",
            "memory_recall": "memory_recall_node",
            "memory_recall_v3": "memory_recall_v3_node",
            "memory_recall_federated": "memory_recall_federated_node",
            "memory_agents_list": "memory_agents_list_node",
            "memory_node_share": "memory_node_share_node",
            "memory_agent_recall": "memory_agent_recall_node",
            "memory_node_feedback": "memory_node_feedback_node",
            "memory_node_performance": "memory_node_performance_node",
            "memory_suggest": "memory_suggest_node",
            "memory_nodus_execute": "memory_nodus_execute_node",
        }
    )

    if "memory_execute_loop" not in FLOW_REGISTRY:
        register_flow(
            "memory_execute_loop",
            {
                "start": "memory_execution_validate",
                "edges": {
                    "memory_execution_validate": ["memory_execution_run"],
                    "memory_execution_run": ["memory_execution_orchestrate"],
                },
                "end": ["memory_execution_orchestrate"],
            },
        )
