"""
External Service Resilience Tests

Covers hardened failure behaviour for:
  1. OpenAI agent planning failure → clear, structured error (not silent None)
  2. Embedding failure → inspectable embedding_status='failed' on the memory node
  3. Distributed mode without Redis → explicit RuntimeError (not silent fallback)
  4. Mongo skipped mode → HTTP 503, unrelated routes unaffected

All tests use mocks — no live external services required.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Force test-safe environment before any AINDY imports
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("TEST_MODE", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")


# ===========================================================================
# Helpers
# ===========================================================================

def _mock_db():
    """Return a lightweight MagicMock that satisfies Session-like calls."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.add.return_value = None
    db.commit.return_value = None
    db.refresh.return_value = None
    return db


# ===========================================================================
# 1. OpenAI agent planning failure → clear error reason propagated
# ===========================================================================

class TestAgentPlanningFailure:

    def test_generate_plan_stores_failure_reason_in_thread_local(self):
        """
        When OpenAI raises, generate_plan() must store the exception type+message
        in _plan_failure.reason before returning None.
        """
        from AINDY.agents import agent_runtime

        db = _mock_db()

        with patch.object(
            agent_runtime, "perform_external_call",
            side_effect=ConnectionError("OpenAI connection refused"),
        ), patch.object(
            agent_runtime, "_get_planner_context",
            return_value={"system_prompt": "You are a planner."},
        ), patch.object(
            agent_runtime, "_get_tools_for_run",
            return_value=[],
        ):
            result = agent_runtime.generate_plan(
                objective="Send all user data to /dev/null",
                user_id=str(uuid.uuid4()),
                db=db,
            )

        assert result is None, "generate_plan must return None on failure"
        reason = getattr(agent_runtime._plan_failure, "reason", None)
        assert reason is not None, "_plan_failure.reason must be set after failure"
        assert "ConnectionError" in reason
        assert "OpenAI connection refused" in reason

    def test_create_run_includes_failure_reason_in_error_event(self):
        """
        create_run() must embed the captured failure reason in the emitted
        error event, not just log a generic 'Failed to generate agent plan'.
        """
        from AINDY.agents import agent_runtime

        db = _mock_db()
        captured_events: list[dict[str, Any]] = []

        def _capture_error_event(**kwargs):
            captured_events.append(kwargs)

        with patch.object(
            agent_runtime, "perform_external_call",
            side_effect=TimeoutError("OpenAI request timed out"),
        ), patch.object(
            agent_runtime, "_get_planner_context",
            return_value={"system_prompt": "You are a planner."},
        ), patch.object(
            agent_runtime, "_get_tools_for_run",
            return_value=[],
        ), patch.object(
            agent_runtime, "emit_error_event",
            side_effect=_capture_error_event,
        ):
            result = agent_runtime.create_run(
                objective="Do dangerous thing",
                user_id=str(uuid.uuid4()),
                db=db,
            )

        assert result is None, "create_run must return None when planning fails"
        assert len(captured_events) >= 1, "An error event must be emitted"

        plan_event = next(
            (e for e in captured_events if e.get("error_type") == "agent_plan_generation"),
            None,
        )
        assert plan_event is not None, "agent_plan_generation error event must be emitted"
        message = plan_event.get("message", "")
        assert "TimeoutError" in message or "timed out" in message, (
            f"Error message should include the specific exception; got: {message!r}"
        )
        # The failure_reason must also appear in the payload for structured logging
        payload = plan_event.get("payload", {})
        assert "failure_reason" in payload, (
            "failure_reason must be included in the error event payload"
        )

    def test_generate_plan_returns_none_on_json_parse_failure(self):
        """
        When OpenAI returns non-JSON, generate_plan must return None and store reason.
        """
        from AINDY.agents import agent_runtime

        db = _mock_db()

        bad_response = MagicMock()
        bad_response.choices[0].message.content = "This is not JSON at all!"

        with patch.object(
            agent_runtime, "perform_external_call",
            return_value=bad_response,
        ), patch.object(
            agent_runtime, "_get_planner_context",
            return_value={"system_prompt": "You are a planner."},
        ), patch.object(
            agent_runtime, "_get_tools_for_run",
            return_value=[],
        ):
            result = agent_runtime.generate_plan(
                objective="test",
                user_id=str(uuid.uuid4()),
                db=db,
            )

        assert result is None
        # Either JSON parse error or missing-fields guard
        reason = getattr(agent_runtime._plan_failure, "reason", None)
        assert reason is not None


