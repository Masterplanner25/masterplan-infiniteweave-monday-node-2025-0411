"""ARM (Autonomous Refactoring Module) domain bootstrap."""
from __future__ import annotations

import logging
from threading import Lock

logger = logging.getLogger(__name__)

_ANALYZER = None
_ANALYZER_LOCK = Lock()

BOOTSTRAP_DEPENDS_ON: list[str] = []
APP_DEPENDS_ON: list[str] = ["agent", "analytics"]


def register() -> None:
    _register_models()
    _register_router()
    _register_route_prefixes()
    _register_response_adapters()
    _register_syscalls()
    _register_jobs()
    _register_async_jobs()
    _register_agent_tools()
    _register_agent_capabilities()
    _register_capture_rules()
    _register_flow_results()
    _register_flow_plans()
    _register_required_flow_nodes()
    _register_health_check()


def _register_models() -> None:
    from AINDY.db.database import Base
    from AINDY.db.model_registry import register_models
    from AINDY.platform_layer.registry import register_symbols
    import apps.arm.models as arm_models

    register_models(arm_models.register_models)
    register_symbols(
        {
            name: value
            for name, value in vars(arm_models).items()
            if isinstance(value, type) and getattr(value, "metadata", None) is Base.metadata
        }
    )


def _register_router() -> None:
    from AINDY.platform_layer.registry import register_router
    from apps.arm.routes.arm_router import router as arm_router
    register_router(arm_router)


def _register_route_prefixes() -> None:
    from AINDY.platform_layer.registry import register_route_prefix
    register_route_prefix("arm", "flow")


def _register_response_adapters() -> None:
    from AINDY.platform_layer.registry import register_response_adapter
    from AINDY.platform_layer.response_adapters import raw_json_adapter
    register_response_adapter("arm", raw_json_adapter)


def _register_syscalls() -> None:
    from apps.arm.syscalls import register_arm_syscall_handlers

    register_arm_syscall_handlers()


def _register_jobs() -> None:
    from AINDY.platform_layer.registry import register_job
    register_job("arm.analyzer", _create_arm_analyzer)


def _register_async_jobs() -> None:
    from AINDY.platform_layer.async_job_service import register_async_job
    register_async_job("arm.analyze")(_job_arm_analyze)
    register_async_job("arm.generate")(_job_arm_generate)


def _register_agent_tools() -> None:
    from apps.arm.agents.tools import register as register_arm_tools
    register_arm_tools()


def _register_agent_capabilities() -> None:
    from apps.arm.agents.capabilities import register as register_arm_capabilities
    register_arm_capabilities()


def _register_capture_rules() -> None:
    from AINDY.platform_layer.registry import register_memory_policy
    from apps.arm.memory_policy import register as register_arm_memory_policy
    register_arm_memory_policy(register_memory_policy)


def _register_flow_results() -> None:
    from AINDY.platform_layer.registry import register_flow_result

    result_keys = {
        "arm_analysis": "analysis_result",
        "arm_generate": "generation_result",
        "arm_logs": "arm_logs_result",
        "arm_config_get": "arm_config_get_result",
        "arm_config_update": "arm_config_update_result",
        "arm_metrics": "arm_metrics_result",
        "arm_config_suggest": "arm_config_suggest_result",
    }
    for flow_name, result_key in result_keys.items():
        register_flow_result(flow_name, result_key=result_key)

    register_flow_result("arm_analysis", completion_event="arm_analysis_complete")


def _register_flow_plans() -> None:
    from AINDY.platform_layer.registry import register_flow_plan

    register_flow_plan(
        "arm_analysis",
        {"steps": ["arm_validate_input", "arm_analyze_code", "arm_store_result"]},
    )
    register_flow_plan(
        "arm_generation",
        {"steps": ["validate_input", "generate_code", "store_result"]},
    )


def _register_required_flow_nodes() -> None:
    from AINDY.platform_layer.registry import register_required_flow_node

    register_required_flow_node("arm_analyze_code")
    register_required_flow_node("arm_validate_input")


def _create_arm_analyzer():
    from apps.arm.services.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer
    return DeepSeekCodeAnalyzer()


def _get_analyzer():
    global _ANALYZER
    if _ANALYZER is None:
        with _ANALYZER_LOCK:
            if _ANALYZER is None:
                _ANALYZER = _create_arm_analyzer()
    return _ANALYZER


def _job_arm_analyze(payload: dict, db):
    analyzer = _get_analyzer()
    return analyzer.run_analysis(
        file_path=payload["file_path"],
        user_id=payload["user_id"],
        db=db,
        complexity=payload.get("complexity"),
        urgency=payload.get("urgency"),
        additional_context=payload.get("context", ""),
    )


def _job_arm_generate(payload: dict, db):
    analyzer = _get_analyzer()
    return analyzer.generate_code(
        prompt=payload["prompt"],
        user_id=payload["user_id"],
        db=db,
        original_code=payload.get("original_code", ""),
        language=payload.get("language", "python"),
        generation_type=payload.get("generation_type", "generate"),
        analysis_id=payload.get("analysis_id"),
        complexity=payload.get("complexity"),
        urgency=payload.get("urgency"),
    )


def _register_health_check() -> None:
    from AINDY.platform_layer.registry import register_health_check

    register_health_check("arm", _check_health)


def _check_health() -> dict:
    db = None
    reasons: list[str] = []
    try:
        from AINDY.config import settings
        from AINDY.db.database import SessionLocal
        from apps.arm.models import ArmConfig

        db = SessionLocal()
        db.query(ArmConfig.id).limit(1).all()
        if not settings.DEEPSEEK_API_KEY:
            reasons.append("deepseek api key not configured")
        if reasons:
            return {"status": "degraded", "reason": "; ".join(reasons)}
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "degraded", "reason": str(exc)}
    finally:
        if db is not None:
            db.close()
