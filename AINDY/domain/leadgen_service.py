"""
LEAD GENERATION SERVICE
------------------------------------
Module: B2B Lead Generation via AI Search Optimization
Purpose: Executes AI Search queries, evaluates leads with Infinity Algorithm logic,
and logs symbolic results into the A.I.N.D.Y. Memory Bridge.
"""

import uuid
import logging
import json
import re

from core.execution_signal_helper import queue_memory_capture
from analytics.search_scoring import score_lead_result
from datetime import datetime
from sqlalchemy.orm import Session
from openai import OpenAI

from memory.bridge import create_memory_node
from db.models.leadgen_model import LeadGenResult
from platform_layer.external_call_service import perform_external_call
from domain.search_service import search_leads
from utils.trace_context import is_pipeline_active
import os

# Initialize the OpenAI client (ensure API key is set in environment)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger(__name__)


# --------------------------------------------------------
# 🧩 CORE FUNCTIONS
# --------------------------------------------------------

def run_ai_search(query: str, user_id: str = None, db=None):
    """
    Executes an AI-optimized search query.
    This is a placeholder function for the web_search logic.
    In production, integrate with A.I.N.D.Y.’s Codex or API-based web agent.

    Recalls past leadgen searches before querying and writes an outcome
    memory node after results are returned.
    """
    import logging
    logger.info("[LeadGen] Running AI search for query: %s", query)

    # Step 1: Recall relevant past leadgen searches
    if user_id and db and not is_pipeline_active():
        try:
            from db.dao.memory_node_dao import MemoryNodeDAO
            from runtime.memory import MemoryOrchestrator

            orchestrator = MemoryOrchestrator(MemoryNodeDAO)
            context = orchestrator.get_context(
                user_id=user_id,
                query=query,
                task_type="strategy",
                db=db,
                max_tokens=500,
                metadata={
                    "tags": ["leadgen", "search", "outcome"],
                    "node_type": "outcome",
                    "limit": 2,
                },
            )
            if context.items:
                logger.info(
                    "[LeadGen] Recalled %s past searches for context.",
                    len(context.items),
                )
        except Exception as e:
            logger.warning("LeadGen memory recall failed: %s", e)

    # Step 2: External retrieval (best-effort)
    example_results = []
    try:
        payload = search_leads(query, db=db, user_id=user_id, max_results=3)
        example_results = payload.get("results") or []
    except Exception as e:
        logger.warning("[LeadGen] External search failed, using fallback: %s", e)

    # Fallback mocked results if external search fails
    if not example_results:
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

    # Step 3: Write outcome memory node after results are gathered.
    # MemoryCaptureEngine-backed queue_memory_capture persists the search outcome.
    if user_id and db and not is_pipeline_active():
        try:
            result_count = len(example_results)
            top = example_results[0]["company"] if example_results else "none"
            memory_content = (
                f"LeadGen search: ‘{query[:100]}’. "
                f"Found {result_count} leads. "
                f"Top result: {top}"
            )
            queue_memory_capture(
                db=db,
                user_id=user_id,
                agent_namespace="leadgen",
                event_type="leadgen_search",
                content=memory_content,
                source="leadgen_search",
                tags=["leadgen", "search", "outcome", f"leads_{result_count}"],
                node_type="outcome",
            )
        except Exception as e:
            logging.warning(f"LeadGen memory write failed: {e}")

    return example_results


def _extract_leads_from_text(text: str, max_results: int = 3) -> list[dict]:
    urls = re.findall(r"https?://[^\s,;]+", text)
    leads = []
    for url in urls[:max_results]:
        leads.append(
            {
                "company": url.replace("https://", "").split("/")[0],
                "url": url,
                "context": f"Found via text search: {text[:100]}",
            }
        )
    return leads


def _extract_leads_from_response(payload: dict, max_results: int = 3) -> list[dict]:
    results = payload.get("results", []) if payload else []
    leads = []
    for entry in results[:max_results]:
        leads.append(
            {
                "company": entry.get("title") or entry.get("company", ""),
                "url": entry.get("url") or entry.get("href"),
                "context": entry.get("snippet") or entry.get("description") or "",
            }
        )
    return leads


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
    logger.info("[LeadGen] Scoring lead: %s", lead_data["company"])

    try:
        completion = perform_external_call(
            service_name="openai",
            endpoint="chat.completions.create",
            model="gpt-4o-mini",
            method="openai.chat",
            extra={"purpose": "lead_scoring", "company": lead_data["company"]},
            operation=lambda: client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": lead_summary},
                ],
            ),
        )

        text_output = (completion.choices[0].message.content or "").strip()

        # Extract JSON from messy output if needed
        if not text_output.startswith("{"):
            import re
            json_match = re.search(r"\{.*\}", text_output, re.DOTALL)
            if json_match:
                text_output = json_match.group(0)

        result = json.loads(text_output)
        return result

    except Exception as e:
        logger.warning("[LeadGen] Scoring failed for %s: %s", lead_data["company"], e)
        return {
            "fit_score": 0,
            "intent_score": 0,
            "data_quality_score": 0,
            "overall_score": 0,
            "reasoning": f"Parsing or API error: {e}"
        }



def create_lead_results(db: Session, query: str, user_id: str = None):
    """
    Runs the full pipeline:
    1. Perform AI Search (with memory recall + write)
    2. Score each lead
    3. Store results in database
    4. Log symbolic traces into Memory Bridge
    """
    if not user_id:
        raise ValueError("user_id is required to create lead results")
    results = []
    leads = run_ai_search(query, user_id=user_id, db=db)
    logger.info("[LeadGen] Found %s potential leads", len(leads))

    for lead in leads:
        score = score_lead(lead)
        search_score = score_lead_result(
            overall_score=score.get("overall_score"),
            fit_score=score.get("fit_score"),
            intent_score=score.get("intent_score"),
            data_quality_score=score.get("data_quality_score"),
        )

        db_entry = LeadGenResult(
            query=query,
            user_id=uuid.UUID(str(user_id)) if user_id else None,
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
        if not is_pipeline_active():
            create_memory_node(
                content=f"Lead Discovered: {lead['company']} | {lead['context']} | Score: {score['overall_score']}",
                source="leadgen",
                tags=["leadgen", "aindy", "infinity", "ai-search"],
                db=db,
                user_id=user_id,
            )

        logger.info("[LeadGen] Logged %s (%s)", lead["company"], score["overall_score"])
        results.append((db_entry, search_score))

    results.sort(key=lambda item: item[1], reverse=True)
    return results



