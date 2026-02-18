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


def call_genesis_synthesis_llm(current_state: dict) -> dict:

    # Minimal stub for now
    return {
        "vision_statement": current_state.get("vision_summary", ""),
        "time_horizon_years": current_state.get("time_horizon", 5),
        "primary_mechanism": current_state.get("mechanism_summary", ""),
        "core_domains": [
            {"name": d, "intent": ""}
            for d in current_state.get("inferred_domains", [])
        ],
        "phases": [
            {"name": p, "description": ""}
            for p in current_state.get("inferred_phases", [])
        ],
        "key_assets": current_state.get("assets_summary", []),
        "confidence_at_synthesis": current_state.get("confidence", 0.0)
    }