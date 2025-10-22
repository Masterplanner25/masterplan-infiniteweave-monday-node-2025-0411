import requests, openai
from datetime import datetime
from sqlalchemy.orm import Session
from db import models

def web_search(query: str) -> str:
    """External web or API search."""
    url = f"https://api.perplexity.ai/search?q={query}"
    resp = requests.get(url)
    return resp.text[:5000]  # limit content size

def ai_analyze(content: str) -> str:
    """Summarize and extract next actions."""
    prompt = f"Summarize and extract 3 recommended actions:\n\n{content}"
    completion = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role":"user","content":prompt}]
    )
    return completion.choices[0].message["content"]

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
