from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from AINDY.agents.agent_runtime.shared import get_runtime_compat_module, logger

PLANNER_SYSTEM_PROMPT = """You are a generic agent planner.

Produce a structured execution plan using only the injected tool catalog.

Available tools are provided by registered application extensions.

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
- Be specific in args using the request context
- overall_risk must match the highest step risk_level
- Return ONLY the JSON object, no markdown, no extra text
"""


def _requires_approval(overall_risk: str, user_id: str, db: Session) -> bool:
    if overall_risk == "high":
        return True

    from AINDY.db.models.agent_run import AgentTrustSettings
    from AINDY.platform_layer.user_ids import parse_user_id

    owner_user_id = parse_user_id(user_id)
    owner_filter_value = owner_user_id if owner_user_id is not None else user_id
    trust = db.query(AgentTrustSettings).filter(AgentTrustSettings.user_id == owner_filter_value).first()
    if not trust:
        return True
    if overall_risk == "medium":
        return not trust.auto_execute_medium
    if overall_risk == "low":
        return not trust.auto_execute_low
    return True


def _build_kpi_context_block(user_id: str, db: Session) -> str:
    try:
        compat = get_runtime_compat_module()

        return compat._get_planner_context("default", user_id=user_id, db=db).get("context_block", "")
    except Exception:
        return ""


def _legacy_planner_context_block_disabled(user_id: str, db: Session) -> str:
    return ""


def generate_plan(
    objective: str | None = None,
    user_id: str | None = None,
    db: Session | None = None,
    **values,
) -> Optional[dict]:
    try:
        compat = get_runtime_compat_module()
        from AINDY.config import settings

        objective_text = compat._resolve_objective(objective, values)
        run_type = "default"
        planner_context = compat._get_planner_context(run_type, user_id=user_id, db=db)
        tools = compat._get_tools_for_run(run_type, user_id=user_id, db=db)
        tool_block = ""
        if tools:
            tool_block = "\n\nAvailable tools:\n" + "\n".join(
                f"- {tool.get('name')}: {tool.get('description', '')} (risk={tool.get('risk', 'unknown')})"
                for tool in tools
                if isinstance(tool, dict) and tool.get("name")
            )
        system_prompt = str(planner_context.get("system_prompt") or "")
        if not system_prompt:
            logger.warning("[AgentRuntime] No planner context registered for %s", run_type)
            return None
        context_block = compat._build_kpi_context_block(user_id=user_id, db=db)
        if context_block and context_block not in system_prompt:
            system_prompt += context_block
        system_prompt += tool_block

        response = compat.perform_external_call(
            service_name="openai",
            db=db,
            user_id=user_id,
            endpoint="chat.completions.create",
            model="gpt-4o",
            method="openai.chat",
            extra={"purpose": "agent_plan_generation"},
            operation=lambda: compat.chat_completion(
                compat._get_client(),
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Objective: {objective_text}"},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                timeout=settings.OPENAI_CHAT_TIMEOUT_SECONDS,
            ),
        )
        plan = json.loads(response.choices[0].message.content)
        if "steps" not in plan or "overall_risk" not in plan:
            logger.warning("[AgentRuntime] Plan missing required fields: %s", plan)
            return None

        step_risks = [step.get("risk_level", "high") for step in plan["steps"]]
        risk_order = {"low": 0, "medium": 1, "high": 2}
        max_risk = max(step_risks, key=lambda risk: risk_order.get(risk, 2), default="high")
        if risk_order.get(plan["overall_risk"], 0) < risk_order.get(max_risk, 0):
            plan["overall_risk"] = max_risk
        return plan
    except Exception as exc:
        compat = get_runtime_compat_module()

        compat._plan_failure.reason = f"{type(exc).__name__}: {exc}"
        logger.warning("[AgentRuntime] Plan generation failed: %s", exc)
        return None