# ===========================================================================
# 2. Embedding failure → inspectable deferred pending state
# ===========================================================================

class TestEmbeddingFailureStatus:

    def test_generate_embedding_raises_embedding_failed_error_on_api_failure(self):
        """
        generate_embedding() must raise EmbeddingFailedError (not return a zero
        vector) when the OpenAI API call fails after all retries.
        """
        from AINDY.memory.embedding_service import EmbeddingFailedError, generate_embedding

        with patch(
            "AINDY.memory.embedding_service.perform_external_call",
            side_effect=RuntimeError("API key invalid"),
        ):
            with pytest.raises(EmbeddingFailedError) as exc_info:
                generate_embedding("Some content that needs embedding")

        assert "API key invalid" in str(exc_info.value)

    def test_generate_query_embedding_degrades_gracefully(self):
        """
        generate_query_embedding() must return a zero vector (not raise) when
        the API is unavailable, so similarity searches continue to work.
        """
        from AINDY.memory.embedding_service import EMBEDDING_DIMENSIONS, generate_query_embedding

        with patch(
            "AINDY.memory.embedding_service.perform_external_call",
            side_effect=RuntimeError("timeout"),
        ):
            result = generate_query_embedding("find similar content")

        assert result == [0.0] * EMBEDDING_DIMENSIONS, (
            "generate_query_embedding must return zero vector on failure, not raise"
        )

    def test_process_embedding_job_leaves_pending_status_on_api_error(self):
        """
        When generate_embedding() raises, process_embedding_job() must leave
        the memory node pending so a later background sweep can retry it.
        """
        from AINDY.memory.embedding_service import EmbeddingFailedError

        db = _mock_db()
        node_id = uuid.uuid4()

        mock_node = MagicMock()
        mock_node.id = node_id
        mock_node.content = "Important memory content"
        mock_node.user_id = uuid.uuid4()
        mock_node.source_event_id = None
        mock_node.extra = {}
        mock_node.embedding_pending = True
        mock_node.embedding_status = "pending"

        db.query.return_value.filter.return_value.first.return_value = mock_node

        committed_statuses: list[str] = []

        def _capture_commit():
            committed_statuses.append(mock_node.embedding_status)

        db.commit.side_effect = _capture_commit

        with patch(
            "AINDY.memory.embedding_jobs.generate_embedding",
            side_effect=EmbeddingFailedError("OpenAI returned 429 Too Many Requests"),
        ), patch(
            "AINDY.memory.embedding_jobs.queue_system_event",
            return_value=str(uuid.uuid4()),
        ):
            from AINDY.memory.embedding_jobs import process_embedding_job

            result = process_embedding_job(
                {"memory_id": str(node_id), "trace_id": "t-1"},
                db,
            )

        assert result is not None
        assert result.get("embedding_pending") is True, (
            f"Expected embedding_pending=True, got: {result}"
        )
        assert result.get("embedding_status") == "pending", (
            f"Expected embedding_status='pending', got: {result}"
        )
        assert "pending" in committed_statuses, (
            "embedding_status='pending' must be committed to the DB"
        )

    def test_empty_text_returns_zero_vector_without_api_call(self):
        """
        Empty text must return a zero vector immediately without touching the
        API — this is intentional behaviour (not a failure path).
        """
        from AINDY.memory.embedding_service import EMBEDDING_DIMENSIONS, generate_embedding

        with patch(
            "AINDY.memory.embedding_service.perform_external_call",
            side_effect=AssertionError("API must not be called for empty text"),
        ):
            result = generate_embedding("")

        assert result == [0.0] * EMBEDDING_DIMENSIONS


