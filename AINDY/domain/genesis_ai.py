import os
import json
import logging
from core.execution_signal_helper import queue_memory_capture
from openai import OpenAI
from platform_layer.external_call_service import perform_external_call
from core.observability_events import emit_observability_event

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"  # efficient + structured

GENESIS_SYSTEM_PROMPT = """
You are A.I.N.D.Y., a calm and reflective strategic partner helping a user define a long-term MasterPlan.

Rules:
- Responses must be 2–4 lines maximum.
- Tone must be calm and minimal.
- No hype language.
- No emojis.
- Ask clarifying questions when mechanism logic is missing.
- Extract structured signals from user input.

You MUST return valid JSON in this exact format:

{
  "reply": "...",
  "state_update": {
    "vision_summary": null,
    "time_horizon": null,
    "mechanism_summary": null,
    "assets_summary": null,
    "inferred_domains": [],
    "inferred_phases": [],
    "confidence": 0.0
  },
  "synthesis_ready": false
}
"""


def call_genesis_llm(message: str, current_state: dict, user_id: str = None, db=None):
    import logging

    # Step 1: Recall relevant past strategic memories before responding
    prior_context = ""
    if user_id and db:
        try:
            from db.dao.memory_node_dao import MemoryNodeDAO
            from runtime.memory import MemoryOrchestrator

            orchestrator = MemoryOrchestrator(MemoryNodeDAO)
            context = orchestrator.get_context(
                user_id=user_id,
                query=message,
                task_type="strategy",
                db=db,
                max_tokens=600,
                metadata={
                    "tags": ["genesis", "masterplan", "decision"],
                    "limit": 2,
                },
            )
            if context.items:
                prior_context = (
                    "\n\nRelevant past strategic context from this user:\n"
                    + "\n".join(f"- {m.content[:200]}" for m in context.items)
                )
        except Exception as e:
            logging.warning(f"Genesis memory recall failed: {e}")

    # Step 1b: Federated recall - ask ARM what it has learned
    arm_context = ""
    try:
        if user_id and db:
            from db.dao.memory_node_dao import MemoryNodeDAO
            fed_dao = MemoryNodeDAO(db)
            arm_memories = fed_dao.recall_from_agent(
                agent_namespace="arm",
                query=message,
                tags=["insight", "analysis"],
                limit=2,
                user_id=user_id,
                include_private=False,
            )
            if arm_memories:
                arm_context = (
                    "\n\nRelevant ARM analysis insights "
                    "(from code reasoning engine):\n"
                    + "\n".join(
                        f"- {m['content'][:150]}"
                        for m in arm_memories
                    )
                )
    except Exception as exc:
        emit_observability_event(
            logger=logger,
            event="genesis_llm_arm_context_lookup_failed",
            user_id=user_id,
            error=str(exc),
        )

    # Step 2: Build prompt with injected memory + identity context
    identity_context = ""
    try:
        if user_id and db:
            from domain.identity_service import IdentityService
            id_service = IdentityService(db=db, user_id=user_id)
            identity_context = id_service.get_context_for_prompt()
    except Exception as exc:
        emit_observability_event(
            logger=logger,
            event="genesis_llm_identity_context_failed",
            user_id=user_id,
            error=str(exc),
        )

    system_content = (
        GENESIS_SYSTEM_PROMPT + prior_context + arm_context + identity_context
    )
    response = perform_external_call(
        service_name="openai",
        db=db,
        user_id=user_id,
        endpoint="chat.completions.create",
        model=MODEL,
        method="openai.chat",
        extra={"purpose": "genesis_message"},
        operation=lambda: client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_content},
                {
                    "role": "user",
                    "content": f"""
Current Structured State:
{json.dumps(current_state)}

New User Message:
{message}

Update the structured state incrementally.
Return only valid JSON.
"""
                }
            ],
            temperature=0.4,
        ),
    )

    content = response.choices[0].message.content

    try:
        llm_output = json.loads(content)
    except Exception:
        # Fail-safe fallback
        llm_output = {
            "reply": "I need a bit more clarity. Can you elaborate?",
            "state_update": {},
            "synthesis_ready": False,
        }

    # Step 3: Write memory node after successful LLM call
    if user_id and db:
        try:
            state_signals = []
            if current_state.get("vision_summary"):
                state_signals.append(f"vision: {current_state['vision_summary'][:100]}")
            if current_state.get("mechanism_summary"):
                state_signals.append(f"mechanism: {current_state['mechanism_summary'][:100]}")

            memory_content = (
                f"Genesis conversation: user said '{message[:100]}'. "
                f"Current signals: {'; '.join(state_signals) or 'gathering'}. "
                f"Synthesis ready: {llm_output.get('synthesis_ready', False)}"
            )

            queue_memory_capture(
                db=db,
                user_id=user_id,
                agent_namespace="genesis",
                event_type="genesis_message",
                content=memory_content,
                source="genesis_conversation",
                tags=[
                    "genesis",
                    "conversation",
                    "insight",
                    "synthesis_ready" if llm_output.get("synthesis_ready") else "in_progress",
                ],
                node_type="insight",
                context={"significance": current_state.get("confidence", 0.5)},
            )
        except Exception as e:
            logging.warning(f"Genesis conversation memory write failed: {e}")

    return llm_output


