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


def call_genesis_llm(user_message: str, current_state: dict):

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": GENESIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"""
Current Structured State:
{json.dumps(current_state)}

New User Message:
{user_message}

Update the structured state incrementally.
Return only valid JSON.
"""
            }
        ],
        temperature=0.4,
    )

    content = response.choices[0].message.content

    try:
        return json.loads(content)
    except Exception:
        # Fail-safe fallback
        return {
            "reply": "I need a bit more clarity. Can you elaborate?",
            "state_update": {},
            "synthesis_ready": False
        }


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