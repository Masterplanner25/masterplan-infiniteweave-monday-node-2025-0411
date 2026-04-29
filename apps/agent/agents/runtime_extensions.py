"""Application-owned agent runtime behavior.

The platform runtime asks these hooks for planner context, available tools, and
post-run behavior without embedding product assumptions in AINDY.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


PLANNER_SYSTEM_PROMPT = """You are A.I.N.D.Y.'s strategic agent planner.

Given a user goal, produce a structured execution plan using only the available tools.

Risk rules:
- overall_risk = the highest risk_level of any step
- If ANY step is high risk, overall_risk must be "high"

Return ONLY valid JSON with exactly this structure:
{
  "executive_summary": "2-3 sentence summary of what the agent will do",
  "steps": [
    {
      "tool": "<tool_name>",
      "args": {<tool-specific args>},
      "risk_level": "low|medium|high",
      "description": "one sentence explaining this step"
    }
  ],
  "overall_risk": "low|medium|high"
}

Rules:
- Use only tools listed above
- Keep plans concise (3-7 steps maximum)
- Be specific in args - use realistic values based on the goal
- overall_risk must match the highest step risk_level
- Return ONLY the JSON object, no markdown, no extra text
"""


def _build_kpi_context_block(user_id, db) -> str:
    try:
        from AINDY.platform_layer.registry import get_job

        get_user_kpi_snapshot = get_job("analytics.kpi_snapshot")
        if get_user_kpi_snapshot is None:
            return ""
        snapshot = get_user_kpi_snapshot(user_id=user_id, db=db)
        if not snapshot:
            return ""

        lines = [
            "",
            "## User Performance Context (Infinity Score)",
            f"Overall score: {snapshot['master_score']:.1f}/100 (confidence: {snapshot['confidence']})",
            f"- Execution speed:      {snapshot['execution_speed']:.1f}",
            f"- Decision efficiency:  {snapshot['decision_efficiency']:.1f}",
            f"- AI productivity:      {snapshot['ai_productivity_boost']:.1f}",
            f"- Focus quality:        {snapshot['focus_quality']:.1f}",
            f"- Masterplan progress:  {snapshot['masterplan_progress']:.1f}",
            "",
            "Scoring guidance:",
        ]

        if snapshot["focus_quality"] < 40:
            lines.append("- Focus quality is low - prefer memory.recall and research.query over intensive tasks")
        if snapshot["execution_speed"] < 40:
            lines.append("- Execution speed is low - bias toward task.create to rebuild momentum")
        if snapshot["ai_productivity_boost"] < 40:
            lines.append("- ARM usage is low - consider arm.analyze to improve code quality")
        if snapshot["master_score"] >= 70:
            lines.append("- High overall score - medium-risk tools are appropriate given strong performance")

        return "\n".join(lines)
    except Exception:
        return ""


def build_planner_context(context: dict) -> dict:
    db = context.get("db")
    user_id = context.get("user_id")
    kpi_context = _build_kpi_context_block(user_id, db)
    prompt = PLANNER_SYSTEM_PROMPT + kpi_context
    try:
        from AINDY.memory.memory_helpers import enrich_context, format_memories_for_prompt

        memory_context = enrich_context({
            "db": db,
            "user_id": str(user_id) if user_id else None,
            "node_name": "agent_planning",
            "agent_type": context.get("run_type") or "default",
        })
        prompt += format_memories_for_prompt(memory_context.get("memory_context") or [])
    except Exception as exc:
        logger.debug("agent planner memory context skipped: %s", exc)
    return {"system_prompt": prompt, "context_block": kpi_context}


def get_tools_for_run(_context: dict) -> list[dict]:
    from AINDY.agents.tool_registry import TOOL_REGISTRY
    from AINDY.platform_layer.registry import load_plugins

    load_plugins()

    return [
        {
            "name": name,
            "risk": metadata.get("risk"),
            "description": metadata.get("description"),
            "capability": metadata.get("capability"),
            "required_capability": metadata.get("required_capability"),
            "category": metadata.get("category"),
            "egress_scope": metadata.get("egress_scope"),
        }
        for name, metadata in TOOL_REGISTRY.items()
    ]


def handle_agent_run_completed(context: dict):
    run = context.get("run")
    db = context.get("db")
    user_id = context.get("user_id")
    if run is None or db is None:
        return None

    result_payload = run.result if isinstance(run.result, dict) else {}
    if result_payload.get("loop_enforced"):
        return None

    try:
        from AINDY.platform_layer.registry import get_job

        execute_infinity_orchestrator = get_job("analytics.infinity_execute")
        if execute_infinity_orchestrator is None:
            raise RuntimeError("No registered infinity orchestration job")
        orchestration = execute_infinity_orchestrator(
            user_id=user_id,
            trigger_event="agent_completed",
            db=db,
        )
        run.result = {
            **result_payload,
            "loop_enforced": True,
            "next_action": orchestration["next_action"],
        }
        db.commit()
        db.refresh(run)
        return run.result
    except Exception as exc:
        logger.warning(
            "[AgentRuntimeExtensions] Agent completion orchestrator failed for %s: %s",
            getattr(run, "id", None),
            exc,
        )
        return None


def register() -> None:
    from AINDY.platform_layer.registry import (
        register_agent_event,
        register_agent_planner_context,
        register_agent_run_tools,
    )

    register_agent_planner_context("default", build_planner_context)
    register_agent_run_tools("default", get_tools_for_run)
    register_agent_event("agent.run.completed", handle_agent_run_completed)
