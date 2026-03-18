"""
Embedding Service

Generates vector embeddings via OpenAI text-embedding-ada-002.
Uses C++ kernel for cosine similarity when available.
Falls back to pure Python.
"""
import logging
import os
import sys
import time
from typing import Optional

from openai import OpenAI

from config import settings

EMBEDDING_MODEL = "text-embedding-ada-002"
EMBEDDING_DIMENSIONS = 1536

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def generate_embedding(text: str) -> list:
    """
    Generate 1536-dim embedding for text.
    Returns zero vector on failure — never crashes.
    """
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIMENSIONS

    text = text[:32000]
    client = get_client()

    for attempt in range(3):
        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text
            )
            embedding = response.data[0].embedding
            assert len(embedding) == EMBEDDING_DIMENSIONS
            return embedding
        except Exception as e:
            if attempt == 2:
                logging.warning(
                    f"Embedding failed after 3 attempts: {e}. "
                    f"Saving node without embedding."
                )
                return [0.0] * EMBEDDING_DIMENSIONS
            time.sleep(2 ** attempt)

    return [0.0] * EMBEDDING_DIMENSIONS


def generate_query_embedding(query: str) -> list:
    return generate_embedding(query)


def cosine_similarity_python(a: list, b: list) -> float:
    """Pure Python cosine similarity fallback."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def cosine_similarity(a: list, b: list) -> float:
    """
    Cosine similarity using C++ kernel if available.
    Falls back to pure Python.
    """
    try:
        _debug_path = os.path.join(
            os.path.dirname(__file__), "..",
            "bridge", "memory_bridge_rs", "target", "debug"
        )
        _debug_path = os.path.abspath(_debug_path)
        if _debug_path not in sys.path:
            sys.path.insert(0, _debug_path)
        import memory_bridge_rs as _mbr
        return _mbr.semantic_similarity(a, b)
    except (ImportError, AttributeError, Exception):
        return cosine_similarity_python(a, b)
