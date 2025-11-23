"""
LEAD GENERATION SERVICE
------------------------------------
Module: B2B Lead Generation via AI Search Optimization
Purpose: Executes AI Search queries, evaluates leads with Infinity Algorithm logic,
and logs symbolic results into the A.I.N.D.Y. Memory Bridge.
"""

import json
from datetime import datetime
from sqlalchemy.orm import Session
from openai import OpenAI

from bridge.bridge import create_memory_node
from db.models.leadgen_model import LeadGenResult
from dotenv import load_dotenv
import os
load_dotenv()

# Initialize the OpenAI client (ensure API key is set in environment)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# --------------------------------------------------------
# 🧩 CORE FUNCTIONS
# --------------------------------------------------------

def run_ai_search(query: str):
    """
    Executes an AI-optimized search query.
    This is a placeholder function for the web_search logic.
    In production, integrate with A.I.N.D.Y.’s Codex or API-based web agent.
    """
    print(f"[LeadGen] Running AI search for query: {query}")

    # Example mocked results – replace with live search results later
    example_results = [
        {
            "company": "Acme AI Solutions",
            "url": "https://acmeai.com",
            "context": "Acme AI is hiring ML engineers and seeking automation partners."
        },
        {
            "company": "Finovate Labs",
            "url": "https://finovatelabs.io",
            "context": "Finovate is implementing AI-driven fintech automation tools."
        },
        {
            "company": "HealthEdge Analytics",
            "url": "https://healthedge.ai",
            "context": "HealthEdge announced plans to adopt AI workflow automation."
        }
    ]
    return example_results


def score_lead(lead_data: dict):
    """
    Uses GPT-4o to generate structured lead quality scores with fallback parsing.
    """
    system_prompt = """
You are LeadQualificationAnalyst, an expert B2B analyst who scores potential leads for AI consulting services.
Return ONLY a valid JSON object with these exact keys:
fit_score, intent_score, data_quality_score, overall_score, reasoning.
Each score must be a number between 0 and 100.
"""

    lead_summary = f"Company: {lead_data['company']}\nURL: {lead_data['url']}\nContext: {lead_data['context']}"
    print(f"[LeadGen] Scoring lead: {lead_data['company']}")

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            input=f"{system_prompt}\n\n{lead_summary}"
        )

        # Depending on SDK version, output may differ:
        text_output = (
            completion.choices[0].message.content
            if hasattr(completion, "output") and completion.output
            else completion.choices[0].message.content
        ).strip()

        # Extract JSON from messy output if needed
        if not text_output.startswith("{"):
            import re
            json_match = re.search(r"\{.*\}", text_output, re.DOTALL)
            if json_match:
                text_output = json_match.group(0)

        result = json.loads(text_output)
        return result

    except Exception as e:
        print(f"[LeadGen] Scoring failed for {lead_data['company']}: {e}")
        return {
            "fit_score": 0,
            "intent_score": 0,
            "data_quality_score": 0,
            "overall_score": 0,
            "reasoning": f"Parsing or API error: {e}"
        }

    # Combine context into a single lead summary
    lead_summary = f"Company: {lead_data['company']}\nURL: {lead_data['url']}\nContext: {lead_data['context']}"
    print(f"[LeadGen] Scoring lead: {lead_data['company']}")

    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            input=f"{system_prompt}\n\n{lead_summary}"
        )

        # The model should return a JSON block
        response_text = completion.choices[0].message.content.strip()
        result = json.loads(response_text)
        return result

    except Exception as e:
        print(f"[LeadGen] Scoring failed for {lead_data['company']}: {e}")
        return {
            "fit_score": 0,
            "intent_score": 0,
            "data_quality_score": 0,
            "overall_score": 0,
            "reasoning": f"Error: {e}"
        }


def create_lead_results(db: Session, query: str):
    """
    Runs the full pipeline:
    1. Perform AI Search
    2. Score each lead
    3. Store results in database
    4. Log symbolic traces into Memory Bridge
    """
    results = []
    leads = run_ai_search(query)
    print(f"[LeadGen] Found {len(leads)} potential leads")

    for lead in leads:
        score = score_lead(lead)

        db_entry = LeadGenResult(
            query=query,
            company=lead["company"],
            url=lead["url"],
            context=lead["context"],
            fit_score=score["fit_score"],
            intent_score=score["intent_score"],
            data_quality_score=score["data_quality_score"],
            overall_score=score["overall_score"],
            reasoning=score["reasoning"],
            created_at=datetime.utcnow()
        )

        db.add(db_entry)
        db.commit()
        db.refresh(db_entry)

        # 🧠 Log symbolic memory node
        create_memory_node(
            title=f"Lead Discovered: {lead['company']}",
            content=f"{lead['context']} | Score: {score['overall_score']}",
            tags=["leadgen", "aindy", "infinity", "ai-search"]
        )

        print(f"[LeadGen] Logged {lead['company']} ({score['overall_score']})")
        results.append(db_entry)

    return results