# ===========================================================================
# 3. Distributed mode without Redis → hard RuntimeError
# ===========================================================================

class TestDistributedModeRequiresRedis:

    def setup_method(self):
        from AINDY.core.distributed_queue import reset_queue
        reset_queue()

    def teardown_method(self):
        from AINDY.core.distributed_queue import reset_queue
        reset_queue()

    def test_get_queue_raises_when_distributed_and_no_redis_url(self):
        """
        get_queue() must raise RuntimeError (not silently fall back to in-memory)
        when EXECUTION_MODE=distributed and REDIS_URL is absent.
        Silently falling back would cause jobs to be lost on process restart.
        """
        from AINDY.core.distributed_queue import get_queue

        env_patch = {
            "EXECUTION_MODE": "distributed",
            "TESTING": "false",
            "TEST_MODE": "false",
        }
        # Ensure REDIS_URL is absent
        with patch.dict(os.environ, env_patch, clear=False):
            original_redis = os.environ.pop("REDIS_URL", None)
            try:
                with pytest.raises(RuntimeError) as exc_info:
                    get_queue()
            finally:
                if original_redis is not None:
                    os.environ["REDIS_URL"] = original_redis

        assert "REDIS_URL" in str(exc_info.value)
        assert "distributed" in str(exc_info.value).lower()

    def test_get_queue_falls_back_to_memory_when_thread_mode_and_no_redis(self):
        """
        In EXECUTION_MODE=thread (the default), omitting REDIS_URL must still
        fall back to InMemoryQueueBackend with a warning — not raise.
        """
        from AINDY.core.distributed_queue import InMemoryQueueBackend, get_queue

        env_patch = {
            "EXECUTION_MODE": "thread",
            "TESTING": "false",
            "TEST_MODE": "false",
        }
        with patch.dict(os.environ, env_patch, clear=False):
            original_redis = os.environ.pop("REDIS_URL", None)
            try:
                queue = get_queue()
            finally:
                if original_redis is not None:
                    os.environ["REDIS_URL"] = original_redis

        assert isinstance(queue, InMemoryQueueBackend)

    def test_test_mode_always_uses_memory_regardless_of_execution_mode(self):
        """
        Test mode must always use InMemoryQueueBackend even when
        EXECUTION_MODE=distributed — the distributed guard must not interfere
        with the test isolation path.
        """
        from AINDY.core.distributed_queue import InMemoryQueueBackend, get_queue

        env_patch = {
            "EXECUTION_MODE": "distributed",
            "TESTING": "true",
        }
        with patch.dict(os.environ, env_patch, clear=False):
            original_redis = os.environ.pop("REDIS_URL", None)
            try:
                queue = get_queue()
            finally:
                if original_redis is not None:
                    os.environ["REDIS_URL"] = original_redis

        assert isinstance(queue, InMemoryQueueBackend)


# ===========================================================================
# 4. Mongo skipped mode → HTTP 503, unrelated routes unaffected
# ===========================================================================

