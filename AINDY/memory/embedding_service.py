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
import threading

from openai import OpenAI

from AINDY.config import settings
from AINDY.platform_layer.external_call_service import perform_external_call
from AINDY.platform_layer.openai_client import create_embedding

EMBEDDING_MODEL = "text-embedding-ada-002"
EMBEDDING_DIMENSIONS = 1536
_DEFAULT_PERFORM_EXTERNAL_CALL = perform_external_call


class EmbeddingFailedError(RuntimeError):
    """
    Raised by generate_embedding() when the OpenAI API call fails after all
    retry attempts.  Callers in the async-job path (embedding_jobs.py) let
    this propagate so that process_embedding_job() can set
    embedding_status='failed' on the node.  Query-path callers
    (generate_query_embedding) catch this and return a zero vector so that
    similarity searches degrade gracefully rather than crashing.
    """


_client: Optional[OpenAI] = None
_client_lock = threading.Lock()


def get_client() -> OpenAI:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def generate_embedding(text: str) -> list:
    """
    Generate a 1536-dim embedding for *text*.

    Returns a zero vector immediately when *text* is empty — that is an
    intentional no-op, not a failure.

    Raises EmbeddingFailedError when the OpenAI API call fails after all
    retry attempts, so callers (e.g. process_embedding_job) receive the
    actual error and can set an inspectable embedding_status='failed' on
    the memory node.
    """
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIMENSIONS
    if (
        settings.is_testing
        and perform_external_call is _DEFAULT_PERFORM_EXTERNAL_CALL
        and _client is None
    ):
        return [0.0] * EMBEDDING_DIMENSIONS

    text = text[:32000]
    client = get_client()
    last_exc: Exception | None = None

    for attempt in range(3):
        try:
            response = perform_external_call(
                service_name="openai",
                endpoint="embeddings.create",
                model=EMBEDDING_MODEL,
                method="openai.embeddings",
                extra={"purpose": "embedding_generation"},
                operation=lambda: create_embedding(
                    client,
                    input=text,
                    model=EMBEDDING_MODEL,
                    timeout=settings.OPENAI_EMBEDDING_TIMEOUT_SECONDS,
                ),
            )
            embedding = response.data[0].embedding
            assert len(embedding) == EMBEDDING_DIMENSIONS
            return embedding
        except Exception as e:
            last_exc = e
            if attempt < 2:
                time.sleep(2 ** attempt)

    # All 3 attempts failed — raise a typed error so callers can mark the
    # node as failed rather than silently storing a zero vector.
    raise EmbeddingFailedError(
        f"Embedding generation failed after 3 attempts: {last_exc}"
    ) from last_exc


def generate_query_embedding(query: str) -> list:
    """
    Generate an embedding for a similarity query.

    Degrades gracefully: returns a zero vector when the API is unavailable
    so that search callers get empty results rather than a 500 error.
    """
    try:
        return generate_embedding(query)
    except EmbeddingFailedError as exc:
        logging.warning(
            "Query embedding failed — returning zero vector for graceful degradation: %s", exc
        )
        return [0.0] * EMBEDDING_DIMENSIONS


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
            os.path.dirname(__file__),
            "native", "memory_bridge_rs", "target", "debug"
        )
        _debug_path = os.path.abspath(_debug_path)
        if _debug_path not in sys.path:
            sys.path.insert(0, _debug_path)
        import memory_bridge_rs as _mbr
        return _mbr.semantic_similarity(a, b)
    except (ImportError, AttributeError, Exception):
        return cosine_similarity_python(a, b)

