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
  "confidence_at_synthesis": 0.0
}

Rules:
- ambition_score is a float 0.0–1.0 representing how ambitious/aggressive the plan is.
- time_horizon_years must be a number.
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