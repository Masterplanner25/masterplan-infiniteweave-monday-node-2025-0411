"""
Agent Runtime — Sprint N+4 Agentics Phase 1+2

Lifecycle: goal → plan → dry-run preview → approve → execute → memory

Phase 1: Minimal Runtime
  - GPT-4o plan generation from plain-English goal
  - Tool registry execution loop
  - AgentRun + AgentStep persistence

Phase 2: Dry-Run + Approval
  - Plan returned as preview before execution
  - Trust gate: auto-execute low/medium if trust settings allow
  - High-risk plans ALWAYS require explicit approval

Plan schema (JSON mode):
  {
    "executive_summary": "...",
    "steps": [
      {
        "tool": "task.create",
        "args": {"name": "...", ...},
        "risk_level": "low",
        "description": "human-readable step description"
      }
    ],
    "overall_risk": "low|medium|high"
  }
"""
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from config import settings
from services.agent_tools import TOOL_REGISTRY, execute_tool, get_tool_risk

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


# ── Plan Schema Prompt ────────────────────────────────────────────────────────

PLANNER_SYSTEM_PROMPT = """You are A.I.N.D.Y.'s strategic agent planner.

Given a user goal, produce a structured execution plan using only the available tools.

Available tools and their risk levels:
- task.create (low) — create a new task
- task.complete (medium) — mark a task as done
- memory.recall (low) — recall relevant past memories
- memory.write (low) — write a memory node
- arm.analyze (medium) — analyze a code file
- arm.generate (medium) — generate or refactor code
- leadgen.search (medium) — search for B2B leads
- research.query (low) — query external research sources
- genesis.message (high) — send a message to the Genesis strategic planner

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
- Be specific in args — use realistic values based on the goal
- overall_risk must match the highest step risk_level
- Return ONLY the JSON object, no markdown, no extra text
"""


# ── Trust Gate ────────────────────────────────────────────────────────────────

def _requires_approval(overall_risk: str, user_id: str, db: Session) -> bool:
    """
    Returns True if the plan requires human approval before execution.

    High risk: ALWAYS requires approval (hardcoded invariant).
    Medium/low: requires approval unless trust settings allow auto-execute.
    """
    if overall_risk == "high":
        return True

    from db.models.agent_run import AgentTrustSettings

    trust = db.query(AgentTrustSettings).filter(
        AgentTrustSettings.user_id == user_id
    ).first()

    if not trust:
        return True  # Default: require approval

    if overall_risk == "medium":
        return not trust.auto_execute_medium
    if overall_risk == "low":
        return not trust.auto_execute_low

    return True


# ── Planner ───────────────────────────────────────────────────────────────────

def _build_kpi_context_block(user_id: str, db: Session) -> str:
    """
    Build a KPI context block for the planner prompt.

    Returns a formatted string if scores exist, empty string otherwise.
    Guides the planner toward appropriate tool choices based on current KPI state.
    Never raises.
    """
    try:
        from services.infinity_service import get_user_kpi_snapshot
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
            lines.append("- Focus quality is low — prefer memory.recall and research.query over intensive tasks")
        if snapshot["execution_speed"] < 40:
            lines.append("- Execution speed is low — bias toward task.create to rebuild momentum")
        if snapshot["ai_productivity_boost"] < 40:
            lines.append("- ARM usage is low — consider arm.analyze to improve code quality")
        if snapshot["master_score"] >= 70:
            lines.append("- High overall score — medium-risk tools are appropriate given strong performance")

        return "\n".join(lines)
    except Exception:
        return ""


def generate_plan(goal: str, user_id: str, db: Session) -> Optional[dict]:
    """
    Generate a structured execution plan from a plain-English goal.

    Injects the user's live KPI snapshot into the system prompt when available.
    Returns the parsed plan dict or None on failure.
    Never raises.
    """
    try:
        kpi_block = _build_kpi_context_block(user_id=user_id, db=db)
        system_prompt = PLANNER_SYSTEM_PROMPT + kpi_block

        client = _get_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Goal: {goal}"},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        plan = json.loads(content)

        # Validate structure
        if "steps" not in plan or "overall_risk" not in plan:
            logger.warning("[AgentRuntime] Plan missing required fields: %s", plan)
            return None

        # Enforce overall_risk invariant
        step_risks = [s.get("risk_level", "high") for s in plan["steps"]]
        risk_order = {"low": 0, "medium": 1, "high": 2}
        max_risk = max(step_risks, key=lambda r: risk_order.get(r, 2), default="high")
        if risk_order.get(plan["overall_risk"], 0) < risk_order.get(max_risk, 0):
            plan["overall_risk"] = max_risk

        return plan

    except Exception as exc:
        logger.warning("[AgentRuntime] Plan generation failed: %s", exc)
        return None


# ── Run creation ──────────────────────────────────────────────────────────────

