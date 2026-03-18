import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
            from bridge import recall_memories
            past_memories = recall_memories(
                db=db,
                query=message,
                tags=["genesis", "masterplan", "decision"],
                user_id=user_id,
                limit=2,
            )
            if past_memories:
                prior_context = (
                    "\n\nRelevant past strategic context from this user:\n"
                    + "\n".join(f"- {m['content'][:200]}" for m in past_memories)
                )
        except Exception as e:
            logging.warning(f"Genesis memory recall failed: {e}")

    # Step 2: Build prompt with injected memory context
    system_content = GENESIS_SYSTEM_PROMPT + prior_context

    response = client.chat.completions.create(
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
            from db.dao.memory_node_dao import MemoryNodeDAO
            dao = MemoryNodeDAO(db)

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

            dao.save(
                content=memory_content,
                source="genesis_conversation",
                tags=[
                    "genesis", "conversation", "insight",
                    "synthesis_ready" if llm_output.get("synthesis_ready") else "in_progress",
                ],
                user_id=user_id,
                node_type="insight",
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


def call_genesis_synthesis_llm(current_state: dict) -> dict:
    """Real GPT-4o synthesis call. Replaces the stub from initial implementation."""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
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


def validate_draft_integrity(draft: dict) -> dict:
    """
    GPT-4o strategic integrity audit for a synthesis draft.
    Returns audit result dict with findings, audit_passed, overall_confidence.
    Retries up to 3 times on JSON parse failure.
    """
    retry_limit = 3
    last_error = None

    for attempt in range(retry_limit):
        try:
            response = client.chat.completions.create(
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