import requests
from AINDY.platform_layer.openai_client import get_openai_client
from datetime import datetime
from sqlalchemy.orm import Session
from AINDY.db import models
from AINDY.platform_layer.external_call_service import perform_external_call

def web_search(query: str) -> str:
    """External web or API search."""
    url = f"https://api.perplexity.ai/search?q={query}"
    resp = perform_external_call(
        service_name="http",
        endpoint=url,
        method="GET",
        extra={"purpose": "research_web_search", "provider": "perplexity"},
        operation=lambda: requests.get(url),
    )
    return resp.text[:5000]  # limit content size

def ai_analyze(content: str) -> str:
    """Summarize and extract next actions."""
    prompt = f"Summarize and extract 3 recommended actions:\n\n{content}"
    completion = perform_external_call(
        service_name="openai",
        endpoint="chat.completions.create",
        model="gpt-4o",
        method="openai.chat",
        extra={"purpose": "research_ai_analyze"},
        operation=lambda: get_openai_client().chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"user","content":prompt}]
        ),
    )
    return completion.choices[0].message.content

def save_result(db: Session, query, summary, source):
    record = models.ResearchResult(
        query=query,
        summary=summary,
        source=source,
        created_at=datetime.utcnow()
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record

