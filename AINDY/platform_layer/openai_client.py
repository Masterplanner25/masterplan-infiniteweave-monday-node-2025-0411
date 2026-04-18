from __future__ import annotations

from typing import Optional

from openai import OpenAI


_client: Optional[OpenAI] = None


def get_openai_client() -> OpenAI:
    """Lazily create and cache the OpenAI client using the configured API key."""
    global _client
    if _client is None:
        from AINDY.config import settings

        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client
