"""
Agent Runtime — Sprint N+4 Agentics Phase 1+2 / Sprint N+6 Deterministic Agent / Sprint N+7 Observability

Lifecycle: goal → plan → dry-run preview → approve → execute → memory

Phase 1: Minimal Runtime
  - GPT-4o plan generation from plain-English goal
  - Tool registry execution loop
  - AgentRun + AgentStep persistence

Phase 2: Dry-Run + Approval
  - Plan returned as preview before execution
  - Trust gate: auto-execute low/medium if trust settings allow
  - High-risk plans ALWAYS require explicit approval

Sprint N+6: Deterministic execution via NodusAgentAdapter
  - execute_run() delegates entirely to NodusAgentAdapter.execute_with_flow()
  - Per-step retry (low/medium: 3x; high: halt immediately)
  - FlowRun checkpointing + FlowHistory → Memory Bridge capture

Sprint N+7: Agent Observability
  - replay_run() creates a new AgentRun from original plan; trust gate re-applied
  - replayed_from_run_id tracks lineage in _run_to_dict()

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

from AINDY.config import settings
from AINDY.agents.agent_tools import TOOL_REGISTRY
from AINDY.agents.capability_service import mint_token
from AINDY.agents.agent_coordinator import decide_execution_mode
from AINDY.agents.agent_coordinator import register_or_update_agent
from AINDY.core.execution_signal_helper import record_agent_event
from AINDY.platform_layer.external_call_service import perform_external_call
from AINDY.core.system_event_service import emit_error_event
from AINDY.utils.trace_context import get_parent_event_id
from AINDY.utils.trace_context import get_trace_id
from AINDY.utils.trace_context import reset_parent_event_id
from AINDY.utils.trace_context import set_parent_event_id
from AINDY.utils.user_ids import parse_user_id

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None
LOCAL_AGENT_ID = "00000000-0000-0000-0000-000000000001"


def _db_user_id(user_id: str):
    parsed = parse_user_id(user_id)
    return parsed if parsed is not None else user_id


def _db_run_id(run_id):
    parsed = parse_user_id(run_id)
    return parsed if parsed is not None else run_id


def _user_matches(left, right) -> bool:
    left_uuid = parse_user_id(left)
    right_uuid = parse_user_id(right)
    if left_uuid is not None and right_uuid is not None:
        return left_uuid == right_uuid
    return str(left) == str(right)


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

    from AINDY.db.models.agent_run import AgentTrustSettings
    owner_user_id = parse_user_id(user_id)
    owner_filter_value = owner_user_id if owner_user_id is not None else user_id

    trust = db.query(AgentTrustSettings).filter(
        AgentTrustSettings.user_id == owner_filter_value
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
        from AINDY.domain.infinity_service import get_user_kpi_snapshot
        snapshot = get_user_kpi_snapshot(user_id=_db_user_id(user_id), db=db)
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
        from AINDY.memory.memory_helpers import enrich_context, format_memories_for_prompt
        _plan_ctx = enrich_context({
            "db": db,
            "user_id": str(user_id) if user_id else None,
            "node_name": "agent_planning",
            "agent_type": "default",
        })
        memory_block = format_memories_for_prompt(_plan_ctx.get("memory_context") or [])
        system_prompt = PLANNER_SYSTEM_PROMPT + kpi_block + memory_block

        client = _get_client()
        response = perform_external_call(
            service_name="openai",
            db=db,
            user_id=user_id,
            endpoint="chat.completions.create",
            model="gpt-4o",
            method="openai.chat",
            extra={"purpose": "agent_plan_generation"},
            operation=lambda: client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Goal: {goal}"},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            ),
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
        from AINDY.db.models.agent_run import AgentRun
        user_db_id = _db_user_id(user_id)

        plan = generate_plan(goal=goal, user_id=user_db_id, db=db)
        if not plan:
            emit_error_event(
                db=db,
                error_type="agent_plan_generation",
                message="Failed to generate agent plan",
                user_id=user_db_id,
                trace_id=get_trace_id(),
                parent_event_id=get_parent_event_id(),
                source="agent",
                payload={"goal_preview": goal[:120]},
                required=True,
            )
            return None

        overall_risk = plan.get("overall_risk", "high")
        needs_approval = _requires_approval(overall_risk, user_db_id, db)
        status = "pending_approval" if needs_approval else "approved"

        # Generate correlation token — propagated through all child records
        correlation_id = f"run_{uuid.uuid4()}"

        run = AgentRun(
            user_id=user_db_id,
            agent_type="default",
            trace_id=get_trace_id(),
            goal=goal,
            plan=plan,
            executive_summary=plan.get("executive_summary", ""),
            overall_risk=overall_risk,
            status=status,
            steps_total=len(plan.get("steps", [])),
            correlation_id=correlation_id,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService
            ExecutionUnitService(db).create(
                eu_type="agent",
                user_id=user_db_id,
                source_type="agent_run",
                source_id=str(run.id),
                correlation_id=correlation_id,
                status="pending",
                extra={"goal_preview": goal[:120], "overall_risk": overall_risk},
            )
        except Exception as _eu_exc:
            logger.warning("[EU] agent hook create failed — non-fatal | error=%s", _eu_exc)

        if status == "approved":
            token = mint_token(
                run_id=str(run.id),
                user_id=user_db_id,
                plan=plan,
                db=db,
                approval_mode="auto",
                agent_type=getattr(run, "agent_type", "default"),
            )
            if token:
                run.execution_token = token.get("execution_token")
                run.capability_token = token
                db.commit()
                db.refresh(run)
            else:
                logger.warning(
                    "[AgentRuntime] Auto-approval capability preflight failed for run %s",
                    run.id,
                )
                run.status = "pending_approval"
                run.error_message = (
                    "Capability preflight failed for auto-approval; manual approval required."
                )
                db.commit()
                db.refresh(run)
                status = run.status

        logger.info(
            "[AgentRuntime] Run created: %s (risk=%s, status=%s)",
            run.id, overall_risk, status,
        )

        # Emit PLAN_CREATED lifecycle event
        auto_executed = status == "approved"
        record_agent_event(
            run_id=str(run.id),
            user_id=user_db_id,
            event_type="PLAN_CREATED",
            db=db,
            correlation_id=correlation_id,
            payload={
                "overall_risk": overall_risk,
                "steps_total": len(plan.get("steps", [])),
                "auto_executed": auto_executed,
                "goal_preview": goal[:120],
                "requires_approval": not auto_executed,
            },
            required=True,
        )

        return _run_to_dict(run)

    except Exception as exc:
        logger.warning("[AgentRuntime] create_run failed: %s", exc)
        emit_error_event(
            db=db,
            error_type="agent_create_run",
            message=str(exc),
            user_id=user_id,
            trace_id=get_trace_id(),
            parent_event_id=get_parent_event_id(),
            source="agent",
            payload={"goal_preview": goal[:120]},
            required=True,
        )
        return None


# ── Executor ─────────────────────────────────────────────────────────────────

def execute_run(run_id: str, user_id: str, db: Session) -> Optional[dict]:
    """
    Execute an approved AgentRun via the canonical Nodus runtime entrypoint.

    Requires run.status == "approved".
    Marks the run as "executing", then delegates entirely to the canonical
    runtime helper which currently uses flow-backed Nodus execution and handles:
      - Per-step retry (low/medium: 3x; high-risk: halt immediately)
      - AgentStep persistence after each step
      - AgentRun finalisation (completed / failed)
      - FlowRun checkpointing + FlowHistory → Memory Bridge capture

    Returns updated run dict or None on failure.
    Never raises.
    """
    try:
        from AINDY.db.models.agent_run import AgentRun
        from AINDY.runtime.nodus_execution_service import execute_agent_run_via_nodus
        user_db_id = _db_user_id(user_id)

        db_run_id = _db_run_id(run_id)
        run = db.query(AgentRun).filter(AgentRun.id == db_run_id).first()
        if not run:
            logger.warning("[AgentRuntime] Run %s not found", run_id)
            return None

        if run.status not in ("approved",):
            logger.warning(
                "[AgentRuntime] Run %s cannot execute — status=%s", run_id, run.status
            )
            return _run_to_dict(run)

        if not _user_matches(run.user_id, user_db_id):
            logger.warning("[AgentRuntime] Run %s owner mismatch", run_id)
            return None

        capability_token = getattr(run, "capability_token", None)
        if not isinstance(capability_token, dict):
            logger.warning(
                "[AgentRuntime] Run %s cannot execute without scoped capability token",
                run_id,
            )
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.error_message = "Missing scoped capability token."
            db.commit()
            record_agent_event(
                run_id=str(run.id),
                user_id=user_db_id,
                event_type="CAPABILITY_DENIED",
                db=db,
                correlation_id=getattr(run, "correlation_id", None),
                payload={"error": "missing scoped capability token"},
                required=True,
            )
            return _run_to_dict(run)

        register_or_update_agent(
            db,
            agent_id=LOCAL_AGENT_ID,
            capabilities=["manage_tasks", "read_memory", "write_memory", "external_api_call", "strategic_planning"],
            current_state={"run_id": str(run.id), "status": "executing"},
            load=min(1.0, max(0.1, (run.steps_total or 1) / 10.0)),
            health_status="healthy",
        )
        coordination = decide_execution_mode(
            db,
            local_agent_id=LOCAL_AGENT_ID,
            task={
                "name": run.goal,
                "description": run.executive_summary,
                "goal": run.goal,
                "required_capabilities": capability_token.get("allowed_capabilities", []),
            },
            user_id=str(user_db_id),
        )
        if coordination["mode"] in {"delegate", "collaborate"}:
            run.result = {
                "coordination_mode": coordination["mode"],
                "selected_agent": coordination["selected_agent"],
                "candidates": coordination["candidates"],
                "next_action": {
                    "type": coordination["mode"],
                    "selected_agent": coordination["selected_agent"],
                },
            }
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            record_agent_event(
                run_id=str(run.id),
                user_id=user_db_id,
                event_type="COMPLETED",
                db=db,
                correlation_id=getattr(run, "correlation_id", None),
                payload={"coordination": coordination},
                required=True,
            )
            return _run_to_dict(run)

        # Mark as executing
        if not getattr(run, "trace_id", None) and get_trace_id():
            run.trace_id = get_trace_id()
        run.status = "executing"
        run.started_at = datetime.now(timezone.utc)
        execution_memory_context = _build_execution_memory_context(
            goal=run.goal,
            plan=run.plan or {},
            user_id=user_db_id,
            trace_id=run.trace_id or get_trace_id() or getattr(run, "correlation_id", None),
            db=db,
        )
        execution_plan = dict(run.plan or {})
        execution_plan["memory_context"] = execution_memory_context
        run.plan = execution_plan
        db.commit()
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService

            _eu = ExecutionUnitService(db).get_by_source("agent_run", str(run.id))
            if _eu:
                ExecutionUnitService(db).update_status(_eu.id, "executing")
        except Exception:
            logger.debug("[EU] agent execute hook start skipped", exc_info=True)

        # Emit EXECUTION_STARTED lifecycle event
        execution_started_event_id = record_agent_event(
            run_id=str(run.id),
            user_id=user_db_id,
            event_type="EXECUTION_STARTED",
            db=db,
            correlation_id=getattr(run, "correlation_id", None),
            payload={},
            required=True,
        )

        # Delegate entirely to the deterministic adapter
        parent_token = set_parent_event_id(execution_started_event_id)
        try:
            execute_agent_run_via_nodus(
                run_id=str(run.id),
                plan=execution_plan,
                user_id=user_id,
                db=db,
                correlation_id=getattr(run, "correlation_id", None),
                execution_token=capability_token,
            )
        finally:
            reset_parent_event_id(parent_token)

        db.refresh(run)
        if run.status == "completed":
            result_payload = run.result if isinstance(run.result, dict) else {}
            if not result_payload.get("loop_enforced"):
                try:
                    from AINDY.domain.infinity_orchestrator import execute as execute_infinity_orchestrator

                    orchestration = execute_infinity_orchestrator(
                        user_id=user_db_id,
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
                except Exception as loop_exc:
                    logger.warning(
                        "[AgentRuntime] Agent completion orchestrator failed for %s: %s",
                        run_id,
                        loop_exc,
                    )
        logger.info(
            "[AgentRuntime] Run %s %s (%d/%d steps)",
            run_id, run.status, run.steps_completed, run.steps_total,
        )
        try:
            from AINDY.core.execution_unit_service import ExecutionUnitService

            _eu = ExecutionUnitService(db).get_by_source("agent_run", str(run.id))
            if _eu:
                final_status = "completed" if run.status == "completed" else "failed" if run.status == "failed" else None
                if final_status:
                    ExecutionUnitService(db).update_status(_eu.id, final_status)
        except Exception:
            logger.debug("[EU] agent execute hook finish skipped", exc_info=True)
        return _run_to_dict(run)

    except Exception as exc:
        logger.warning("[AgentRuntime] execute_run failed for %s: %s", run_id, exc)
        try:
            emit_error_event(
                db=db,
                error_type="agent_execution",
                message=str(exc),
                user_id=user_id,
                trace_id=get_trace_id(),
                parent_event_id=get_parent_event_id(),
                source="agent",
                payload={"run_id": run_id},
                required=True,
            )
        except Exception:
            logger.exception("[AgentRuntime] failed to emit required error event for %s", run_id)
        return None


def _build_execution_memory_context(
    *,
    goal: str,
    plan: dict,
    user_id: str,
    trace_id: str | None,
    db: Session,
) -> dict:
    try:
        from AINDY.db.dao.memory_node_dao import MemoryNodeDAO
        from AINDY.runtime.memory import MemoryOrchestrator, memory_items_to_dicts

        step_tools = [
            step.get("tool")
            for step in (plan or {}).get("steps", [])
            if isinstance(step, dict) and step.get("tool")
        ]
        orchestrator = MemoryOrchestrator(MemoryNodeDAO)
        context = orchestrator.get_context(
            user_id=user_id,
            query=goal or "agent execution",
            task_type="agent_execution",
            db=db,
            max_tokens=900,
            metadata={
                "tags": [tool.replace(".", "_") for tool in step_tools[:3]],
                "limit": 9,
                "trace_id": trace_id,
                "node_types": ["outcome", "insight", "decision"],
            },
        )
        items = memory_items_to_dicts(context.items)
        similar_past_outcomes = [item for item in items if item.get("memory_type") == "outcome"][:3]
        relevant_failures = [item for item in items if item.get("memory_type") == "failure"][:3]
        successful_patterns = [
            item
            for item in items
            if item.get("memory_type") in {"decision", "insight"}
            and (item.get("success_rate", 0.0) or 0.0) >= 0.5
        ][:3]
        return {
            "similar_past_outcomes": similar_past_outcomes,
            "relevant_failures": relevant_failures,
            "successful_patterns": successful_patterns,
            "trace_id": trace_id,
        }
    except Exception as exc:
        logger.warning("[AgentRuntime] execution memory context failed: %s", exc)
        return {
            "similar_past_outcomes": [],
            "relevant_failures": [],
            "successful_patterns": [],
            "trace_id": trace_id,
        }


# ── Approval / Rejection ─────────────────────────────────────────────────────

def approve_run(run_id: str, user_id: str, db: Session) -> Optional[dict]:
    """
    Approve a pending_approval run and execute it immediately.
    Returns the final run dict or None on failure.
    """
    try:
        from AINDY.db.models.agent_run import AgentRun
        user_db_id = _db_user_id(user_id)

        db_run_id = _db_run_id(run_id)
        run = db.query(AgentRun).filter(AgentRun.id == db_run_id).first()
        if not run or not _user_matches(run.user_id, user_db_id):
            return None

        if run.status != "pending_approval":
            return _run_to_dict(run)

        run.status = "approved"
        run.approved_at = datetime.now(timezone.utc)
        token = mint_token(
            run_id=str(run.id),
            user_id=user_db_id,
            plan=run.plan,
            db=db,
            approval_mode="manual",
            agent_type=getattr(run, "agent_type", "default"),
        )
        if not token:
            db.rollback()
            run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
            if run:
                run.error_message = "Capability preflight failed; run not approved."
                db.commit()
                db.refresh(run)
                return _run_to_dict(run)
            return None

        run.execution_token = token.get("execution_token")
        run.capability_token = token
        run.error_message = None
        db.commit()

        # Emit APPROVED lifecycle event
        record_agent_event(
            run_id=str(run.id),
            user_id=user_db_id,
            event_type="APPROVED",
            db=db,
            correlation_id=getattr(run, "correlation_id", None),
            payload={"auto_executed": False},
            required=True,
        )

        return execute_run(run_id=run.id, user_id=user_db_id, db=db)

    except Exception as exc:
        logger.warning("[AgentRuntime] approve_run failed for %s: %s", run_id, exc)
        emit_error_event(
            db=db,
            error_type="agent_approve_run",
            message=str(exc),
            user_id=user_id,
            trace_id=get_trace_id(),
            parent_event_id=get_parent_event_id(),
            source="agent",
            payload={"run_id": str(run_id)},
            required=True,
        )
        return None


def reject_run(run_id: str, user_id: str, db: Session) -> Optional[dict]:
    """Reject a pending_approval run. Returns updated run dict or None."""
    try:
        from AINDY.db.models.agent_run import AgentRun
        user_db_id = _db_user_id(user_id)

        db_run_id = _db_run_id(run_id)
        run = db.query(AgentRun).filter(AgentRun.id == db_run_id).first()
        if not run or not _user_matches(run.user_id, user_db_id):
            return None

        if run.status != "pending_approval":
            return _run_to_dict(run)

        run.status = "rejected"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

        # Emit REJECTED lifecycle event
        record_agent_event(
            run_id=str(run.id),
            user_id=user_db_id,
            event_type="REJECTED",
            db=db,
            correlation_id=getattr(run, "correlation_id", None),
            payload={},
            required=True,
        )

        return _run_to_dict(run)

    except Exception as exc:
        logger.warning("[AgentRuntime] reject_run failed for %s: %s", run_id, exc)
        emit_error_event(
            db=db,
            error_type="agent_reject_run",
            message=str(exc),
            user_id=user_id,
            trace_id=get_trace_id(),
            parent_event_id=get_parent_event_id(),
            source="agent",
            payload={"run_id": str(run_id)},
            required=True,
        )
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_to_dict(run) -> dict:
    from AINDY.core.execution_record_service import record_from_agent_run

    capability_token = getattr(run, "capability_token", None)
    if not isinstance(capability_token, dict):
        capability_token = {}
    agent_type = getattr(run, "agent_type", None)
    if not isinstance(agent_type, str) or not agent_type:
        agent_type = "default"
    execution_token = getattr(run, "execution_token", None)
    if not isinstance(execution_token, str):
        execution_token = None
    execution_record = record_from_agent_run(run)
    return {
        "run_id": str(run.id),
        "user_id": run.user_id,
        "agent_type": agent_type,
        "goal": run.goal,
        "executive_summary": run.executive_summary,
        "overall_risk": run.overall_risk,
        "status": run.status,
        "steps_total": run.steps_total,
        "steps_completed": run.steps_completed,
        "plan": run.plan,
        "result": run.result,
        "error_message": run.error_message,
        "flow_run_id": str(run.flow_run_id) if getattr(run, "flow_run_id", None) else None,
        "replayed_from_run_id": (
            str(run.replayed_from_run_id)
            if getattr(run, "replayed_from_run_id", None)
            else None
        ),
        "execution_token": execution_token,
        "granted_tools": capability_token.get("granted_tools", []),
        "allowed_capabilities": capability_token.get("allowed_capabilities", []),
        "correlation_id": getattr(run, "correlation_id", None),
        "trace_id": getattr(run, "trace_id", None),
        "execution_record": execution_record,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "approved_at": run.approved_at.isoformat() if run.approved_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


def _normalize_agent_events(timeline: Optional[dict]) -> list[dict]:
    if not timeline or not isinstance(timeline.get("events"), list):
        return []
    return [
        {
            "type": "agent.event",
            "event_type": event.get("event_type"),
            "timestamp": event.get("occurred_at"),
            "payload": event.get("payload", {}),
        }
        for event in timeline["events"]
    ]


def to_execution_response(run: dict, db: Session) -> dict:
    run_id = run.get("run_id")
    user_id = run.get("user_id")
    timeline = get_run_events(run_id=run_id, user_id=user_id, db=db) if run_id and user_id else None

    result_payload = run.get("result")
    if result_payload is None:
        result_payload = {
            "goal": run.get("goal"),
            "plan": run.get("plan"),
            "overall_risk": run.get("overall_risk"),
        }

    next_action = None
    if isinstance(result_payload, dict):
        next_action = result_payload.get("next_action")

    return {
        "status": str(run.get("status", "unknown")).upper(),
        "result": result_payload,
        "events": _normalize_agent_events(timeline),
        "next_action": next_action,
        "trace_id": run.get("trace_id") or run.get("correlation_id") or run_id,
        "execution_record": run.get("execution_record"),
    }


# ── Replay ────────────────────────────────────────────────────────────────────

def _create_run_from_plan(
    goal: str,
    plan: dict,
    user_id: str,
    db: Session,
    replayed_from_run_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Persist a new AgentRun from an existing plan dict (skips GPT-4o).

    Trust gate is re-applied — prior approval does not carry forward.
    Returns the new run dict or None on failure.
    Never raises.
    """
    try:
        from AINDY.db.models.agent_run import AgentRun

        overall_risk = plan.get("overall_risk", "high")
        needs_approval = _requires_approval(overall_risk, user_id, db)
        status = "pending_approval" if needs_approval else "approved"

        # Generate correlation token — propagated through all child records
        correlation_id = f"run_{uuid.uuid4()}"

        run = AgentRun(
            user_id=user_id,
            agent_type="default",
            trace_id=get_trace_id(),
            goal=goal,
            plan=plan,
            executive_summary=plan.get("executive_summary", ""),
            overall_risk=overall_risk,
            status=status,
            steps_total=len(plan.get("steps", [])),
            replayed_from_run_id=replayed_from_run_id,
            correlation_id=correlation_id,
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        if status == "approved":
            token = mint_token(
                run_id=str(run.id),
                user_id=user_id,
                plan=plan,
                db=db,
                approval_mode="auto",
                agent_type=getattr(run, "agent_type", "default"),
            )
            if token:
                run.execution_token = token.get("execution_token")
                run.capability_token = token
                db.commit()
                db.refresh(run)
            else:
                run.status = "pending_approval"
                run.error_message = (
                    "Capability preflight failed for auto-approval; manual approval required."
                )
                db.commit()
                db.refresh(run)

        logger.info(
            "[AgentRuntime] Replay run created: %s (origin=%s, risk=%s, status=%s)",
            run.id,
            replayed_from_run_id,
            overall_risk,
            status,
        )

        return _run_to_dict(run)

    except Exception as exc:
        logger.warning("[AgentRuntime] _create_run_from_plan failed: %s", exc)
        return None


def replay_run(
    run_id: str,
    user_id: str,
    db: Session,
    mode: str = "same_plan",
) -> Optional[dict]:
    """
    Create a new AgentRun by replaying an existing run's plan (Sprint N+7).

    Only ``mode="same_plan"`` is supported this sprint — the original plan
    is re-used verbatim without re-calling GPT-4o.

    Trust gate is re-applied on the new run; prior approval does not carry
    forward.

    Returns:
      dict  — new run dict on success
      None  — original run not found or user mismatch

    Never raises.
    """
    try:
        from AINDY.db.models.agent_run import AgentRun

        db_run_id = _db_run_id(run_id)
        original = db.query(AgentRun).filter(AgentRun.id == db_run_id).first()
        if not original:
            logger.warning("[AgentRuntime] replay_run: run %s not found", run_id)
            return None

        if not _user_matches(original.user_id, user_id):
            logger.warning("[AgentRuntime] replay_run: owner mismatch for %s", run_id)
            return None

        if mode == "new_plan":
            fresh_plan = generate_plan(goal=original.goal, user_id=user_id, db=db)
            if not fresh_plan:
                logger.warning(
                    "[AgentRuntime] replay_run new_plan: plan generation failed for %s",
                    run_id,
                )
                return None
            plan = fresh_plan
        else:
            plan = original.plan or {}

        new_run = _create_run_from_plan(
            goal=original.goal,
            plan=plan,
            user_id=user_id,
            db=db,
            replayed_from_run_id=str(original.id),
        )

        # Emit REPLAY_CREATED lifecycle event on the new run
        if new_run:
            record_agent_event(
                run_id=new_run["run_id"],
                user_id=user_id,
                event_type="REPLAY_CREATED",
                db=db,
                correlation_id=new_run.get("correlation_id"),
                payload={
                    "original_run_id": str(original.id),
                    "mode": mode,
                },
                required=True,
            )

        return new_run

    except Exception as exc:
        logger.warning("[AgentRuntime] replay_run failed for %s: %s", run_id, exc)
        emit_error_event(
            db=db,
            error_type="agent_replay_run",
            message=str(exc),
            user_id=user_id,
            trace_id=get_trace_id(),
            parent_event_id=get_parent_event_id(),
            source="agent",
            payload={"run_id": str(run_id), "mode": mode},
            required=True,
        )
        return None


# ── Event timeline ────────────────────────────────────────────────────────────

def get_run_events(run_id: str, user_id: str, db: Session) -> Optional[dict]:
    """
    Return a unified event timeline for a single agent run (Sprint N+8).

    Merges:
      - AgentEvent rows (lifecycle events: PLAN_CREATED, APPROVED, etc.)
      - AgentStep rows (synthesised as STEP_EXECUTED / STEP_FAILED events)

    Both lists are sorted by occurred_at ASC to produce a single chronological
    timeline. AgentStep.executed_at=None falls back to created_at.

    Returns:
      {
        "run_id": str,
        "correlation_id": str | None,
        "events": [ {id, event_type, occurred_at, payload}, ... ]
      }
      OR None if run not found / ownership mismatch.

    Never raises.
    """
    try:
        from AINDY.db.models.agent_run import AgentRun, AgentStep
        from AINDY.db.models.agent_event import AgentEvent

        db_run_id = _db_run_id(run_id)
        run = db.query(AgentRun).filter(AgentRun.id == db_run_id).first()
        if not run:
            return None
        if not _user_matches(run.user_id, user_id):
            return None

        # ── Lifecycle events from agent_events ────────────────────────────
        lifecycle_rows = (
            db.query(AgentEvent)
            .filter(AgentEvent.run_id == run.id)
            .order_by(AgentEvent.occurred_at.asc())
            .all()
        )
        lifecycle_events = [
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                "payload": row.payload or {},
            }
            for row in lifecycle_rows
        ]

        # ── Step events synthesised from agent_steps ──────────────────────
        step_rows = (
            db.query(AgentStep)
            .filter(AgentStep.run_id == run.id)
            .order_by(AgentStep.step_index.asc())
            .all()
        )
        step_events = []
        for step in step_rows:
            ts = step.executed_at or step.created_at
            step_events.append(
                {
                    "id": str(step.id),
                    "event_type": "STEP_EXECUTED" if step.status == "success" else "STEP_FAILED",
                    "occurred_at": ts.isoformat() if ts else None,
                    "payload": {
                        "step_index": step.step_index,
                        "tool_name": step.tool_name,
                        "risk_level": step.risk_level,
                        "description": step.description,
                        "status": step.status,
                        "execution_ms": step.execution_ms,
                        "error_message": step.error_message,
                    },
                }
            )

        # ── Merge and sort by occurred_at ──────────────────────────────────
        all_events = lifecycle_events + step_events
        all_events.sort(
            key=lambda e: e["occurred_at"] or "0000",
        )

        return {
            "run_id": str(run.id),
            "correlation_id": getattr(run, "correlation_id", None),
            "events": all_events,
        }

    except Exception as exc:
        logger.warning("[AgentRuntime] get_run_events failed for %s: %s", run_id, exc)
        return None