SYNTHESIS_SYSTEM_PROMPT = """
You are A.I.N.D.Y., a strategic synthesis engine. Given a structured session state, produce a
complete, actionable MasterPlan draft.

You MUST return valid JSON in this exact format:

{
  "vision_statement": "...",
  "time_horizon_years": 5,
  "primary_mechanism": "...",
  "ambition_score": 0.7,
  "core_domains": [{"name": "...", "intent": "..."}],
  "phases": [{"name": "...", "description": "...", "duration_months": 12}],
  "key_assets": ["..."],
  "success_criteria": ["..."],
  "risk_factors": ["..."],
  "confidence_at_synthesis": 0.0,
  "synthesis_notes": "Brief meta-commentary on the synthesis process and confidence level"
}

Rules:
- ambition_score is a float 0.0–1.0 representing how ambitious/aggressive the plan is.
- time_horizon_years must be a number.
- synthesis_notes should summarize what the AI was confident about and what was inferred.
- Return ONLY the JSON object. No explanation text.
"""


def call_genesis_synthesis_llm(
    current_state: dict,
    user_id: str = None,
    db=None,
) -> dict:
    """Real GPT-4o synthesis call. Replaces the stub from initial implementation."""
    arm_insights = ""
    try:
        if user_id and db:
            from db.dao.memory_node_dao import MemoryNodeDAO
            fed_dao = MemoryNodeDAO(db)
            arm_memories = fed_dao.recall_from_agent(
                agent_namespace="arm",
                query=str(current_state),
                tags=["insight"],
                limit=3,
                user_id=user_id,
                include_private=False,
            )
            if arm_memories:
                arm_insights = (
                    "\n\nTechnical insights from ARM "
                    "(code analysis engine):\n"
                    + "\n".join(
                        f"- {m['content'][:200]}"
                        for m in arm_memories
                    )
                )
    except Exception as exc:
        emit_observability_event(
            logger=logger,
            event="genesis_synthesis_arm_context_lookup_failed",
            user_id=user_id,
            error=str(exc),
        )

    system_prompt = SYNTHESIS_SYSTEM_PROMPT + arm_insights
    response = perform_external_call(
        service_name="openai",
        db=db,
        user_id=user_id,
        endpoint="chat.completions.create",
        model="gpt-4o",
        method="openai.chat",
        extra={"purpose": "genesis_synthesis"},
        operation=lambda: client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"""
Session State:
{json.dumps(current_state, indent=2)}

Synthesize this into a complete MasterPlan draft.
Return only valid JSON.
"""
                }
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        ),
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except Exception:
        # Fail-safe: return minimal valid structure
        return {
            "vision_statement": current_state.get("vision_summary", ""),
            "time_horizon_years": current_state.get("time_horizon", 5),
            "primary_mechanism": current_state.get("mechanism_summary", ""),
            "ambition_score": 0.5,
            "core_domains": [
                {"name": d, "intent": ""}
                for d in current_state.get("inferred_domains", [])
            ],
            "phases": [
                {"name": p, "description": "", "duration_months": 12}
                for p in current_state.get("inferred_phases", [])
            ],
            "key_assets": current_state.get("assets_summary", []) or [],
            "success_criteria": [],
            "risk_factors": [],
            "confidence_at_synthesis": current_state.get("confidence", 0.0)
        }


AUDIT_SYSTEM_PROMPT = """
You are the Strategic Integrity Validator of A.I.N.D.Y. — a senior strategic advisor reviewing a
MasterPlan draft before it is locked.

Your job: identify structural flaws, gaps, contradictions, or risks in the draft.

You MUST return valid JSON in this exact format:

{
  "audit_passed": true,
  "findings": [
    {
      "type": "mechanism_gap | contradiction | timeline_risk | asset_gap | confidence_concern",
      "severity": "critical | warning | advisory",
      "description": "...",
      "recommendation": "..."
    }
  ],
  "overall_confidence": 0.0,
  "audit_summary": "One sentence summary of audit result."
}

Rules:
- audit_passed is true only if there are zero critical findings.
- overall_confidence is a float 0.0–1.0.
- findings may be an empty list if the draft is clean.
- Return ONLY the JSON object. No explanation text.
"""


def validate_draft_integrity(draft: dict, user_id: str = None, db=None) -> dict:
    """
    GPT-4o strategic integrity audit for a synthesis draft.
    Returns audit result dict with findings, audit_passed, overall_confidence.
    Retries up to 3 times on JSON parse failure.
    """
    retry_limit = 3
    last_error = None

    for attempt in range(retry_limit):
        try:
            response = perform_external_call(
                service_name="openai",
                db=db,
                user_id=user_id,
                endpoint="chat.completions.create",
                model="gpt-4o",
                method="openai.chat",
                extra={"purpose": "genesis_draft_audit", "attempt": attempt + 1},
                operation=lambda: client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"""
MasterPlan Draft:
{json.dumps(draft, indent=2)}

Audit this draft for structural integrity.
Return only valid JSON.
"""
                        }
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                ),
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            last_error = e
            continue

    # Fail-safe after all retries exhausted
    return {
        "audit_passed": False,
        "findings": [
            {
                "type": "confidence_concern",
                "severity": "warning",
                "description": f"Audit service error after {retry_limit} attempts: {str(last_error)}",
                "recommendation": "Retry the audit or proceed with caution."
            }
        ],
        "overall_confidence": 0.0,
        "audit_summary": "Audit could not be completed due to a service error."
    }