def create_run(goal: str, user_id: str, db: Session) -> Optional[dict]:
    """
    Create an AgentRun: generate plan, apply trust gate, persist to DB.

    Returns the run dict (including status) or None on failure.

    Status after creation:
      - "pending_approval" if trust gate requires human approval
      - "approved"         if trust settings allow auto-execution
    """
    try:
        from db.models.agent_run import AgentRun

        plan = generate_plan(goal=goal, user_id=user_id, db=db)
        if not plan:
            return None

        overall_risk = plan.get("overall_risk", "high")
        needs_approval = _requires_approval(overall_risk, user_id, db)
        status = "pending_approval" if needs_approval else "approved"

        run = AgentRun(
            user_id=user_id,
            goal=goal,
            plan=plan,
            executive_summary=plan.get("executive_summary", ""),
            overall_risk=overall_risk,
            status=status,
            steps_total=len(plan.get("steps", [])),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        logger.info(
            "[AgentRuntime] Run created: %s (risk=%s, status=%s)",
            run.id, overall_risk, status,
        )

        return _run_to_dict(run)

    except Exception as exc:
        logger.warning("[AgentRuntime] create_run failed: %s", exc)
        return None


# ── Executor ─────────────────────────────────────────────────────────────────

def execute_run(run_id: str, user_id: str, db: Session) -> Optional[dict]:
    """
    Execute an approved AgentRun — run all steps sequentially.

    Requires run.status == "approved".
    Returns updated run dict or None on failure.
    Never raises.
    """
    try:
        from db.models.agent_run import AgentRun, AgentStep

        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            logger.warning("[AgentRuntime] Run %s not found", run_id)
            return None

        if run.status not in ("approved",):
            logger.warning(
                "[AgentRuntime] Run %s cannot execute — status=%s", run_id, run.status
            )
            return _run_to_dict(run)

        if run.user_id != user_id:
            logger.warning("[AgentRuntime] Run %s owner mismatch", run_id)
            return None

        # Mark as executing
        run.status = "executing"
        run.started_at = datetime.now(timezone.utc)
        db.commit()

        steps = (run.plan or {}).get("steps", [])
        step_results = []
        run_success = True

        for idx, step in enumerate(steps):
            tool_name = step.get("tool", "")
            tool_args = step.get("args", {})
            risk_level = step.get("risk_level", "high")
            description = step.get("description", "")

            start_ms = int(time.time() * 1000)

            tool_result = execute_tool(
                tool_name=tool_name,
                args=tool_args,
                user_id=user_id,
                db=db,
            )

            exec_ms = int(time.time() * 1000) - start_ms
            step_status = "success" if tool_result["success"] else "failed"

            # Persist step
            agent_step = AgentStep(
                run_id=run.id,
                step_index=idx,
                tool_name=tool_name,
                tool_args=tool_args,
                risk_level=risk_level,
                description=description,
                status=step_status,
                result=tool_result.get("result"),
                error_message=tool_result.get("error"),
                execution_ms=exec_ms,
                executed_at=datetime.now(timezone.utc),
            )
            db.add(agent_step)

            run.steps_completed = idx + 1
            run.current_step = idx + 1
            db.commit()

            step_results.append({
                "step_index": idx,
                "tool": tool_name,
                "status": step_status,
                "result": tool_result.get("result"),
                "error": tool_result.get("error"),
            })

            if not tool_result["success"]:
                logger.warning(
                    "[AgentRuntime] Step %d (%s) failed: %s",
                    idx, tool_name, tool_result.get("error"),
                )
                run_success = False
                # Continue remaining steps (non-blocking failure)

        # Finalize run
        run.status = "completed" if run_success else "failed"
        run.completed_at = datetime.now(timezone.utc)
        run.result = {"steps": step_results}
        if not run_success:
            failed = [s for s in step_results if s["status"] == "failed"]
            run.error_message = f"{len(failed)} step(s) failed"
        db.commit()

        logger.info(
            "[AgentRuntime] Run %s %s (%d/%d steps)",
            run_id, run.status, run.steps_completed, run.steps_total,
        )

        # Write execution summary to memory (fire-and-forget)
        try:
            from bridge.bridge import create_memory_node
            create_memory_node(
                content=(
                    f"Agent run completed: '{run.goal[:100]}'. "
                    f"Steps: {run.steps_completed}/{run.steps_total}. "
                    f"Status: {run.status}."
                ),
                source="agent_runtime",
                tags=["agent", "execution", run.status],
                user_id=user_id,
                db=db,
                node_type="outcome",
            )
        except Exception:
            pass

        return _run_to_dict(run)

    except Exception as exc:
        logger.warning("[AgentRuntime] execute_run failed for %s: %s", run_id, exc)
        return None


# ── Approval / Rejection ─────────────────────────────────────────────────────

def approve_run(run_id: str, user_id: str, db: Session) -> Optional[dict]:
    """
    Approve a pending_approval run and execute it immediately.
    Returns the final run dict or None on failure.
    """
    try:
        from db.models.agent_run import AgentRun

        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run or run.user_id != user_id:
            return None

        if run.status != "pending_approval":
            return _run_to_dict(run)

        run.status = "approved"
        run.approved_at = datetime.now(timezone.utc)
        db.commit()

        return execute_run(run_id=run_id, user_id=user_id, db=db)

    except Exception as exc:
        logger.warning("[AgentRuntime] approve_run failed for %s: %s", run_id, exc)
        return None


def reject_run(run_id: str, user_id: str, db: Session) -> Optional[dict]:
    """Reject a pending_approval run. Returns updated run dict or None."""
    try:
        from db.models.agent_run import AgentRun

        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run or run.user_id != user_id:
            return None

        if run.status != "pending_approval":
            return _run_to_dict(run)

        run.status = "rejected"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

        return _run_to_dict(run)

    except Exception as exc:
        logger.warning("[AgentRuntime] reject_run failed for %s: %s", run_id, exc)
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_to_dict(run) -> dict:
    return {
        "run_id": str(run.id),
        "user_id": run.user_id,
        "goal": run.goal,
        "executive_summary": run.executive_summary,
        "overall_risk": run.overall_risk,
        "status": run.status,
        "steps_total": run.steps_total,
        "steps_completed": run.steps_completed,
        "plan": run.plan,
        "result": run.result,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "approved_at": run.approved_at.isoformat() if run.approved_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