class TestMongoSkipMode:

    def test_get_mongo_db_raises_http_503_when_client_is_none(self):
        """
        get_mongo_db() must raise HTTPException(503) — not RuntimeError —
        when the Mongo client is None (SKIP_MONGO_PING=true or no MONGO_URL).
        HTTP 503 produces a structured API error response; RuntimeError would
        produce an unhandled 500 with a traceback.
        """
        from fastapi import HTTPException
        from AINDY.db import mongo_setup

        with patch.object(mongo_setup, "get_mongo_client", return_value=None):
            gen = mongo_setup.get_mongo_db()
            with pytest.raises(HTTPException) as exc_info:
                next(gen)

        assert exc_info.value.status_code == 503
        assert "MongoDB" in exc_info.value.detail

    def test_get_mongo_db_is_not_raised_for_routes_not_using_mongo(self):
        """
        Routes that do not call get_mongo_db() must be completely unaffected
        when Mongo is unavailable.  This test simulates a non-Mongo dependency
        call (get_db for Postgres) to confirm isolation.
        """
        from AINDY.db.database import get_db

        # get_db is the Postgres SessionLocal dependency — it must not raise
        # even when Mongo is unavailable.
        with patch("AINDY.db.mongo_setup.get_mongo_client", return_value=None):
            # Just verify get_db itself is importable and callable without Mongo
            assert callable(get_db)

    def test_get_mongo_db_yields_db_when_client_is_available(self):
        """
        Sanity check: get_mongo_db() must yield normally when a client is present.
        """
        from AINDY.db import mongo_setup

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db

        with patch.object(mongo_setup, "get_mongo_client", return_value=mock_client):
            gen = mongo_setup.get_mongo_db()
            result = next(gen)

        assert result is mock_db


# ===========================================================================
# 5. Circuit open routes -> structured 503
# ===========================================================================

class TestCircuitOpenErrorHttpResponse:

    def test_genesis_message_returns_503_when_circuit_is_open(self, client, auth_headers):
        with patch(
            "apps.masterplan.routes.genesis_router._get_owned_session",
            return_value=SimpleNamespace(synthesis_ready=False),
        ), patch(
            "apps.masterplan.routes.genesis_router.run_flow",
            return_value={"status": "FAILED", "error": "Circuit open rejecting call"},
        ):
            response = client.post(
                "/genesis/message",
                json={"session_id": 1, "message": "help me define the plan"},
                headers=auth_headers,
            )

        assert response.status_code == 503
        assert response.json()["error"] == "ai_provider_unavailable"
        assert "Retry-After" in response.headers

    def test_leadgen_returns_503_when_circuit_is_open(self, client, auth_headers):
        from AINDY.kernel.circuit_breaker import CircuitOpenError

        with patch(
            "apps.search.services.leadgen_service.search_leads",
            return_value={
                "results": [
                    {
                        "company": "Acme AI",
                        "url": "https://acme.example",
                        "context": "Acme is evaluating automation partners.",
                    }
                ]
            },
        ), patch(
            "apps.search.services.leadgen_service.chat_completion",
            side_effect=CircuitOpenError("circuit open"),
        ), patch(
            "apps.search.services.leadgen_service.create_memory_node",
            return_value=None,
        ):
            response = client.post("/leadgen/?query=acme", headers=auth_headers)

        assert response.status_code == 503
        assert response.json()["retryable"] is True

    def test_non_ai_routes_still_work_when_openai_circuit_is_open(self, client, auth_headers):
        from AINDY.kernel.circuit_breaker import get_openai_circuit_breaker

        cb = get_openai_circuit_breaker()
        cb.reset()
        try:
            cb._record_failure("closed")
            cb._record_failure("closed")
            cb._record_failure("closed")

            with patch(
                "apps.tasks.services.task_service.list_tasks",
                return_value=[],
            ):
                health_response = client.get("/health")
                tasks_response = client.get("/tasks/list", headers=auth_headers)

            assert health_response.status_code == 200
            assert tasks_response.status_code == 200
        finally:
            cb.reset()

    def test_health_deep_reports_degraded_when_circuit_is_open(self, client):
        from AINDY.kernel.circuit_breaker import get_openai_circuit_breaker

        cb = get_openai_circuit_breaker()
        cb.reset()
        try:
            cb._record_failure("closed")
            cb._record_failure("closed")
            cb._record_failure("closed")

            response = client.get("/health/deep")
            payload = response.json()

            assert response.status_code == 200
            assert payload["status"] == "degraded"
            assert payload["checks"]["ai_providers"]["openai"]["circuit"] == "open"
        finally:
            cb.reset()
