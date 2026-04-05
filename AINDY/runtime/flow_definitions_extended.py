"""
flow_definitions_extended.py — Hard Execution Boundary node extensions.

All single-node flows required to route every router endpoint through
run_flow().  Registered via register_extended_flows() called from
register_all_flows() in flow_definitions.py.

Node contract: fn(state, context) -> {"status": "SUCCESS"|"FAILURE", "output_patch": {...}}
Special HTTP responses are encoded in the result key as:
  {"_http_status": 202, "_http_response": {...}}   for 202 deferred
  {"_decision_response": {...}}                     for autonomy ignore/defer
  {"_http_error": {"status_code": N, "detail": ...}} for 4xx/5xx from nodes
"""
import logging
from runtime.flow_engine import FLOW_REGISTRY, register_flow, register_node

logger = logging.getLogger(__name__)

_single = lambda start: {"start": start, "edges": {}, "end": [start]}  # noqa: E731


# ── ARM ────────────────────────────────────────────────────────────────────────

@register_node("arm_logs_node")
def arm_logs_node(state, context):
    try:
        from uuid import UUID
        from db.models.arm_models import AnalysisResult, CodeGeneration
        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        limit = state.get("limit", 20)
        analyses = (
            db.query(AnalysisResult)
            .filter(AnalysisResult.user_id == user_id)
            .order_by(AnalysisResult.created_at.desc())
            .limit(limit)
            .all()
        )
        generations = (
            db.query(CodeGeneration)
            .filter(CodeGeneration.user_id == user_id)
            .order_by(CodeGeneration.created_at.desc())
            .limit(limit)
            .all()
        )
        result = {
            "analyses": [
                {
                    "session_id": str(a.session_id),
                    "file": (a.file_path or "").split("/")[-1].split("\\")[-1],
                    "status": a.status,
                    "execution_seconds": a.execution_seconds,
                    "input_tokens": a.input_tokens,
                    "output_tokens": a.output_tokens,
                    "task_priority": a.task_priority,
                    "execution_speed": round(
                        ((a.input_tokens or 0) + (a.output_tokens or 0))
                        / max(a.execution_seconds or 0.001, 0.001),
                        1,
                    ),
                    "summary": a.result_summary,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in analyses
            ],
            "generations": [
                {
                    "session_id": str(g.session_id),
                    "language": g.language,
                    "generation_type": g.generation_type,
                    "execution_seconds": g.execution_seconds,
                    "input_tokens": g.input_tokens,
                    "output_tokens": g.output_tokens,
                    "created_at": g.created_at.isoformat() if g.created_at else None,
                }
                for g in generations
            ],
            "summary": {
                "total_analyses": len(analyses),
                "total_generations": len(generations),
                "total_tokens_used": sum((a.input_tokens or 0) + (a.output_tokens or 0) for a in analyses)
                + sum((g.input_tokens or 0) + (g.output_tokens or 0) for g in generations),
            },
        }
        return {"status": "SUCCESS", "output_patch": {"arm_logs_result": result}}
    except Exception as e:
        logger.error("arm_logs_node error: %s", e)
        return {"status": "FAILURE", "error": str(e)}


@register_node("arm_config_get_node")
def arm_config_get_node(state, context):
    try:
        from modules.deepseek.config_manager_deepseek import ConfigManager
        return {"status": "SUCCESS", "output_patch": {"arm_config_get_result": ConfigManager().get_all()}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("arm_config_update_node")
def arm_config_update_node(state, context):
    try:
        from modules.deepseek.config_manager_deepseek import ConfigManager
        updated = ConfigManager().update(state.get("updates", {}))
        return {"status": "SUCCESS", "output_patch": {"arm_config_update_result": {"status": "updated", "config": updated}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("arm_metrics_node")
def arm_metrics_node(state, context):
    try:
        from analytics.arm_metrics_service import ARMMetricsService
        db = context.get("db")
        user_id = context.get("user_id")
        window = state.get("window", 30)
        result = ARMMetricsService(db=db, user_id=user_id).get_all_metrics(window=window)
        return {"status": "SUCCESS", "output_patch": {"arm_metrics_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("arm_config_suggest_node")
def arm_config_suggest_node(state, context):
    try:
        from modules.deepseek.config_manager_deepseek import ConfigManager
        from analytics.arm_metrics_service import ARMMetricsService, ARMConfigSuggestionEngine
        db = context.get("db")
        user_id = context.get("user_id")
        window = state.get("window", 30)
        metrics = ARMMetricsService(db=db, user_id=user_id).get_all_metrics(window=window)
        current_config = ConfigManager().get_all()
        suggestions = ARMConfigSuggestionEngine(current_config=current_config, metrics=metrics).generate_suggestions()
        suggestions["metrics_snapshot"] = {
            "decision_efficiency": metrics.get("decision_efficiency", {}).get("score", 0),
            "execution_speed_avg": metrics.get("execution_speed", {}).get("average", 0),
            "ai_productivity_ratio": metrics.get("ai_productivity_boost", {}).get("ratio", 0),
            "waste_percentage": metrics.get("lost_potential", {}).get("waste_percentage", 0),
            "learning_trend": metrics.get("learning_efficiency", {}).get("trend", "insufficient data"),
            "total_sessions": metrics.get("total_sessions", 0),
        }
        return {"status": "SUCCESS", "output_patch": {"arm_config_suggest_result": suggestions}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Goals ──────────────────────────────────────────────────────────────────────

@register_node("goals_list_node")
def goals_list_node(state, context):
    try:
        from domain.goal_service import get_active_goals
        db = context.get("db")
        user_id = context.get("user_id")
        return {"status": "SUCCESS", "output_patch": {"goals_list_result": get_active_goals(db, user_id)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("goals_state_node")
def goals_state_node(state, context):
    try:
        from domain.goal_service import detect_goal_drift, get_goal_states
        db = context.get("db")
        user_id = context.get("user_id")
        result = {
            "goals": get_goal_states(db, user_id),
            "drift": detect_goal_drift(db, user_id),
        }
        return {"status": "SUCCESS", "output_patch": {"goals_state_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Score ──────────────────────────────────────────────────────────────────────

@register_node("score_get_node")
def score_get_node(state, context):
    try:
        import uuid
        from db.models.user_score import UserScore, KPI_WEIGHTS
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))

        score = db.query(UserScore).filter(UserScore.user_id == user_id).first()
        if not score:
            from domain.infinity_orchestrator import execute as execute_infinity_orchestrator
            result = execute_infinity_orchestrator(user_id=user_id, db=db, trigger_event="manual")
            if result:
                return {"status": "SUCCESS", "output_patch": {"score_get_result": result["score"]}}
            return {"status": "SUCCESS", "output_patch": {"score_get_result": {
                "user_id": str(user_id), "master_score": 0.0, "kpis": {}, "message": "No score yet.",
            }}}

        from domain.infinity_loop import get_latest_adjustment, serialize_adjustment
        latest = get_latest_adjustment(user_id=str(user_id), db=db)
        serialized = serialize_adjustment(latest)
        latest_payload = None
        memory_visibility = {"memory_context_count": 0, "memory_signal_count": 0}
        if serialized:
            adj_payload = (serialized.get("adjustment_payload") or {})
            loop_context = adj_payload.get("loop_context") or {}
            memory_signals = list(loop_context.get("memory_signals") or [])
            memory_visibility = {
                "memory_context_count": len(loop_context.get("memory") or []),
                "memory_signal_count": len(memory_signals),
            }
            latest_payload = {
                "decision_type": serialized["decision_type"],
                "applied_at": serialized["applied_at"],
                "adjustment_payload": serialized["adjustment_payload"],
            }

        result = {
            "user_id": str(user_id),
            "master_score": score.master_score,
            "kpis": {
                "execution_speed": score.execution_speed_score,
                "decision_efficiency": score.decision_efficiency_score,
                "ai_productivity_boost": score.ai_productivity_boost_score,
                "focus_quality": score.focus_quality_score,
                "masterplan_progress": score.masterplan_progress_score,
            },
            "weights": KPI_WEIGHTS,
            "metadata": {
                "confidence": score.confidence,
                "data_points_used": score.data_points_used,
                "trigger_event": score.trigger_event,
                "calculated_at": score.calculated_at.isoformat() if score.calculated_at else None,
                "memory_context_count": memory_visibility["memory_context_count"],
                "memory_signal_count": memory_visibility["memory_signal_count"],
            },
            "latest_adjustment": latest_payload,
        }
        return {"status": "SUCCESS", "output_patch": {"score_get_result": result}}
    except Exception as e:
        logger.error("score_get_node error: %s", e)
        return {"status": "FAILURE", "error": str(e)}


@register_node("score_history_node")
def score_history_node(state, context):
    try:
        import uuid
        from db.models.user_score import ScoreHistory
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        limit = state.get("limit", 30)
        history = (
            db.query(ScoreHistory)
            .filter(ScoreHistory.user_id == user_id)
            .order_by(ScoreHistory.calculated_at.desc())
            .limit(limit)
            .all()
        )
        result = {
            "user_id": str(user_id),
            "history": [
                {
                    "master_score": h.master_score,
                    "calculated_at": h.calculated_at.isoformat() if h.calculated_at else None,
                }
                for h in history
            ],
        }
        return {"status": "SUCCESS", "output_patch": {"score_history_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("score_feedback_list_node")
def score_feedback_list_node(state, context):
    try:
        import uuid
        from db.models.infinity_loop import UserFeedback
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        limit = state.get("limit", 50)
        history = (
            db.query(UserFeedback)
            .filter(UserFeedback.user_id == user_id)
            .order_by(UserFeedback.created_at.desc())
            .limit(limit)
            .all()
        )
        return {"status": "SUCCESS", "output_patch": {"score_feedback_list_result": {
            "user_id": str(user_id),
            "count": len(history),
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── LeadGen ────────────────────────────────────────────────────────────────────

@register_node("leadgen_list_node")
def leadgen_list_node(state, context):
    try:
        import uuid
        from db.models.leadgen_model import LeadGenResult
        from schemas.leadgen_schema import LeadGenItem
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        results = (
            db.query(LeadGenResult)
            .filter(LeadGenResult.user_id == user_id)
            .order_by(LeadGenResult.created_at.desc())
            .all()
        )
        data = [
            LeadGenItem(
                company=r.company,
                url=r.url,
                fit_score=r.fit_score,
                intent_score=r.intent_score,
                data_quality_score=r.data_quality_score,
                overall_score=r.overall_score,
                reasoning=r.reasoning,
                created_at=r.created_at,
            ).model_dump()
            for r in results
        ]
        return {"status": "SUCCESS", "output_patch": {"leadgen_list_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("leadgen_preview_search_node")
def leadgen_preview_search_node(state, context):
    try:
        from domain.search_service import search_leads
        db = context.get("db")
        user_id = context.get("user_id")
        query = state.get("query", "")
        result = search_leads(query, db=db, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"leadgen_preview_search_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Tasks ──────────────────────────────────────────────────────────────────────

@register_node("tasks_list_node")
def tasks_list_node(state, context):
    try:
        import uuid
        from db.models.task import Task
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        tasks = db.query(Task).filter(Task.user_id == user_id).all()
        data = [
            {
                "task_id": t.id,
                "task_name": t.name,
                "category": t.category,
                "priority": t.priority,
                "status": getattr(t, "status", "unknown"),
                "time_spent": t.time_spent,
                "masterplan_id": getattr(t, "masterplan_id", None),
                "parent_task_id": getattr(t, "parent_task_id", None),
                "depends_on": getattr(t, "depends_on", []) or [],
                "dependency_type": getattr(t, "dependency_type", "hard"),
                "automation_type": getattr(t, "automation_type", None),
                "automation_config": getattr(t, "automation_config", None),
            }
            for t in tasks
        ]
        return {"status": "SUCCESS", "output_patch": {"tasks_list_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("tasks_recurrence_check_node")
def tasks_recurrence_check_node(state, context):
    try:
        import threading
        from domain.task_services import handle_recurrence
        t = threading.Thread(target=handle_recurrence, daemon=True)
        t.start()
        return {"status": "SUCCESS", "output_patch": {"tasks_recurrence_check_result": {
            "message": "Recurrence job started in background."
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Agent ──────────────────────────────────────────────────────────────────────

@register_node("agent_run_create_node")
def agent_run_create_node(state, context):
    try:
        from agents.agent_runtime import create_run, execute_run, to_execution_response
        from platform_layer.async_job_service import (
            async_heavy_execution_enabled,
            build_queued_response,
            submit_autonomous_async_job,
        )
        from agents.autonomous_controller import build_decision_response, evaluate_live_trigger, record_decision
        from platform_layer.async_job_service import defer_async_job
        from utils.trace_context import ensure_trace_id
        from utils.uuid_utils import normalize_uuid

        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        goal = state.get("goal", "").strip()

        if async_heavy_execution_enabled():
            response = submit_autonomous_async_job(
                task_name="agent.create_run",
                payload={"goal": goal, "user_id": str(user_id)},
                user_id=user_id,
                source="agent_router",
                trigger_type="user",
                trigger_context={"goal": goal, "importance": 0.95},
            )
            return {"status": "SUCCESS", "output_patch": {"agent_run_create_result": {
                "_http_status": 202, "_http_response": response,
            }}}

        trace_id = ensure_trace_id()
        trigger_context = {"goal": goal, "importance": 0.95}
        trigger = {"trigger_type": "user", "source": "agent_router", "goal": goal}
        evaluation = evaluate_live_trigger(db=db, trigger=trigger, user_id=user_id, context=trigger_context)
        record_decision(db=db, trigger=trigger, evaluation=evaluation, user_id=user_id, trace_id=trace_id, context=trigger_context)

        if evaluation["decision"] == "ignore":
            return {"status": "SUCCESS", "output_patch": {"agent_run_create_result": {
                "_decision_response": build_decision_response(evaluation, trace_id=trace_id),
            }}}
        if evaluation["decision"] == "defer":
            log_id = defer_async_job(
                task_name="agent.create_run",
                payload={"goal": goal, "user_id": str(user_id), "__autonomy": {"trigger_type": "user", "source": "agent_router", "context": trigger_context}},
                user_id=user_id, source="agent_router", decision=evaluation,
            )
            return {"status": "SUCCESS", "output_patch": {"agent_run_create_result": {
                "_http_status": 202,
                "_http_response": build_decision_response(
                    evaluation, trace_id=log_id,
                    result={"automation_log_id": log_id, "decision": "defer", "reason": evaluation["reason"]},
                    next_action={"type": "poll_automation_log", "automation_log_id": log_id},
                ),
            }}}

        run = create_run(goal=goal, user_id=user_id, db=db)
        if not run:
            return {"status": "FAILURE", "error": "HTTP_500:Failed to generate plan"}
        if run["status"] == "approved":
            run = execute_run(run_id=run["run_id"], user_id=user_id, db=db) or run
        return {"status": "SUCCESS", "output_patch": {"agent_run_create_result": to_execution_response(run, db)}}
    except Exception as e:
        logger.error("agent_run_create_node error: %s", e)
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_runs_list_node")
def agent_runs_list_node(state, context):
    try:
        from db.models.agent_run import AgentRun
        from agents.agent_runtime import _run_to_dict
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        status_filter = state.get("status")
        limit = state.get("limit", 20)
        query = db.query(AgentRun).filter(AgentRun.user_id == user_id)
        if status_filter:
            query = query.filter(AgentRun.status == status_filter)
        runs = query.order_by(AgentRun.created_at.desc()).limit(limit).all()
        return {"status": "SUCCESS", "output_patch": {"agent_runs_list_result": [_run_to_dict(r) for r in runs]}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_run_get_node")
def agent_run_get_node(state, context):
    try:
        from db.models.agent_run import AgentRun
        from agents.agent_runtime import _run_to_dict
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        try:
            run_id = normalize_uuid(state.get("run_id"))
        except Exception:
            return {"status": "FAILURE", "error": "HTTP_400:Invalid run_id"}
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Run not found"}
        if run.user_id != user_id:
            return {"status": "FAILURE", "error": "HTTP_403:Not authorized"}
        return {"status": "SUCCESS", "output_patch": {"agent_run_get_result": _run_to_dict(run)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_run_approve_node")
def agent_run_approve_node(state, context):
    try:
        from agents.agent_runtime import approve_run, to_execution_response
        from platform_layer.async_job_service import async_heavy_execution_enabled, submit_autonomous_async_job
        from agents.autonomous_controller import build_decision_response, evaluate_live_trigger, record_decision
        from platform_layer.async_job_service import defer_async_job
        from utils.trace_context import ensure_trace_id
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        run_id = state.get("run_id")

        if async_heavy_execution_enabled():
            response = submit_autonomous_async_job(
                task_name="agent.approve_run",
                payload={"run_id": run_id, "user_id": str(user_id)},
                user_id=user_id, source="agent_router", trigger_type="user",
                trigger_context={"goal": f"approve_run:{run_id}", "importance": 0.9},
            )
            return {"status": "SUCCESS", "output_patch": {"agent_run_approve_result": {
                "_http_status": 202, "_http_response": response,
            }}}

        trace_id = ensure_trace_id()
        trigger_context = {"goal": f"approve_run:{run_id}", "importance": 0.9}
        trigger = {"trigger_type": "user", "source": "agent_router.approve", "goal": f"approve_run:{run_id}"}
        evaluation = evaluate_live_trigger(db=db, trigger=trigger, user_id=user_id, context=trigger_context)
        record_decision(db=db, trigger=trigger, evaluation=evaluation, user_id=user_id, trace_id=trace_id, context=trigger_context)

        if evaluation["decision"] == "ignore":
            return {"status": "SUCCESS", "output_patch": {"agent_run_approve_result": {
                "_decision_response": build_decision_response(evaluation, trace_id=trace_id),
            }}}
        if evaluation["decision"] == "defer":
            log_id = defer_async_job(
                task_name="agent.approve_run",
                payload={"run_id": run_id, "user_id": str(user_id), "__autonomy": {"trigger_type": "user", "source": "agent_router.approve", "context": trigger_context}},
                user_id=user_id, source="agent_router", decision=evaluation,
            )
            return {"status": "SUCCESS", "output_patch": {"agent_run_approve_result": {
                "_http_status": 202,
                "_http_response": build_decision_response(
                    evaluation, trace_id=log_id,
                    result={"automation_log_id": log_id, "decision": "defer", "reason": evaluation["reason"]},
                    next_action={"type": "poll_automation_log", "automation_log_id": log_id},
                ),
            }}}

        run = approve_run(run_id=run_id, user_id=user_id, db=db)
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Run not found or not approvable"}
        return {"status": "SUCCESS", "output_patch": {"agent_run_approve_result": to_execution_response(run, db)}}
    except Exception as e:
        logger.error("agent_run_approve_node error: %s", e)
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_run_reject_node")
def agent_run_reject_node(state, context):
    try:
        from agents.agent_runtime import reject_run, to_execution_response
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        run = reject_run(run_id=state.get("run_id"), user_id=user_id, db=db)
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Run not found or not rejectable"}
        return {"status": "SUCCESS", "output_patch": {"agent_run_reject_result": to_execution_response(run, db)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_run_recover_node")
def agent_run_recover_node(state, context):
    try:
        from agents.agent_runtime import to_execution_response
        from agents.stuck_run_service import recover_stuck_agent_run
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        result = recover_stuck_agent_run(
            run_id=state.get("run_id"), user_id=user_id, db=db, force=state.get("force", False)
        )
        if result["ok"]:
            return {"status": "SUCCESS", "output_patch": {"agent_run_recover_result": to_execution_response(result["run"], db)}}
        error_code = result.get("error_code", "internal_error")
        http_map = {"not_found": 404, "forbidden": 403, "wrong_status": 409, "too_recent": 409}
        http_status = http_map.get(error_code, 500)
        detail = result.get("detail", error_code)
        return {"status": "FAILURE", "error": f"HTTP_{http_status}:{detail}"}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_run_replay_node")
def agent_run_replay_node(state, context):
    try:
        from agents.agent_runtime import replay_run, to_execution_response
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        new_run = replay_run(run_id=state.get("run_id"), user_id=user_id, db=db)
        if not new_run:
            return {"status": "FAILURE", "error": "HTTP_404:Run not found or not replayable"}
        return {"status": "SUCCESS", "output_patch": {"agent_run_replay_result": to_execution_response(new_run, db)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_run_steps_node")
def agent_run_steps_node(state, context):
    try:
        from db.models.agent_run import AgentRun, AgentStep
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        run_id = normalize_uuid(state.get("run_id"))
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Run not found"}
        if run.user_id != user_id:
            return {"status": "FAILURE", "error": "HTTP_403:Not authorized"}
        steps = (
            db.query(AgentStep)
            .filter(AgentStep.run_id == run_id)
            .order_by(AgentStep.step_index.asc())
            .all()
        )
        data = [
            {
                "step_index": s.step_index,
                "tool_name": s.tool_name,
                "description": s.description,
                "risk_level": s.risk_level,
                "status": s.status,
                "result": s.result,
                "error_message": s.error_message,
                "execution_ms": s.execution_ms,
                "executed_at": s.executed_at.isoformat() if s.executed_at else None,
            }
            for s in steps
        ]
        return {"status": "SUCCESS", "output_patch": {"agent_run_steps_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_run_events_node")
def agent_run_events_node(state, context):
    try:
        from db.models.agent_run import AgentRun
        from agents.agent_runtime import get_run_events
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        run_id = state.get("run_id")
        try:
            normalized_run_id = normalize_uuid(run_id)
        except Exception:
            return {"status": "FAILURE", "error": "HTTP_400:Invalid run_id"}
        result = get_run_events(run_id=run_id, user_id=user_id, db=db)
        if result is None:
            run = db.query(AgentRun).filter(AgentRun.id == normalized_run_id).first()
            if not run:
                return {"status": "FAILURE", "error": "HTTP_404:Run not found"}
            return {"status": "FAILURE", "error": "HTTP_403:Not authorized"}
        return {"status": "SUCCESS", "output_patch": {"agent_run_events_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_tools_list_node")
def agent_tools_list_node(state, context):
    try:
        from agents.agent_tools import TOOL_REGISTRY
        data = [
            {
                "name": name,
                "risk": entry["risk"],
                "description": entry["description"],
                "capability": entry.get("capability"),
                "required_capability": entry.get("required_capability"),
                "category": entry.get("category"),
                "egress_scope": entry.get("egress_scope"),
            }
            for name, entry in TOOL_REGISTRY.items()
        ]
        return {"status": "SUCCESS", "output_patch": {"agent_tools_list_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_trust_get_node")
def agent_trust_get_node(state, context):
    try:
        from db.models.agent_run import AgentTrustSettings
        from agents.capability_service import get_auto_grantable_tools
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        trust = db.query(AgentTrustSettings).filter(AgentTrustSettings.user_id == user_id).first()
        result = {
            "user_id": str(user_id),
            "auto_execute_low": trust.auto_execute_low if trust else False,
            "auto_execute_medium": trust.auto_execute_medium if trust else False,
            "allowed_auto_grant_tools": (
                trust.allowed_auto_grant_tools
                if trust and trust.allowed_auto_grant_tools is not None
                else get_auto_grantable_tools(user_id=user_id, db=db)
            ),
            "note": "High-risk plans always require approval regardless of trust settings.",
        }
        return {"status": "SUCCESS", "output_patch": {"agent_trust_get_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_trust_update_node")
def agent_trust_update_node(state, context):
    try:
        from datetime import datetime, timezone
        from db.models.agent_run import AgentTrustSettings
        from agents.agent_tools import TOOL_REGISTRY
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        trust = db.query(AgentTrustSettings).filter(AgentTrustSettings.user_id == user_id).first()
        if not trust:
            trust = AgentTrustSettings(user_id=user_id)
            db.add(trust)
        auto_low = state.get("auto_execute_low")
        auto_medium = state.get("auto_execute_medium")
        allowed_tools = state.get("allowed_auto_grant_tools")
        if auto_low is not None:
            trust.auto_execute_low = auto_low
        if auto_medium is not None:
            trust.auto_execute_medium = auto_medium
        if allowed_tools is not None:
            trust.allowed_auto_grant_tools = sorted({
                t for t in allowed_tools
                if t in TOOL_REGISTRY and TOOL_REGISTRY[t]["risk"] in {"low", "medium"} and t != "genesis.message"
            })
        trust.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(trust)
        result = {
            "user_id": str(user_id),
            "auto_execute_low": trust.auto_execute_low,
            "auto_execute_medium": trust.auto_execute_medium,
            "allowed_auto_grant_tools": trust.allowed_auto_grant_tools or [],
            "note": "High-risk plans always require approval regardless of trust settings.",
        }
        return {"status": "SUCCESS", "output_patch": {"agent_trust_update_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("agent_suggestions_get_node")
def agent_suggestions_get_node(state, context):
    try:
        from agents.agent_tools import suggest_tools
        from domain.infinity_service import get_user_kpi_snapshot
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        snapshot = get_user_kpi_snapshot(user_id=user_id, db=db)
        result = suggest_tools(kpi_snapshot=snapshot, user_id=user_id, db=db)
        return {"status": "SUCCESS", "output_patch": {"agent_suggestions_get_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Analytics ──────────────────────────────────────────────────────────────────

@register_node("analytics_linkedin_ingest_node")
def analytics_linkedin_ingest_node(state, context):
    try:
        import uuid
        from db.models import MasterPlan
        from db.models.metrics_models import CanonicalMetricDB
        from schemas.analytics import LinkedInRawInput
        from analytics.linkedin_adapter import linkedin_adapter
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        data_dict = state.get("data", {})
        masterplan_id = data_dict.get("masterplan_id")

        plan = db.query(MasterPlan).filter(
            MasterPlan.id == masterplan_id,
            MasterPlan.user_id == user_id,
        ).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:MasterPlan not found"}

        data = LinkedInRawInput(**data_dict)
        canonical = linkedin_adapter(data)
        canonical["user_id"] = user_id

        existing = db.query(CanonicalMetricDB).filter_by(
            masterplan_id=canonical["masterplan_id"],
            platform=canonical["platform"],
            scope_type=canonical["scope_type"],
            scope_id=canonical["scope_id"],
            period_type=canonical["period_type"],
            period_start=canonical["period_start"],
        ).first()

        if existing:
            for key, value in canonical.items():
                setattr(existing, key, value)
            db_record = existing
        else:
            db_record = CanonicalMetricDB(**canonical)
            db.add(db_record)

        db.commit()
        db.refresh(db_record)
        return {"status": "SUCCESS", "output_patch": {"analytics_linkedin_ingest_result": db_record}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("analytics_masterplan_get_node")
def analytics_masterplan_get_node(state, context):
    try:
        import uuid
        from db.models import MasterPlan
        from db.models.metrics_models import CanonicalMetricDB
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        masterplan_id = state.get("masterplan_id")
        period_type = state.get("period_type")
        platform = state.get("platform")
        scope_type = state.get("scope_type")

        plan = db.query(MasterPlan).filter(
            MasterPlan.id == masterplan_id,
            MasterPlan.user_id == user_id,
        ).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:MasterPlan not found"}

        query = db.query(CanonicalMetricDB).filter(CanonicalMetricDB.masterplan_id == masterplan_id)
        if period_type:
            query = query.filter(CanonicalMetricDB.period_type == period_type)
        if platform:
            query = query.filter(CanonicalMetricDB.platform == platform)
        if scope_type:
            query = query.filter(CanonicalMetricDB.scope_type == scope_type)

        return {"status": "SUCCESS", "output_patch": {
            "analytics_masterplan_get_result": query.order_by(CanonicalMetricDB.period_start.desc()).all()
        }}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("analytics_masterplan_summary_node")
def analytics_masterplan_summary_node(state, context):
    try:
        import uuid
        from db.models import MasterPlan
        from db.models.metrics_models import CanonicalMetricDB
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        masterplan_id = state.get("masterplan_id")
        group_by = state.get("group_by")

        plan = db.query(MasterPlan).filter(
            MasterPlan.id == masterplan_id,
            MasterPlan.user_id == user_id,
        ).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:MasterPlan not found"}

        records = (
            db.query(CanonicalMetricDB)
            .filter(CanonicalMetricDB.masterplan_id == masterplan_id)
            .order_by(CanonicalMetricDB.period_start.asc())
            .all()
        )
        if not records:
            return {"status": "SUCCESS", "output_patch": {"analytics_masterplan_summary_result": {"message": "No telemetry records found."}}}

        if group_by == "period":
            grouped = {}
            for r in records:
                key = (r.period_type, r.period_start)
                if key not in grouped:
                    grouped[key] = {"period_type": r.period_type, "period_start": r.period_start, "period_end": r.period_end,
                                    "totals": {k: 0 for k in ["passive_visibility", "active_discovery", "unique_reach",
                                                               "interaction_volume", "deep_attention_units", "intent_signals",
                                                               "conversion_events", "growth_velocity"]}}
                g = grouped[key]["totals"]
                for k in g:
                    g[k] += getattr(r, k) or 0
            output = []
            for (ptype, pstart), data in grouped.items():
                t = data["totals"]
                vis = t["passive_visibility"] or 1
                reach = t["unique_reach"] or 1
                intent = t["intent_signals"] or 1
                output.append({
                    "period_type": ptype,
                    "period_start": data["period_start"],
                    "period_end": data["period_end"],
                    "totals": t,
                    "rates": {
                        "interaction_rate": t["interaction_volume"] / vis,
                        "attention_rate": t["deep_attention_units"] / vis,
                        "intent_rate": t["intent_signals"] / reach,
                        "conversion_rate": t["conversion_events"] / intent,
                        "discovery_ratio": t["active_discovery"] / vis,
                        "growth_rate": t["growth_velocity"] / reach,
                    },
                })
            result = {"masterplan_id": masterplan_id, "grouped": output}
        else:
            totals = {k: sum(getattr(r, k) or 0 for r in records)
                      for k in ["passive_visibility", "active_discovery", "unique_reach",
                                 "interaction_volume", "deep_attention_units", "intent_signals",
                                 "conversion_events", "growth_velocity"]}
            vis = totals["passive_visibility"] or 1
            reach = totals["unique_reach"] or 1
            intent = totals["intent_signals"] or 1
            result = {
                "masterplan_id": masterplan_id,
                "record_count": len(records),
                "totals": totals,
                "rates": {
                    "interaction_rate": totals["interaction_volume"] / vis,
                    "attention_rate": totals["deep_attention_units"] / vis,
                    "intent_rate": totals["intent_signals"] / reach,
                    "conversion_rate": totals["conversion_events"] / intent,
                    "discovery_ratio": totals["active_discovery"] / vis,
                    "growth_rate": totals["growth_velocity"] / reach,
                },
            }
        return {"status": "SUCCESS", "output_patch": {"analytics_masterplan_summary_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Watcher ────────────────────────────────────────────────────────────────────

@register_node("watcher_signals_list_node")
def watcher_signals_list_node(state, context):
    try:
        from uuid import UUID
        from db.models.watcher_signal import WatcherSignal
        db = context.get("db")
        session_id = state.get("session_id")
        signal_type = state.get("signal_type")
        user_id_filter = state.get("user_id_filter")
        limit = state.get("limit", 50)
        offset_val = state.get("offset", 0)

        q = db.query(WatcherSignal)
        if session_id:
            q = q.filter(WatcherSignal.session_id == session_id)
        if user_id_filter:
            q = q.filter(WatcherSignal.user_id == UUID(str(user_id_filter)))
        if signal_type:
            q = q.filter(WatcherSignal.signal_type == signal_type)

        signals = q.order_by(WatcherSignal.signal_timestamp.desc()).offset(offset_val).limit(limit).all()
        data = [
            {
                "id": s.id,
                "signal_type": s.signal_type,
                "session_id": s.session_id,
                "app_name": s.app_name,
                "window_title": s.window_title,
                "activity_type": s.activity_type,
                "signal_timestamp": s.signal_timestamp.isoformat(),
                "received_at": s.received_at.isoformat(),
                "duration_seconds": s.duration_seconds,
                "focus_score": s.focus_score,
                "metadata": s.signal_metadata,
            }
            for s in signals
        ]
        return {"status": "SUCCESS", "output_patch": {"watcher_signals_list_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Genesis ────────────────────────────────────────────────────────────────────

@register_node("genesis_session_create_node")
def genesis_session_create_node(state, context):
    try:
        import uuid
        from db.models import GenesisSessionDB
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session = GenesisSessionDB(
            user_id=user_id,
            synthesis_ready=False,
            summarized_state={
                "vision_summary": None, "time_horizon": None, "mechanism_summary": None,
                "assets_summary": None, "inferred_domains": [], "inferred_phases": [], "confidence": 0.0,
            },
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return {"status": "SUCCESS", "output_patch": {"genesis_session_create_result": {"session_id": session.id}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("genesis_session_get_node")
def genesis_session_get_node(state, context):
    try:
        import uuid
        from db.models import GenesisSessionDB
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session_id = state.get("session_id")
        session = db.query(GenesisSessionDB).filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == user_id,
        ).first()
        if not session:
            return {"status": "FAILURE", "error": "HTTP_404:GenesisSession not found"}
        result = {
            "session_id": session.id,
            "status": session.status,
            "synthesis_ready": session.synthesis_ready,
            "summarized_state": session.summarized_state,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
        return {"status": "SUCCESS", "output_patch": {"genesis_session_get_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("genesis_draft_get_node")
def genesis_draft_get_node(state, context):
    try:
        import uuid
        from db.models import GenesisSessionDB
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session_id = state.get("session_id")
        session = db.query(GenesisSessionDB).filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == user_id,
        ).first()
        if not session:
            return {"status": "FAILURE", "error": "HTTP_404:GenesisSession not found"}
        if not session.draft_json:
            return {"status": "FAILURE", "error": "HTTP_404:No draft available yet - run /genesis/synthesize first"}
        result = {
            "session_id": session.id,
            "draft": session.draft_json,
            "synthesis_ready": session.synthesis_ready,
        }
        return {"status": "SUCCESS", "output_patch": {"genesis_draft_get_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("genesis_synthesize_node")
def genesis_synthesize_node(state, context):
    try:
        import uuid
        from db.models import GenesisSessionDB
        from platform_layer.async_job_service import (
            async_heavy_execution_enabled,
            build_queued_response,
            submit_async_job,
        )
        from domain.genesis_ai import call_genesis_synthesis_llm
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session_id = state.get("session_id")
        session = db.query(GenesisSessionDB).filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == user_id,
        ).first()
        if not session:
            return {"status": "FAILURE", "error": "HTTP_404:GenesisSession not found"}
        if not session.synthesis_ready:
            return {"status": "FAILURE", "error": "HTTP_422:Session is not ready for synthesis yet"}
        if async_heavy_execution_enabled():
            log_id = submit_async_job(
                task_name="genesis.synthesize",
                payload={"session_id": session_id, "user_id": str(user_id)},
                user_id=user_id, source="genesis_router",
            )
            return {"status": "SUCCESS", "output_patch": {"genesis_synthesize_result": {
                "_http_status": 202,
                "_http_response": build_queued_response(log_id, task_name="genesis.synthesize", source="genesis_router"),
            }}}
        current_state = session.summarized_state or {}
        draft = call_genesis_synthesis_llm(current_state, user_id=str(user_id), db=db)
        session.draft_json = draft
        db.commit()
        return {"status": "SUCCESS", "output_patch": {"genesis_synthesize_result": {"draft": draft}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("genesis_audit_node")
def genesis_audit_node(state, context):
    try:
        import uuid
        from db.models import GenesisSessionDB
        from platform_layer.async_job_service import (
            async_heavy_execution_enabled,
            build_queued_response,
            submit_async_job,
        )
        from domain.genesis_ai import validate_draft_integrity
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session_id = state.get("session_id")
        session = db.query(GenesisSessionDB).filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == user_id,
        ).first()
        if not session:
            return {"status": "FAILURE", "error": "HTTP_404:GenesisSession not found"}
        if not session.draft_json:
            return {"status": "FAILURE", "error": "HTTP_422:No draft available - run /genesis/synthesize first"}
        if async_heavy_execution_enabled():
            log_id = submit_async_job(
                task_name="genesis.audit",
                payload={"session_id": session_id, "user_id": str(user_id)},
                user_id=user_id, source="genesis_router",
            )
            return {"status": "SUCCESS", "output_patch": {"genesis_audit_result": {
                "_http_status": 202,
                "_http_response": build_queued_response(log_id, task_name="genesis.audit", source="genesis_router"),
            }}}
        return {"status": "SUCCESS", "output_patch": {"genesis_audit_result": validate_draft_integrity(session.draft_json)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("genesis_lock_node")
def genesis_lock_node(state, context):
    try:
        import uuid
        from core.execution_signal_helper import queue_memory_capture
        from db.models import GenesisSessionDB
        from domain.masterplan_factory import create_masterplan_from_genesis
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session_id = state.get("session_id")
        draft = state.get("draft")
        session = db.query(GenesisSessionDB).filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == user_id,
        ).first()
        if not session:
            return {"status": "FAILURE", "error": "HTTP_404:GenesisSession not found"}
        try:
            masterplan = create_masterplan_from_genesis(
                session_id=session_id, draft=draft, db=db, user_id=str(user_id)
            )
        except Exception as e:
            return {"status": "FAILURE", "error": f"HTTP_400:Failed to create masterplan: {e}"}
        try:
            vision = str(draft.get("vision_statement") or draft.get("vision_summary") or "") if isinstance(draft, dict) else ""
            queue_memory_capture(
                db=db, user_id=str(user_id), agent_namespace="genesis",
                event_type="masterplan_locked",
                content=f"Masterplan locked: {masterplan.version_label} (posture: {masterplan.posture}, session: {session_id}). Vision: {vision[:200]}",
                source="genesis_lock", tags=["genesis", "masterplan", "decision"],
                node_type="decision", force=True,
            )
        except Exception:
            pass
        return {"status": "SUCCESS", "output_patch": {"genesis_lock_result": {
            "masterplan_id": masterplan.id,
            "version": masterplan.version_label,
            "posture": masterplan.posture,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("genesis_activate_node")
def genesis_activate_node(state, context):
    try:
        import uuid
        from datetime import datetime
        from core.execution_signal_helper import queue_memory_capture
        from db.models import MasterPlan
        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        plan_id = state.get("plan_id")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        db.query(MasterPlan).filter(MasterPlan.user_id == user_id).update({"is_active": False})
        plan.is_active = True
        plan.status = "active"
        plan.activated_at = datetime.utcnow()
        db.commit()
        try:
            queue_memory_capture(
                db=db, user_id=str(user_id), agent_namespace="genesis",
                event_type="masterplan_activated",
                content=f"Masterplan activated: {plan.version_label} (id: {plan_id})",
                source="genesis_activate", tags=["genesis", "masterplan", "activation"],
                node_type="decision", force=True,
            )
        except Exception:
            pass
        return {"status": "SUCCESS", "output_patch": {"genesis_activate_result": {"activation_status": "activated"}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Flow ───────────────────────────────────────────────────────────────────────

@register_node("flow_runs_list_node")
def flow_runs_list_node(state, context):
    try:
        from uuid import UUID
        from db.models.flow_run import FlowRun
        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        status_filter = state.get("status")
        workflow_type = state.get("workflow_type")
        limit = state.get("limit", 20)
        query = db.query(FlowRun).filter(
            FlowRun.user_id == user_id,
            FlowRun.flow_name != "flow_runs_list",
        )
        if status_filter:
            query = query.filter(FlowRun.status == status_filter)
        if workflow_type:
            query = query.filter(FlowRun.workflow_type == workflow_type)
        runs = query.order_by(FlowRun.created_at.desc()).limit(limit).all()
        data = {
            "runs": [
                {
                    "id": r.id,
                    "flow_name": r.flow_name,
                    "workflow_type": r.workflow_type,
                    "status": r.status,
                    "trace_id": r.trace_id,
                    "current_node": r.current_node,
                    "waiting_for": r.waiting_for,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                    "error_message": r.error_message,
                }
                for r in runs
            ],
            "count": len(runs),
        }
        return {"status": "SUCCESS", "output_patch": {"flow_runs_list_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("flow_run_get_node")
def flow_run_get_node(state, context):
    try:
        from uuid import UUID
        from db.models.flow_run import FlowRun
        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        run_id = state.get("run_id")
        run = db.query(FlowRun).filter(FlowRun.id == run_id, FlowRun.user_id == user_id).first()
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Flow run not found"}
        result = {
            "id": run.id,
            "flow_name": run.flow_name,
            "workflow_type": run.workflow_type,
            "status": run.status,
            "trace_id": run.trace_id,
            "current_node": run.current_node,
            "waiting_for": run.waiting_for,
            "state": run.state,
            "error_message": run.error_message,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        return {"status": "SUCCESS", "output_patch": {"flow_run_get_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("flow_run_history_node")
def flow_run_history_node(state, context):
    try:
        from uuid import UUID
        from db.models.flow_run import FlowHistory, FlowRun
        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        run_id = state.get("run_id")
        run = db.query(FlowRun).filter(FlowRun.id == run_id, FlowRun.user_id == user_id).first()
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Flow run not found"}
        history = (
            db.query(FlowHistory)
            .filter(FlowHistory.flow_run_id == run_id)
            .order_by(FlowHistory.created_at.asc())
            .all()
        )
        result = {
            "run_id": run_id,
            "trace_id": run.trace_id,
            "flow_name": run.flow_name,
            "workflow_type": run.workflow_type,
            "history": [
                {
                    "id": h.id,
                    "node_name": h.node_name,
                    "status": h.status,
                    "execution_time_ms": h.execution_time_ms,
                    "output_patch": h.output_patch,
                    "error_message": h.error_message,
                    "created_at": h.created_at.isoformat() if h.created_at else None,
                }
                for h in history
            ],
            "node_count": len(history),
        }
        return {"status": "SUCCESS", "output_patch": {"flow_run_history_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("flow_run_resume_node")
def flow_run_resume_node(state, context):
    try:
        from uuid import UUID
        from db.models.flow_run import FlowRun
        from runtime.flow_engine import route_event
        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        run_id = state.get("run_id")
        event_type = state.get("event_type")
        payload = state.get("payload", {})

        run = db.query(FlowRun).filter(FlowRun.id == run_id, FlowRun.user_id == user_id).first()
        if not run:
            return {"status": "FAILURE", "error": "HTTP_404:Flow run not found"}
        if run.status != "waiting":
            return {"status": "FAILURE", "error": f"HTTP_400:Flow run is '{run.status}', not 'waiting'. Cannot resume."}
        if run.waiting_for != event_type:
            return {"status": "FAILURE", "error": f"HTTP_400:Flow run waiting for '{run.waiting_for}', not '{event_type}'"}

        results = route_event(event_type=event_type, payload=payload, db=db, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"flow_run_resume_result": {
            "run_id": run_id, "resumed": True, "results": results,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("flow_registry_get_node")
def flow_registry_get_node(state, context):
    try:
        from runtime.flow_engine import FLOW_REGISTRY, NODE_REGISTRY
        result = {
            "flows": {
                name: {
                    "start": flow["start"],
                    "end": flow.get("end", []),
                    "node_count": len(flow.get("edges", {})) + 1,
                }
                for name, flow in FLOW_REGISTRY.items()
            },
            "nodes": list(NODE_REGISTRY.keys()),
            "flow_count": len(FLOW_REGISTRY),
            "node_count": len(NODE_REGISTRY),
        }
        return {"status": "SUCCESS", "output_patch": {"flow_registry_get_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Memory ─────────────────────────────────────────────────────────────────────

@register_node("memory_node_create_node")
def memory_node_create_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
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


@register_node("memory_node_get_node")
def memory_node_get_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        from utils.uuid_utils import normalize_uuid
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


@register_node("memory_node_update_node")
def memory_node_update_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
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


@register_node("memory_node_history_node")
def memory_node_history_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        limit = state.get("limit", 20)
        dao = MemoryNodeDAO(db)
        history = dao.get_history(node_id=node_id, user_id=user_id, limit=limit)
        return {"status": "SUCCESS", "output_patch": {"memory_node_history_result": {
            "node_id": node_id, "history": history, "count": len(history),
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_node_links_node")
def memory_node_links_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        direction = state.get("direction", "both")
        if direction not in ("in", "out", "both"):
            return {"status": "FAILURE", "error": "HTTP_422:direction must be 'in', 'out', or 'both'"}
        dao = MemoryNodeDAO(db)
        if not dao.get_by_id(node_id, user_id=user_id):
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_links_result": {
            "nodes": dao.get_linked_nodes(node_id, direction=direction, user_id=user_id)
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_nodes_search_tags_node")
def memory_nodes_search_tags_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        db = context.get("db")
        user_id = str(context.get("user_id"))
        tags_str = state.get("tags", "")
        mode = state.get("mode", "AND")
        limit = state.get("limit", 50)
        if mode.upper() not in ("AND", "OR"):
            return {"status": "FAILURE", "error": "HTTP_422:mode must be 'AND' or 'OR'"}
        tag_list = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
        dao = MemoryNodeDAO(db)
        return {"status": "SUCCESS", "output_patch": {"memory_nodes_search_tags_result": {
            "nodes": dao.get_by_tags(tag_list, limit=limit, mode=mode, user_id=user_id)
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_link_create_node")
def memory_link_create_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        db = context.get("db")
        user_id = str(context.get("user_id"))
        dao = MemoryNodeDAO(db)
        source_id = state.get("source_id")
        target_id = state.get("target_id")
        if not dao.get_by_id(source_id, user_id=user_id) and dao._get_model_by_id(source_id) is not None:
            return {"status": "FAILURE", "error": "HTTP_404:Source node not found"}
        if not dao.get_by_id(target_id, user_id=user_id) and dao._get_model_by_id(target_id) is not None:
            return {"status": "FAILURE", "error": "HTTP_404:Target node not found"}
        try:
            result = dao.create_link(source_id, target_id, state.get("link_type", "related"), state.get("weight", 0.5))
        except ValueError as ve:
            return {"status": "FAILURE", "error": f"HTTP_422:Invalid memory link: {ve}"}
        return {"status": "SUCCESS", "output_patch": {"memory_link_create_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_node_traverse_node")
def memory_node_traverse_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
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


@register_node("memory_nodes_expand_node")
def memory_nodes_expand_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
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


@register_node("memory_nodes_search_similar_node")
def memory_nodes_search_similar_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        from memory.embedding_service import generate_query_embedding
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
        return {"status": "SUCCESS", "output_patch": {"memory_nodes_search_similar_result": {
            "query": query, "results": results, "count": len(results),
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_recall_node")
def memory_recall_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        from runtime.memory import MemoryOrchestrator, memory_items_to_dicts
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
        context_obj = orchestrator.get_context(
            user_id=user_id, query=query or "", task_type="analysis",
            db=db, max_tokens=1200, metadata=metadata,
        )
        results = memory_items_to_dicts(context_obj.items)
        return {"status": "SUCCESS", "output_patch": {"memory_recall_result": {
            "query": query, "tags": tags, "results": results, "count": len(results),
            "scoring_version": "v2",
            "formula": {"semantic": 0.40, "graph": 0.15, "recency": 0.15, "success_rate": 0.20, "usage_frequency": 0.10,
                        "note": "adaptive_weight multiplier applied; tag_score adds up to +0.1"},
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_recall_v3_node")
def memory_recall_v3_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        from runtime.memory import MemoryOrchestrator, memory_items_to_dicts
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
        context_obj = orchestrator.get_context(
            user_id=user_id, query=query or "", task_type="analysis",
            db=db, max_tokens=1200, metadata=metadata,
        )
        results = memory_items_to_dicts(context_obj.items)
        formula = {"semantic": 0.40, "graph": 0.15, "recency": 0.15, "success_rate": 0.20, "usage_frequency": 0.10,
                   "note": "adaptive_weight multiplier applied; tag_score adds up to +0.1"}
        if state.get("expand_results") and context_obj.ids:
            dao = MemoryNodeDAO(db)
            expansion = dao.expand(
                node_ids=context_obj.ids[:3], user_id=user_id,
                include_linked=True, include_similar=True, limit_per_node=2,
            )
            result = {
                "query": query, "tags": tags, "results": results,
                "expanded": expansion.get("expanded_nodes", []),
                "expansion_map": expansion.get("expansion_map", {}),
                "total_context_nodes": len(results) + len(expansion.get("expanded_nodes", [])),
                "scoring_version": "v2", "formula": formula,
            }
        else:
            result = {"query": query, "tags": tags, "results": results, "count": len(results),
                      "scoring_version": "v2", "formula": formula}
        return {"status": "SUCCESS", "output_patch": {"memory_recall_v3_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_recall_federated_node")
def memory_recall_federated_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        query = state.get("query")
        tags = state.get("tags")
        if not query and not tags:
            return {"status": "FAILURE", "error": "HTTP_400:Provide at least one of: query, tags"}
        dao = MemoryNodeDAO(db)
        result = dao.recall_federated(
            query=query, tags=tags,
            agent_namespaces=state.get("agent_namespaces"),
            limit=state.get("limit", 5),
            user_id=user_id,
        )
        return {"status": "SUCCESS", "output_patch": {"memory_recall_federated_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_agents_list_node")
def memory_agents_list_node(state, context):
    try:
        from db.models.agent import Agent
        from memory.memory_persistence import MemoryNodeModel
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        agents = db.query(Agent).filter(Agent.is_active.is_(True)).all()
        result_list = []
        for agent in agents:
            node_count = db.query(MemoryNodeModel).filter(
                MemoryNodeModel.source_agent == agent.memory_namespace,
                MemoryNodeModel.user_id == user_id,
            ).count()
            shared_count = db.query(MemoryNodeModel).filter(
                MemoryNodeModel.source_agent == agent.memory_namespace,
                MemoryNodeModel.user_id == user_id,
                MemoryNodeModel.is_shared.is_(True),
            ).count()
            result_list.append({
                "id": agent.id, "name": agent.name, "agent_type": agent.agent_type,
                "description": agent.description, "memory_namespace": agent.memory_namespace,
                "is_active": agent.is_active,
                "memory_stats": {
                    "total_nodes": node_count,
                    "shared_nodes": shared_count,
                    "private_nodes": node_count - shared_count,
                },
            })
        return {"status": "SUCCESS", "output_patch": {"memory_agents_list_result": {
            "agents": result_list, "total": len(result_list),
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_node_share_node")
def memory_node_share_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        node_id = state.get("node_id")
        dao = MemoryNodeDAO(db)
        node = dao.share_memory(node_id=node_id, user_id=user_id)
        if not node:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_share_result": {
            "node_id": node_id, "is_shared": node.is_shared,
            "source_agent": node.source_agent,
            "message": "Memory node is now shared with all agents.",
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_agent_recall_node")
def memory_agent_recall_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        from utils.uuid_utils import normalize_uuid
        db = context.get("db")
        user_id = normalize_uuid(context.get("user_id"))
        namespace = state.get("namespace", "")
        dao = MemoryNodeDAO(db)
        results = dao.recall_from_agent(
            agent_namespace=namespace,
            query=state.get("query"),
            limit=state.get("limit", 5),
            user_id=user_id,
            include_private=False,
        )
        return {"status": "SUCCESS", "output_patch": {"memory_agent_recall_result": {
            "agent_namespace": namespace, "query": state.get("query"),
            "results": results, "count": len(results),
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_node_feedback_node")
def memory_node_feedback_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        db = context.get("db")
        user_id = str(context.get("user_id"))
        node_id = state.get("node_id")
        outcome = state.get("outcome")
        dao = MemoryNodeDAO(db)
        node = dao.record_feedback(node_id=node_id, outcome=outcome, user_id=user_id)
        if not node:
            return {"status": "FAILURE", "error": "HTTP_404:Memory node not found"}
        return {"status": "SUCCESS", "output_patch": {"memory_node_feedback_result": {
            "node_id": node_id, "outcome": outcome,
            "success_count": node.success_count,
            "failure_count": node.failure_count,
            "usage_count": node.usage_count,
            "adaptive_weight": node.weight,
            "success_rate": dao.get_success_rate(node),
            "message": {
                "success": "Weight boosted - memory reinforced",
                "failure": "Weight reduced - memory suppressed",
                "neutral": "Usage recorded - no weight change",
            }[outcome],
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_node_performance_node")
def memory_node_performance_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
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
        return {"status": "SUCCESS", "output_patch": {"memory_node_performance_result": {
            "node_id": node_id,
            "content_preview": (node.content or "")[:100],
            "node_type": node.node_type,
            "performance": {
                "success_count": node.success_count or 0,
                "failure_count": node.failure_count or 0,
                "usage_count": node.usage_count or 0,
                "success_rate": round(success_rate, 3),
                "adaptive_weight": round(node.weight or 1.0, 3),
                "last_outcome": node.last_outcome,
                "last_used_at": node.last_used_at.isoformat() if node.last_used_at else None,
                "total_feedback_signals": total_feedback,
                "graph_connectivity": round(graph_score, 3),
                "usage_frequency_score": round(usage_freq, 3),
            },
            "resonance_v2_preview": {
                "note": "Scores shown for this node in isolation. Actual resonance depends on query context.",
                "success_rate_component": round(success_rate * 0.20, 4),
                "usage_freq_component": round(usage_freq * 0.10, 4),
                "graph_component": round(graph_score * 0.15, 4),
                "adaptive_weight": round(node.weight or 1.0, 3),
            },
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_suggest_node")
def memory_suggest_node(state, context):
    try:
        from db.dao.memory_node_dao import MemoryNodeDAO
        db = context.get("db")
        user_id = str(context.get("user_id"))
        query = state.get("query")
        tags = state.get("tags")
        if not query and not tags:
            return {"status": "FAILURE", "error": "HTTP_400:Provide at least one of: query, tags"}
        dao = MemoryNodeDAO(db)
        result = dao.suggest(
            query=query, tags=tags, context=state.get("context"),
            user_id=user_id, limit=state.get("limit", 3),
        )
        return {"status": "SUCCESS", "output_patch": {"memory_suggest_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("memory_nodus_execute_node")
def memory_nodus_execute_node(state, context):
    try:
        from platform_layer.async_job_service import (
            async_heavy_execution_enabled,
            build_queued_response,
            submit_async_job,
        )
        from core.execution_envelope import success
        from runtime.nodus_execution_service import execute_nodus_task_payload
        from runtime.nodus_security import NodusSecurityError
        from utils.trace_context import ensure_trace_id
        from utils.user_ids import require_user_id
        db = context.get("db")
        user_id = str(require_user_id(context.get("user_id")))
        if async_heavy_execution_enabled():
            log_id = submit_async_job(
                task_name="memory.nodus.execute",
                payload={
                    "task_name": state.get("task_name"),
                    "task_code": state.get("task_code"),
                    "user_id": user_id,
                    "session_tags": state.get("session_tags", []),
                    "allowed_operations": state.get("allowed_operations"),
                    "execution_id": state.get("execution_id"),
                    "capability_token": state.get("capability_token"),
                },
                user_id=user_id, source="memory_router",
            )
            return {"status": "SUCCESS", "output_patch": {"memory_nodus_execute_result": {
                "_http_status": 202,
                "_http_response": build_queued_response(log_id, task_name="memory.nodus.execute", source="memory_router"),
            }}}
        try:
            result = execute_nodus_task_payload(
                task_name=state.get("task_name"),
                task_code=state.get("task_code"),
                db=db, user_id=user_id,
                session_tags=state.get("session_tags", []),
                allowed_operations=state.get("allowed_operations"),
                execution_id=state.get("execution_id"),
                capability_token=state.get("capability_token"),
                logger=logger,
            )
            if isinstance(result, dict) and {"status", "result", "events", "next_action", "trace_id"}.issubset(result.keys()):
                return {"status": "SUCCESS", "output_patch": {"memory_nodus_execute_result": result}}
            return {"status": "SUCCESS", "output_patch": {"memory_nodus_execute_result": success(result, [], ensure_trace_id())}}
        except NodusSecurityError as exc:
            return {"status": "FAILURE", "error": f"HTTP_403:nodus_security_violation: {exc}"}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Automation ─────────────────────────────────────────────────────────────────

@register_node("automation_logs_list_node")
def automation_logs_list_node(state, context):
    try:
        from uuid import UUID
        from db.models.automation_log import AutomationLog
        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        status = state.get("status")
        source_filter = state.get("source_filter")
        limit = state.get("limit", 50)
        query = db.query(AutomationLog).filter(AutomationLog.user_id == user_id)
        if status:
            query = query.filter(AutomationLog.status == status)
        if source_filter:
            query = query.filter(AutomationLog.source == source_filter)
        logs = query.order_by(AutomationLog.created_at.desc()).limit(limit).all()
        def _s(log):
            return {
                "id": log.id, "source": log.source, "task_name": log.task_name,
                "payload": log.payload, "status": log.status,
                "attempt_count": log.attempt_count, "max_attempts": log.max_attempts,
                "error_message": log.error_message, "result": log.result,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "scheduled_for": log.scheduled_for.isoformat() if log.scheduled_for else None,
            }
        return {"status": "SUCCESS", "output_patch": {"automation_logs_list_result": {
            "logs": [_s(log) for log in logs],
            "count": len(logs),
            "filters": {"status": status, "source": source_filter},
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("automation_log_get_node")
def automation_log_get_node(state, context):
    try:
        from uuid import UUID
        from db.models.automation_log import AutomationLog
        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        log_id = state.get("log_id")
        log = db.query(AutomationLog).filter(
            AutomationLog.id == log_id,
            AutomationLog.user_id == user_id,
        ).first()
        if not log:
            return {"status": "FAILURE", "error": "HTTP_404:Automation log not found"}
        def _s(log):
            return {
                "id": log.id, "source": log.source, "task_name": log.task_name,
                "payload": log.payload, "status": log.status,
                "attempt_count": log.attempt_count, "max_attempts": log.max_attempts,
                "error_message": log.error_message, "result": log.result,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "scheduled_for": log.scheduled_for.isoformat() if log.scheduled_for else None,
            }
        return {"status": "SUCCESS", "output_patch": {"automation_log_get_result": _s(log)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("automation_log_replay_node")
def automation_log_replay_node(state, context):
    try:
        from uuid import UUID
        from db.models.automation_log import AutomationLog
        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        log_id = state.get("log_id")
        log = db.query(AutomationLog).filter(
            AutomationLog.id == log_id,
            AutomationLog.user_id == user_id,
        ).first()
        if not log:
            return {"status": "FAILURE", "error": "HTTP_404:Automation log not found"}
        if log.status not in ("failed", "retrying"):
            return {"status": "FAILURE", "error": f"HTTP_400:Cannot replay log with status '{log.status}'. Only failed or retrying logs can be replayed."}
        payload = log.payload or {}
        if isinstance(payload, dict) and payload.get("execution_token"):
            from agents.capability_service import validate_token
            validation = validate_token(
                token=payload.get("execution_token"),
                run_id=str(payload.get("run_id", "")),
                user_id=user_id,
            )
            if not validation["ok"]:
                return {"status": "FAILURE", "error": f"HTTP_403:Execution token invalid for replay: {validation['error']}"}
        from platform_layer.scheduler_service import replay_task
        result = replay_task(log_id)
        if not result:
            return {"status": "FAILURE", "error": "HTTP_500:Replay failed - task function not registered. Check task registry."}
        return {"status": "SUCCESS", "output_patch": {"automation_log_replay_result": {
            "log_id": log_id,
            "status": "replay_scheduled",
            "message": "Task replay has been scheduled. Check GET /automation/logs/{id} for status updates.",
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("automation_scheduler_status_node")
def automation_scheduler_status_node(state, context):
    try:
        from platform_layer.scheduler_service import get_scheduler
        try:
            scheduler = get_scheduler()
            jobs = scheduler.get_jobs()
            running = scheduler.running
        except RuntimeError as exc:
            return {"status": "FAILURE", "error": f"HTTP_503:{exc}"}
        return {"status": "SUCCESS", "output_patch": {"automation_scheduler_status_result": {
            "running": running,
            "job_count": len(jobs),
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
                for job in jobs
            ],
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("automation_task_trigger_node")
def automation_task_trigger_node(state, context):
    try:
        from domain.task_services import get_task_by_id, queue_task_automation
        db = context.get("db")
        user_id = context.get("user_id")
        task_id = state.get("task_id")
        automation_type = state.get("automation_type")
        automation_config = state.get("automation_config")
        task = get_task_by_id(db, task_id, user_id)
        if not task:
            return {"status": "FAILURE", "error": "HTTP_404:Task not found"}
        if automation_type is not None:
            task.automation_type = automation_type
        if automation_config is not None:
            task.automation_config = automation_config
        db.commit()
        db.refresh(task)
        if not task.automation_type:
            return {"status": "FAILURE", "error": "HTTP_422:task_automation_not_configured"}
        dispatch = queue_task_automation(db=db, task=task, user_id=user_id, reason="manual_trigger")
        if not dispatch:
            return {"status": "FAILURE", "error": "HTTP_500:task_automation_dispatch_failed"}
        return {"status": "SUCCESS", "output_patch": {"automation_task_trigger_result": dispatch}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Freelance ───────────────────────────────────────────────────────────────────

@register_node("freelance_order_create_node")
def freelance_order_create_node(state, context):
    try:
        from schemas.freelance import FreelanceOrderCreate, FreelanceOrderResponse
        from domain import freelance_service
        db = context.get("db")
        user_id = str(context.get("user_id"))
        order = FreelanceOrderCreate(**state.get("order", {}))
        created = freelance_service.create_order(db, order, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"freelance_order_create_result": {
            "data": FreelanceOrderResponse.model_validate(created).model_dump(mode="json"),
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to create order: {e}"}


@register_node("freelance_order_deliver_node")
def freelance_order_deliver_node(state, context):
    try:
        import uuid as _uuid
        from db.models.freelance import FreelanceOrder
        from schemas.freelance import FreelanceOrderResponse
        from domain import freelance_service
        db = context.get("db")
        user_id = str(context.get("user_id"))
        order_id = state.get("order_id")
        ai_output = state.get("ai_output")
        order = db.query(FreelanceOrder).filter(
            FreelanceOrder.id == order_id,
            FreelanceOrder.user_id == _uuid.UUID(user_id),
        ).first()
        if not order:
            return {"status": "FAILURE", "error": "HTTP_404:Order not found"}
        delivered = freelance_service.deliver_order(db, order_id, ai_output, generated_by_ai=False)
        return {"status": "SUCCESS", "output_patch": {"freelance_order_deliver_result": {
            "data": FreelanceOrderResponse.model_validate(delivered).model_dump(mode="json"),
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to deliver order: {e}"}


@register_node("freelance_delivery_update_node")
def freelance_delivery_update_node(state, context):
    try:
        from schemas.freelance import FreelanceOrderResponse
        from domain import freelance_service
        db = context.get("db")
        user_id = str(context.get("user_id"))
        try:
            updated = freelance_service.update_delivery_config(
                db=db, order_id=state.get("order_id"), user_id=user_id,
                delivery_type=state.get("delivery_type"), delivery_config=state.get("delivery_config"),
            )
        except ValueError as e:
            return {"status": "FAILURE", "error": f"HTTP_404:{e}"}
        return {"status": "SUCCESS", "output_patch": {"freelance_delivery_update_result":
            FreelanceOrderResponse.model_validate(updated).model_dump(mode="json")
        }}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to update delivery configuration: {e}"}


@register_node("freelance_feedback_collect_node")
def freelance_feedback_collect_node(state, context):
    try:
        from schemas.freelance import FeedbackCreate, FeedbackResponse
        from domain import freelance_service
        db = context.get("db")
        user_id = str(context.get("user_id"))
        feedback = FeedbackCreate(**state.get("feedback", {}))
        try:
            collected = freelance_service.collect_feedback(db, feedback, user_id=user_id)
        except ValueError as e:
            return {"status": "FAILURE", "error": f"HTTP_404:{e}"}
        return {"status": "SUCCESS", "output_patch": {"freelance_feedback_collect_result": {
            "data": FeedbackResponse.model_validate(collected).model_dump(mode="json"),
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to collect feedback: {e}"}


@register_node("freelance_orders_list_node")
def freelance_orders_list_node(state, context):
    try:
        from schemas.freelance import FreelanceOrderResponse
        from domain import freelance_service
        db = context.get("db")
        user_id = str(context.get("user_id"))
        orders = freelance_service.get_all_orders(db, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"freelance_orders_list_result": [
            FreelanceOrderResponse.model_validate(o).model_dump(mode="json") for o in orders
        ]}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("freelance_feedback_list_node")
def freelance_feedback_list_node(state, context):
    try:
        from schemas.freelance import FeedbackResponse
        from domain import freelance_service
        db = context.get("db")
        user_id = str(context.get("user_id"))
        items = freelance_service.get_all_feedback(db, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"freelance_feedback_list_result": [
            FeedbackResponse.model_validate(i).model_dump(mode="json") for i in items
        ]}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("freelance_metrics_latest_node")
def freelance_metrics_latest_node(state, context):
    try:
        from schemas.freelance import RevenueMetricsResponse
        from domain import freelance_service
        db = context.get("db")
        metric = freelance_service.get_latest_metrics(db)
        if not metric:
            return {"status": "FAILURE", "error": "HTTP_404:No revenue metrics found"}
        return {"status": "SUCCESS", "output_patch": {"freelance_metrics_latest_result":
            RevenueMetricsResponse.model_validate(metric).model_dump(mode="json")
        }}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("freelance_metrics_update_node")
def freelance_metrics_update_node(state, context):
    try:
        from schemas.freelance import RevenueMetricsResponse
        from domain import freelance_service
        db = context.get("db")
        user_id = str(context.get("user_id"))
        metric = freelance_service.update_revenue_metrics(db, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"freelance_metrics_update_result":
            RevenueMetricsResponse.model_validate(metric).model_dump(mode="json")
        }}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Metrics update failed: {e}"}


@register_node("freelance_delivery_generate_node")
def freelance_delivery_generate_node(state, context):
    try:
        import uuid as _uuid
        from db.models.freelance import FreelanceOrder
        from domain import freelance_service
        db = context.get("db")
        user_id = str(context.get("user_id"))
        order_id = state.get("order_id")
        order = db.query(FreelanceOrder).filter(
            FreelanceOrder.id == order_id,
            FreelanceOrder.user_id == _uuid.UUID(user_id),
        ).first()
        if not order:
            return {"status": "FAILURE", "error": "HTTP_404:Order not found"}
        try:
            dispatch = freelance_service.queue_delivery_generation(db, order_id=order_id, user_id=user_id)
        except (LookupError, ValueError) as e:
            return {"status": "FAILURE", "error": f"HTTP_404:{e}"}
        return {"status": "SUCCESS", "output_patch": {"freelance_delivery_generate_result": dispatch}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to queue freelance delivery generation: {e}"}


# ── Research ────────────────────────────────────────────────────────────────────

@register_node("research_create_node")
def research_create_node(state, context):
    try:
        from schemas.research_results_schema import ResearchResultCreate
        from domain import research_results_service
        db = context.get("db")
        user_id = str(context.get("user_id"))
        result_obj = ResearchResultCreate(**state.get("result", {}))
        created = research_results_service.create_research_result(db, result_obj, user_id=user_id)
        def _payload(r):
            d = getattr(r, "data", None)
            return {
                "id": r.id, "query": r.query, "summary": r.summary, "source": r.source, "data": d,
                "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
                "search_score": d.get("search_score") if isinstance(d, dict) else None,
            }
        return {"status": "SUCCESS", "output_patch": {"research_create_result": {"data": _payload(created)}}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to create research result: {e}"}


@register_node("research_list_node")
def research_list_node(state, context):
    try:
        from domain import research_results_service
        db = context.get("db")
        user_id = str(context.get("user_id"))
        items = research_results_service.get_all_research_results(db, user_id=user_id)
        def _payload(r):
            d = getattr(r, "data", None)
            return {
                "id": r.id, "query": r.query, "summary": r.summary, "source": r.source, "data": d,
                "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
                "search_score": d.get("search_score") if isinstance(d, dict) else None,
            }
        return {"status": "SUCCESS", "output_patch": {"research_list_result": [_payload(i) for i in items]}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Failed to load research results: {e}"}


@register_node("research_query_node")
def research_query_node(state, context):
    try:
        import time as _time
        from db.dao.memory_node_dao import MemoryNodeDAO
        from runtime.memory import MemoryOrchestrator
        from schemas.research_results_schema import ResearchResultCreate
        from domain import research_results_service
        from domain.search_service import unified_query
        db = context.get("db")
        user_id = str(context.get("user_id"))
        query_str = state.get("query", "")
        summary_hint = state.get("summary", "")
        start = _time.perf_counter()
        memory_context = None
        try:
            orchestrator = MemoryOrchestrator(MemoryNodeDAO)
            memory_context = orchestrator.get_context(
                user_id=user_id, query=query_str, task_type="analysis", db=db,
                max_tokens=400, metadata={"tags": ["research", "insight"], "node_type": "insight", "limit": 3},
            )
        except Exception:
            memory_context = None
        unified = unified_query(query_str, db=db, user_id=user_id)
        summary = unified.get("summary") or summary_hint
        source = unified.get("source")
        raw_excerpt = unified.get("raw_excerpt")
        search_score = unified.get("search_score") or 0.0
        data: dict = {}
        if memory_context and memory_context.items:
            data = {"memory_context_ids": memory_context.ids, "memory_context": memory_context.formatted}
        data.update({
            "search_score": search_score, "raw_excerpt": raw_excerpt, "source": source,
            "memory_context_count": len(memory_context.items) if memory_context else 0,
        })
        created = research_results_service.create_research_result(
            db, ResearchResultCreate(query=query_str, summary=summary),
            user_id=user_id, data=data, source=source or "research_query",
        )
        duration_ms = (_time.perf_counter() - start) * 1000
        d = getattr(created, "data", None)
        payload = {
            "id": created.id, "query": created.query, "summary": created.summary,
            "source": created.source, "data": d,
            "created_at": created.created_at.isoformat() if getattr(created, "created_at", None) else None,
            "search_score": d.get("search_score") if isinstance(d, dict) else None,
            "_execution_meta": {
                "research_id": str(created.id),
                "duration_ms": round(duration_ms, 2),
                "search_score": search_score,
            },
        }
        return {"status": "SUCCESS", "output_patch": {"research_query_result": {"data": payload}}}
    except Exception as e:
        return {"status": "FAILURE", "error": f"HTTP_500:Research query failed: {e}"}


@register_node("search_history_list_node")
def search_history_list_node(state, context):
    try:
        from domain.search_service import get_search_history
        db = context.get("db")
        user_id = str(context.get("user_id"))
        limit = state.get("limit", 25)
        search_type = state.get("search_type")
        items = get_search_history(db, user_id, limit=limit, search_type=search_type)
        def _h(item):
            p = dict(item.result or {})
            return {
                "id": item.id, "query": item.query, "result": p,
                "search_type": p.get("search_type"),
                "created_at": item.created_at.isoformat() if getattr(item, "created_at", None) else None,
            }
        return {"status": "SUCCESS", "output_patch": {"search_history_list_result": {
            "count": len(items), "items": [_h(i) for i in items],
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("search_history_get_node")
def search_history_get_node(state, context):
    try:
        from domain.search_service import get_search_history_item
        db = context.get("db")
        user_id = str(context.get("user_id"))
        history_id = state.get("history_id")
        item = get_search_history_item(db, user_id, history_id)
        if not item:
            return {"status": "FAILURE", "error": "HTTP_404:Search history item not found"}
        p = dict(item.result or {})
        return {"status": "SUCCESS", "output_patch": {"search_history_get_result": {
            "id": item.id, "query": item.query, "result": p,
            "search_type": p.get("search_type"),
            "created_at": item.created_at.isoformat() if getattr(item, "created_at", None) else None,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("search_history_delete_node")
def search_history_delete_node(state, context):
    try:
        from domain.search_service import delete_search_history_item
        db = context.get("db")
        user_id = str(context.get("user_id"))
        history_id = state.get("history_id")
        deleted = delete_search_history_item(db, user_id, history_id)
        if not deleted:
            return {"status": "FAILURE", "error": "HTTP_404:Search history item not found"}
        return {"status": "SUCCESS", "output_patch": {"search_history_delete_result": {
            "status": "deleted", "id": history_id,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Masterplan ──────────────────────────────────────────────────────────────────

@register_node("masterplan_lock_from_genesis_node")
def masterplan_lock_from_genesis_node(state, context):
    try:
        from domain.masterplan_factory import create_masterplan_from_genesis
        from domain.masterplan_execution_service import sync_masterplan_tasks
        from analytics.posture import posture_description
        db = context.get("db")
        user_id = str(context.get("user_id"))
        session_id = state.get("session_id")
        draft = state.get("draft", {})
        if not session_id:
            return {"status": "FAILURE", "error": "HTTP_400:session_id is required"}
        try:
            masterplan = create_masterplan_from_genesis(session_id=session_id, draft=draft, db=db, user_id=user_id)
        except ValueError as e:
            return {"status": "FAILURE", "error": f"HTTP_422:Masterplan validation failed: {e}"}
        except Exception as e:
            return {"status": "FAILURE", "error": f"HTTP_400:Failed to create masterplan: {e}"}
        task_sync = sync_masterplan_tasks(db=db, masterplan=masterplan, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"masterplan_lock_from_genesis_result": {
            "masterplan_id": masterplan.id,
            "version": masterplan.version_label,
            "posture_description": posture_description(masterplan.posture),
            "posture": masterplan.posture,
            "status": masterplan.status,
            "task_sync": task_sync,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("masterplan_lock_node")
def masterplan_lock_node(state, context):
    try:
        from datetime import datetime
        from db.models import MasterPlan
        from domain.masterplan_execution_service import sync_masterplan_tasks
        db = context.get("db")
        user_id = str(context.get("user_id"))
        plan_id = state.get("plan_id")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        if plan.status == "locked":
            return {"status": "FAILURE", "error": "HTTP_400:Plan is already locked"}
        plan.status = "locked"
        plan.locked_at = datetime.utcnow()
        db.commit()
        task_sync = sync_masterplan_tasks(db=db, masterplan=plan, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"masterplan_lock_result": {
            "plan_id": plan.id, "status": plan.status, "task_sync": task_sync,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("masterplan_list_node")
def masterplan_list_node(state, context):
    try:
        from db.models import MasterPlan
        db = context.get("db")
        user_id = str(context.get("user_id"))
        plans = db.query(MasterPlan).filter(MasterPlan.user_id == user_id).order_by(MasterPlan.id.desc()).all()
        return {"status": "SUCCESS", "output_patch": {"masterplan_list_result": {
            "plans": [
                {
                    "id": p.id, "version_label": p.version_label, "posture": p.posture,
                    "status": p.status, "is_active": p.is_active,
                    "created_at": p.created_at, "locked_at": p.locked_at, "activated_at": p.activated_at,
                }
                for p in plans
            ]
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("masterplan_get_node")
def masterplan_get_node(state, context):
    try:
        from db.models import MasterPlan
        from domain.masterplan_execution_service import get_masterplan_execution_status
        db = context.get("db")
        user_id = str(context.get("user_id"))
        plan_id = state.get("plan_id")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        execution_status = get_masterplan_execution_status(db=db, masterplan_id=plan.id, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"masterplan_get_result": {
            "id": plan.id, "version_label": plan.version_label, "posture": plan.posture,
            "status": plan.status, "is_active": plan.is_active, "structure_json": plan.structure_json,
            "created_at": plan.created_at, "locked_at": plan.locked_at, "activated_at": plan.activated_at,
            "linked_genesis_session_id": plan.linked_genesis_session_id,
            "execution_status": execution_status,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("masterplan_anchor_node")
def masterplan_anchor_node(state, context):
    try:
        from datetime import datetime
        from db.models import MasterPlan
        db = context.get("db")
        user_id = str(context.get("user_id"))
        plan_id = state.get("plan_id")
        anchor_date = state.get("anchor_date")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        if anchor_date is not None:
            try:
                plan.anchor_date = datetime.fromisoformat(anchor_date)
            except ValueError:
                return {"status": "FAILURE", "error": "HTTP_422:anchor_date must be ISO format"}
        if state.get("goal_value") is not None:
            plan.goal_value = state["goal_value"]
        if state.get("goal_unit") is not None:
            plan.goal_unit = state["goal_unit"]
        if state.get("goal_description") is not None:
            plan.goal_description = state["goal_description"]
        db.commit()
        return {"status": "SUCCESS", "output_patch": {"masterplan_anchor_result": {
            "plan_id": plan.id,
            "anchor_date": plan.anchor_date.isoformat() if plan.anchor_date else None,
            "goal_value": plan.goal_value,
            "goal_unit": plan.goal_unit,
            "goal_description": plan.goal_description,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("masterplan_projection_node")
def masterplan_projection_node(state, context):
    try:
        from db.models import MasterPlan
        from analytics.eta_service import calculate_eta
        db = context.get("db")
        user_id = str(context.get("user_id"))
        plan_id = state.get("plan_id")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        try:
            result = calculate_eta(db=db, masterplan_id=plan_id, user_id=user_id)
        except Exception as exc:
            return {"status": "FAILURE", "error": f"HTTP_500:eta_calculation_failed: {exc}"}
        return {"status": "SUCCESS", "output_patch": {"masterplan_projection_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("masterplan_activate_node")
def masterplan_activate_node(state, context):
    try:
        from datetime import datetime
        from db.models import MasterPlan
        from domain.masterplan_execution_service import get_masterplan_execution_status, sync_masterplan_tasks
        db = context.get("db")
        user_id = str(context.get("user_id"))
        plan_id = state.get("plan_id")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        db.query(MasterPlan).filter(MasterPlan.user_id == user_id).update({"is_active": False})
        plan.is_active = True
        plan.status = "active"
        plan.activated_at = datetime.utcnow()
        db.commit()
        task_sync = sync_masterplan_tasks(db=db, masterplan=plan, user_id=user_id)
        execution_status = get_masterplan_execution_status(db=db, masterplan_id=plan.id, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"masterplan_activate_result": {
            "status": "activated", "plan_id": plan.id,
            "task_sync": task_sync, "execution_status": execution_status,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Observability ───────────────────────────────────────────────────────────────

@register_node("observability_scheduler_status_node")
def observability_scheduler_status_node(state, context):
    try:
        import platform_layer.scheduler_service as _sched_svc
        import domain.task_services as _task_svc
        from db.models.background_task_lease import BackgroundTaskLease
        db = context.get("db")
        try:
            sched = _sched_svc.get_scheduler()
            scheduler_running = sched.running
        except RuntimeError:
            scheduler_running = False
        lease_row = db.query(BackgroundTaskLease).filter(
            BackgroundTaskLease.name == _task_svc._BACKGROUND_LEASE_NAME
        ).first()
        lease = None
        if lease_row:
            lease = {
                "owner_id": lease_row.owner_id,
                "acquired_at": lease_row.acquired_at.isoformat() if lease_row.acquired_at else None,
                "heartbeat_at": lease_row.heartbeat_at.isoformat() if lease_row.heartbeat_at else None,
                "expires_at": lease_row.expires_at.isoformat() if lease_row.expires_at else None,
            }
        return {"status": "SUCCESS", "output_patch": {"observability_scheduler_status_result": {
            "scheduler_running": scheduler_running,
            "is_leader": _task_svc.is_background_leader(),
            "lease": lease,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("observability_requests_node")
def observability_requests_node(state, context):
    try:
        import uuid as _uuid
        from datetime import datetime, timedelta
        from sqlalchemy import func
        from db.models.request_metric import RequestMetric
        db = context.get("db")
        user_id = _uuid.UUID(str(context.get("user_id")))
        limit = state.get("limit", 50)
        error_limit = state.get("error_limit", 25)
        window_hours = state.get("window_hours", 24)
        window_start = datetime.utcnow() - timedelta(hours=window_hours)
        base = db.query(RequestMetric).filter(RequestMetric.user_id == user_id)
        total = base.count()
        window_total = base.filter(RequestMetric.created_at >= window_start).count()
        error_total = base.filter(RequestMetric.status_code >= 500).count()
        window_error_total = base.filter(
            RequestMetric.created_at >= window_start, RequestMetric.status_code >= 500
        ).count()
        avg_latency = db.query(func.avg(RequestMetric.duration_ms)).filter(
            RequestMetric.user_id == user_id
        ).scalar()
        recent = base.order_by(RequestMetric.created_at.desc()).limit(limit).all()
        recent_errors = base.filter(RequestMetric.status_code >= 500).order_by(
            RequestMetric.created_at.desc()
        ).limit(error_limit).all()
        def _s(row):
            return {
                "request_id": row.request_id, "trace_id": row.trace_id,
                "method": row.method, "path": row.path,
                "status_code": row.status_code, "duration_ms": row.duration_ms,
                "created_at": row.created_at,
            }
        return {"status": "SUCCESS", "output_patch": {"observability_requests_result": {
            "summary": {
                "total_requests": total, "window_hours": window_hours,
                "window_requests": window_total, "total_errors": error_total,
                "window_errors": window_error_total, "avg_latency_ms": round(avg_latency or 0.0, 2),
            },
            "recent": [_s(r) for r in recent],
            "recent_errors": [_s(r) for r in recent_errors],
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("observability_dashboard_node")
def observability_dashboard_node(state, context):
    try:
        import uuid as _uuid
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func
        from db.models.flow_run import FlowRun
        from db.models.request_metric import RequestMetric
        from db.models.system_event import SystemEvent
        db = context.get("db")
        user_id = _uuid.UUID(str(context.get("user_id")))
        window_hours = state.get("window_hours", 24)
        event_limit = state.get("event_limit", 60)
        request_window_start = datetime.utcnow() - timedelta(hours=window_hours)
        event_window_start = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        req_q = db.query(RequestMetric).filter(RequestMetric.user_id == user_id)
        avg_latency = db.query(func.avg(RequestMetric.duration_ms)).filter(
            RequestMetric.user_id == user_id, RequestMetric.created_at >= request_window_start
        ).scalar()
        window_requests = req_q.filter(RequestMetric.created_at >= request_window_start).count()
        window_errors = req_q.filter(
            RequestMetric.created_at >= request_window_start, RequestMetric.status_code >= 500
        ).count()
        system_events = db.query(SystemEvent).filter(
            SystemEvent.user_id == user_id, SystemEvent.timestamp >= event_window_start
        ).order_by(SystemEvent.timestamp.desc()).limit(event_limit).all()
        flow_rows = db.query(FlowRun).filter(
            FlowRun.user_id == user_id, FlowRun.created_at >= event_window_start
        ).order_by(FlowRun.created_at.desc()).limit(100).all()
        return {"status": "SUCCESS", "output_patch": {"observability_dashboard_result": {
            "summary": {
                "window_hours": window_hours,
                "avg_latency_ms": round(avg_latency or 0.0, 2),
                "window_requests": window_requests,
                "window_errors": window_errors,
                "error_rate_pct": round((window_errors / window_requests) * 100, 2) if window_requests else 0.0,
                "active_flows": sum(1 for r in flow_rows if r.status in {"running", "waiting"}),
                "system_event_total": len(system_events),
            }
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("observability_rippletrace_node")
def observability_rippletrace_node(state, context):
    try:
        import uuid as _uuid
        from db.models.system_event import SystemEvent
        from domain.rippletrace_service import (
            build_trace_graph, calculate_ripple_span,
            detect_root_event, detect_terminal_events, generate_trace_insights,
        )
        db = context.get("db")
        user_id = _uuid.UUID(str(context.get("user_id")))
        trace_id = state.get("trace_id")
        event_count = db.query(SystemEvent).filter(
            SystemEvent.trace_id == trace_id, SystemEvent.user_id == user_id
        ).count()
        if event_count == 0:
            result = {
                "trace_id": trace_id, "nodes": [], "edges": [], "root_event": None,
                "terminal_events": [],
                "ripple_span": {"node_count": 0, "edge_count": 0, "depth": 0, "terminal_count": 0},
            }
        else:
            graph = build_trace_graph(db, trace_id)
            result = {
                "trace_id": trace_id, "nodes": graph["nodes"], "edges": graph["edges"],
                "root_event": detect_root_event(db, trace_id),
                "terminal_events": detect_terminal_events(db, trace_id),
                "ripple_span": calculate_ripple_span(db, trace_id),
                "insights": generate_trace_insights(db, trace_id),
            }
        return {"status": "SUCCESS", "output_patch": {"observability_rippletrace_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Dashboard ──────────────────────────────────────────────────────────────────

@register_node("dashboard_overview_node")
def dashboard_overview_node(state, context):
    try:
        import uuid
        from datetime import datetime
        from db.models.author_model import AuthorDB
        from db.models import PingDB

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))

        authors = (
            db.query(AuthorDB)
            .filter(AuthorDB.user_id == user_id)
            .order_by(AuthorDB.joined_at.desc())
            .limit(10)
            .all()
        )
        author_list = [
            {
                "id": a.id,
                "name": a.name,
                "platform": a.platform,
                "last_seen": a.last_seen.isoformat() if a.last_seen else None,
                "notes": a.notes,
            }
            for a in authors
        ]

        ripples = (
            db.query(PingDB)
            .filter(PingDB.user_id == user_id)
            .order_by(PingDB.date_detected.desc())
            .limit(10)
            .all()
        )
        ripple_list = [
            {
                "ping_type": r.ping_type,
                "source_platform": r.source_platform,
                "summary": r.connection_summary,
                "date_detected": r.date_detected.isoformat() if r.date_detected else None,
            }
            for r in ripples
        ]

        result = {
            "status": "ok",
            "overview": {
                "system_timestamp": datetime.utcnow().isoformat(),
                "author_count": len(author_list),
                "recent_authors": author_list,
                "recent_ripples": ripple_list,
            },
        }
        return {"status": "SUCCESS", "output_patch": {"dashboard_overview_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Autonomy ───────────────────────────────────────────────────────────────────

@register_node("autonomy_decisions_list_node")
def autonomy_decisions_list_node(state, context):
    try:
        from agents.autonomous_controller import list_recent_decisions

        db = context.get("db")
        user_id = context.get("user_id")
        limit = int(state.get("limit") or 50)
        decisions = list_recent_decisions(db, user_id=user_id, limit=limit)
        return {
            "status": "SUCCESS",
            "output_patch": {"autonomy_decisions_list_result": decisions},
        }
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Watcher autonomy gate ──────────────────────────────────────────────────────
# Three-node pipeline: evaluate → record → dispatch (defer | ignore | execute).
# The execute branch re-uses the existing watcher_ingest_* nodes via conditional
# edges; a wrap node normalises the result key to watcher_evaluate_trigger_result.

@register_node("watcher_evaluate_trigger_node")
def watcher_evaluate_trigger_node(state, context):
    """Call evaluate_live_trigger and store the evaluation dict in state."""
    try:
        from agents.autonomous_controller import evaluate_live_trigger

        db = context.get("db")
        user_id = state.get("user_id")
        trigger_context = {
            "goal": "watcher_ingest",
            "importance": 0.40,
            "goal_alignment": 0.45,
        }
        evaluation = evaluate_live_trigger(
            db=db,
            trigger={"trigger_type": "watcher", "source": "watcher_router", "goal": "watcher_ingest"},
            user_id=user_id,
            context=trigger_context,
        )
        return {
            "status": "SUCCESS",
            "output_patch": {
                "watcher_evaluation": evaluation,
                "watcher_trigger_context": trigger_context,
                "watcher_decision": evaluation.get("decision", "ignore"),
            },
        }
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("watcher_record_decision_node")
def watcher_record_decision_node(state, context):
    """Persist the autonomy decision and emit the AUTONOMY_DECISION system event."""
    try:
        from utils.trace_context import ensure_trace_id
        from agents.autonomous_controller import record_decision

        db = context.get("db")
        user_id = state.get("user_id")
        evaluation = state.get("watcher_evaluation") or {}
        trigger_context = state.get("watcher_trigger_context") or {}
        trace_id = str(ensure_trace_id())
        record_decision(
            db=db,
            trigger={"trigger_type": "watcher", "source": "watcher_router", "goal": "watcher_ingest"},
            evaluation=evaluation,
            user_id=user_id,
            trace_id=trace_id,
            context=trigger_context,
        )
        return {
            "status": "SUCCESS",
            "output_patch": {"watcher_trace_id": trace_id},
        }
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("watcher_defer_job_node")
def watcher_defer_job_node(state, context):
    """Create a deferred AutomationLog entry and build the DEFERRED response."""
    try:
        from platform_layer.async_job_service import build_deferred_response, defer_async_job

        user_id = state.get("user_id")
        evaluation = state.get("watcher_evaluation") or {}
        trigger_context = state.get("watcher_trigger_context") or {}
        signals = state.get("signals") or []
        log_id = defer_async_job(
            task_name="watcher.ingest",
            payload={
                "signals": signals,
                "user_id": user_id,
                "__autonomy": {
                    "trigger_type": "watcher",
                    "source": "watcher_router",
                    "context": trigger_context,
                },
            },
            user_id=user_id,
            source="watcher_router",
            decision=evaluation,
        )
        result = build_deferred_response(
            log_id,
            task_name="watcher.ingest",
            source="watcher_router",
            decision=evaluation,
        )
        return {
            "status": "SUCCESS",
            "output_patch": {"watcher_evaluate_trigger_result": result},
        }
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("watcher_ignore_node")
def watcher_ignore_node(state, context):
    """Build the IGNORED response — no ingest, no deferred job."""
    try:
        from agents.autonomous_controller import build_decision_response

        evaluation = state.get("watcher_evaluation") or {}
        trace_id = state.get("watcher_trace_id") or ""
        result = build_decision_response(
            evaluation,
            trace_id=trace_id,
            result={"accepted": 0, "session_ended_count": 0, "orchestration": None},
        )
        return {
            "status": "SUCCESS",
            "output_patch": {"watcher_evaluate_trigger_result": result},
        }
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


@register_node("watcher_execute_wrap_node")
def watcher_execute_wrap_node(state, context):
    """
    Bridge node: re-packages watcher_ingest_result under watcher_evaluate_trigger_result
    so that the watcher_evaluate_trigger flow has a single result key regardless of which
    terminal branch ran.
    """
    ingest = state.get("watcher_ingest_result") or {}
    result = {
        "accepted": int(ingest.get("accepted") or 0),
        "session_ended_count": int(ingest.get("session_ended_count") or 0),
        "orchestration": ingest.get("orchestration"),
    }
    return {
        "status": "SUCCESS",
        "output_patch": {"watcher_evaluate_trigger_result": result},
    }


@register_node("health_dashboard_list_node")
def health_dashboard_list_node(state, context):
    try:
        from db.models.system_health_log import SystemHealthLog

        db = context.get("db")
        limit = int(state.get("limit") or 20)

        logs = (
            db.query(SystemHealthLog)
            .order_by(SystemHealthLog.timestamp.desc())
            .limit(limit)
            .all()
        )
        formatted = [
            {
                "timestamp": log.timestamp.isoformat(),
                "status": log.status,
                "avg_latency_ms": log.avg_latency_ms,
                "components": log.components,
                "api_endpoints": log.api_endpoints,
            }
            for log in logs
        ]
        return {
            "status": "SUCCESS",
            "output_patch": {
                "health_dashboard_list_result": {"count": len(formatted), "logs": formatted}
            },
        }
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# ── Registration ───────────────────────────────────────────────────────────────

def register_extended_flows():
    """Register all single-node flows for the Hard Execution Boundary migration."""
    flows = {
        # ARM
        "arm_logs": "arm_logs_node",
        "arm_config_get": "arm_config_get_node",
        "arm_config_update": "arm_config_update_node",
        "arm_metrics": "arm_metrics_node",
        "arm_config_suggest": "arm_config_suggest_node",
        # Goals
        "goals_list": "goals_list_node",
        "goals_state": "goals_state_node",
        # Score
        "score_get": "score_get_node",
        "score_history": "score_history_node",
        "score_feedback_list": "score_feedback_list_node",
        # LeadGen
        "leadgen_list": "leadgen_list_node",
        "leadgen_preview_search": "leadgen_preview_search_node",
        # Tasks
        "tasks_list": "tasks_list_node",
        "tasks_recurrence_check": "tasks_recurrence_check_node",
        # Agent
        "agent_run_create": "agent_run_create_node",
        "agent_runs_list": "agent_runs_list_node",
        "agent_run_get": "agent_run_get_node",
        "agent_run_approve": "agent_run_approve_node",
        "agent_run_reject": "agent_run_reject_node",
        "agent_run_recover": "agent_run_recover_node",
        "agent_run_replay": "agent_run_replay_node",
        "agent_run_steps": "agent_run_steps_node",
        "agent_run_events": "agent_run_events_node",
        "agent_tools_list": "agent_tools_list_node",
        "agent_trust_get": "agent_trust_get_node",
        "agent_trust_update": "agent_trust_update_node",
        "agent_suggestions_get": "agent_suggestions_get_node",
        # Analytics
        "analytics_linkedin_ingest": "analytics_linkedin_ingest_node",
        "analytics_masterplan_get": "analytics_masterplan_get_node",
        "analytics_masterplan_summary": "analytics_masterplan_summary_node",
        # Autonomy
        "autonomy_decisions_list": "autonomy_decisions_list_node",
        # Dashboard
        "dashboard_overview": "dashboard_overview_node",
        "health_dashboard_list": "health_dashboard_list_node",
        # Watcher (watcher_signals_receive registered as multi-node below)
        "watcher_signals_list": "watcher_signals_list_node",
        # Genesis
        "genesis_session_create": "genesis_session_create_node",
        "genesis_session_get": "genesis_session_get_node",
        "genesis_draft_get": "genesis_draft_get_node",
        "genesis_synthesize": "genesis_synthesize_node",
        "genesis_audit": "genesis_audit_node",
        "genesis_lock": "genesis_lock_node",
        "genesis_activate": "genesis_activate_node",
        # Flow
        "flow_runs_list": "flow_runs_list_node",
        "flow_run_get": "flow_run_get_node",
        "flow_run_history": "flow_run_history_node",
        "flow_run_resume": "flow_run_resume_node",
        "flow_registry_get": "flow_registry_get_node",
        # Memory
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
        # memory_execute_loop registered as multi-node below
        # Automation
        "automation_logs_list": "automation_logs_list_node",
        "automation_log_get": "automation_log_get_node",
        "automation_log_replay": "automation_log_replay_node",
        "automation_scheduler_status": "automation_scheduler_status_node",
        "automation_task_trigger": "automation_task_trigger_node",
        # Freelance
        "freelance_order_create": "freelance_order_create_node",
        "freelance_order_deliver": "freelance_order_deliver_node",
        "freelance_delivery_update": "freelance_delivery_update_node",
        "freelance_feedback_collect": "freelance_feedback_collect_node",
        "freelance_orders_list": "freelance_orders_list_node",
        "freelance_feedback_list": "freelance_feedback_list_node",
        "freelance_metrics_latest": "freelance_metrics_latest_node",
        "freelance_metrics_update": "freelance_metrics_update_node",
        "freelance_delivery_generate": "freelance_delivery_generate_node",
        # Research
        "research_create": "research_create_node",
        "research_list": "research_list_node",
        "research_query": "research_query_node",
        "search_history_list": "search_history_list_node",
        "search_history_get": "search_history_get_node",
        "search_history_delete": "search_history_delete_node",
        # Masterplan
        "masterplan_lock_from_genesis": "masterplan_lock_from_genesis_node",
        "masterplan_lock": "masterplan_lock_node",
        "masterplan_list": "masterplan_list_node",
        "masterplan_get": "masterplan_get_node",
        "masterplan_anchor": "masterplan_anchor_node",
        "masterplan_projection": "masterplan_projection_node",
        "masterplan_activate": "masterplan_activate_node",
        # Observability
        "observability_scheduler_status": "observability_scheduler_status_node",
        "observability_requests": "observability_requests_node",
        "observability_dashboard": "observability_dashboard_node",
        "observability_rippletrace": "observability_rippletrace_node",
    }
    for flow_name, node_name in flows.items():
        if flow_name not in FLOW_REGISTRY:
            register_flow(flow_name, _single(node_name))

    # Multi-node flows — these delegate to existing node sequences rather than
    # wrapping run_flow() calls, keeping the execution graph flat.

    # watcher_signals_receive: identical node graph to watcher_ingest.
    # Result key: watcher_ingest_result (set in workflow_key_map).
    if "watcher_signals_receive" not in FLOW_REGISTRY:
        register_flow(
            "watcher_signals_receive",
            {
                "start": "watcher_ingest_validate",
                "edges": {
                    "watcher_ingest_validate": ["watcher_ingest_persist"],
                    "watcher_ingest_persist": ["watcher_ingest_orchestrate"],
                },
                "end": ["watcher_ingest_orchestrate"],
            },
        )

    # memory_execute_loop: identical node graph to memory_execution.
    # Result key: memory_execution_response (set in workflow_key_map).
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

    # watcher_evaluate_trigger: autonomy gate → ingest or defer or ignore.
    # Conditional edges branch on watcher_decision written by watcher_record_decision_node.
    # The execute branch reuses the existing watcher_ingest_* nodes and wraps the
    # result key via watcher_execute_wrap_node so all branches share one result key.
    if "watcher_evaluate_trigger" not in FLOW_REGISTRY:
        register_flow(
            "watcher_evaluate_trigger",
            {
                "start": "watcher_evaluate_trigger_node",
                "edges": {
                    "watcher_evaluate_trigger_node": ["watcher_record_decision_node"],
                    "watcher_record_decision_node": [
                        {
                            "condition": lambda s: s.get("watcher_decision") == "execute",
                            "target": "watcher_ingest_validate",
                        },
                        {
                            "condition": lambda s: s.get("watcher_decision") == "defer",
                            "target": "watcher_defer_job_node",
                        },
                        {
                            "condition": lambda s: True,
                            "target": "watcher_ignore_node",
                        },
                    ],
                    "watcher_ingest_validate": ["watcher_ingest_persist"],
                    "watcher_ingest_persist": ["watcher_ingest_orchestrate"],
                    "watcher_ingest_orchestrate": ["watcher_execute_wrap_node"],
                },
                "end": [
                    "watcher_execute_wrap_node",
                    "watcher_defer_job_node",
                    "watcher_ignore_node",
                ],
            },
        )

    logger.info("register_extended_flows: %d flows registered", len(flows))


