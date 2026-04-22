import logging

from AINDY.runtime.flow_helpers import register_nodes, register_single_node_flows

logger = logging.getLogger(__name__)


def arm_logs_node(state, context):
    try:
        from uuid import UUID
        from apps.arm.models import AnalysisResult, CodeGeneration

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


def arm_config_get_node(state, context):
    try:
        from apps.arm.services.deepseek.config_manager_deepseek import ConfigManager

        try:
            manager = ConfigManager(db=context.get("db"))
        except TypeError:
            manager = ConfigManager()
        return {
            "status": "SUCCESS",
            "output_patch": {
                "arm_config_get_result": manager.get_all()
            },
        }
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def arm_config_update_node(state, context):
    try:
        from apps.arm.services.deepseek.config_manager_deepseek import ConfigManager

        try:
            manager = ConfigManager(db=context.get("db"))
        except TypeError:
            manager = ConfigManager()
        updated = manager.update(state.get("updates", {}))
        return {"status": "SUCCESS", "output_patch": {"arm_config_update_result": {"status": "updated", "config": updated}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def arm_metrics_node(state, context):
    try:
        from apps.arm.services.arm_metrics_service import ARMMetricsService

        db = context.get("db")
        user_id = context.get("user_id")
        window = state.get("window", 30)
        result = ARMMetricsService(db=db, user_id=user_id).get_all_metrics(window=window)
        return {"status": "SUCCESS", "output_patch": {"arm_metrics_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def arm_config_suggest_node(state, context):
    try:
        from apps.arm.services.deepseek.config_manager_deepseek import ConfigManager
        from apps.arm.services.arm_metrics_service import ARMMetricsService, ARMConfigSuggestionEngine

        db = context.get("db")
        user_id = context.get("user_id")
        window = state.get("window", 30)
        metrics = ARMMetricsService(db=db, user_id=user_id).get_all_metrics(window=window)
        try:
            manager = ConfigManager(db=db)
        except TypeError:
            manager = ConfigManager()
        current_config = manager.get_all()
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


def register() -> None:
    register_nodes(
        {
            "arm_logs_node": arm_logs_node,
            "arm_config_get_node": arm_config_get_node,
            "arm_config_update_node": arm_config_update_node,
            "arm_metrics_node": arm_metrics_node,
            "arm_config_suggest_node": arm_config_suggest_node,
        }
    )
    register_single_node_flows(
        {
            "arm_logs": "arm_logs_node",
            "arm_config_get": "arm_config_get_node",
            "arm_config_update": "arm_config_update_node",
            "arm_metrics": "arm_metrics_node",
            "arm_config_suggest": "arm_config_suggest_node",
        }
    )
