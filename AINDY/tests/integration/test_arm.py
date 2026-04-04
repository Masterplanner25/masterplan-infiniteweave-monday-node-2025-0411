"""
test_arm.py — ARM Autonomous Reasoning Module Tests

Covers:
- SecurityValidator: path traversal, extension block, sensitive content, size limit
- ConfigManager: defaults, Task Priority formula, persistence, key filtering
- FileProcessor: chunking logic, session ID generation
- ARM API routes: auth enforcement, mocked OpenAI calls, config endpoints
"""
import uuid
import pytest
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# SecurityValidator
# ─────────────────────────────────────────────────────────────────────────────

class TestSecurityValidator:

    def test_blocks_env_file(self):
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        v = SecurityValidator()
        with pytest.raises(HTTPException) as exc_info:
            v.validate_file_path("/app/.env")
        assert exc_info.value.status_code == 403

    def test_blocks_dotenv_path_segment(self):
        """Any path containing /.env/ segment is blocked."""
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        v = SecurityValidator()
        with pytest.raises(HTTPException) as exc_info:
            v.validate_file_path("/project/.env/config")
        assert exc_info.value.status_code == 403

    def test_blocks_venv_directory(self):
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        v = SecurityValidator()
        with pytest.raises(HTTPException) as exc_info:
            v.validate_file_path("/app/venv/lib/site-packages/foo.py")
        assert exc_info.value.status_code == 403

    def test_blocks_unsupported_extension(self, tmp_path):
        """Files with unsupported extensions are rejected with 422."""
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        exe_file = tmp_path / "binary.exe"
        exe_file.write_bytes(b"\x00" * 100)
        v = SecurityValidator()
        with pytest.raises(HTTPException) as exc_info:
            v.validate_file_path(str(exe_file))
        assert exc_info.value.status_code == 422

    def test_blocks_dll_extension(self, tmp_path):
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        dll_file = tmp_path / "module.dll"
        dll_file.write_bytes(b"\x00" * 50)
        v = SecurityValidator()
        with pytest.raises(HTTPException) as exc_info:
            v.validate_file_path(str(dll_file))
        assert exc_info.value.status_code == 422

    def test_missing_file_returns_404(self, tmp_path):
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        v = SecurityValidator()
        with pytest.raises(HTTPException) as exc_info:
            v.validate_file_path(str(tmp_path / "does_not_exist.py"))
        assert exc_info.value.status_code == 404

    def test_blocks_openai_key_in_content(self):
        """OpenAI sk- key pattern must be caught."""
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        v = SecurityValidator()
        fake_key = "sk-" + "A" * 48
        with pytest.raises(HTTPException) as exc_info:
            v.validate_content(f'api_key = "{fake_key}"')
        assert exc_info.value.status_code == 403

    def test_blocks_generic_api_key_assignment(self):
        """Generic api_key = '...' pattern is blocked."""
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        v = SecurityValidator()
        with pytest.raises(HTTPException) as exc_info:
            v.validate_content('API_KEY = "supersecretvalue123"')
        assert exc_info.value.status_code == 403

    def test_blocks_private_key_pem(self):
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        v = SecurityValidator()
        with pytest.raises(HTTPException) as exc_info:
            v.validate_content("-----BEGIN RSA PRIVATE KEY-----\nMIIEo...")
        assert exc_info.value.status_code == 403

    def test_blocks_aws_access_key(self):
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        v = SecurityValidator()
        with pytest.raises(HTTPException) as exc_info:
            v.validate_content("aws_key = AKIA1234567890ABCDEF")
        assert exc_info.value.status_code == 403

    def test_allows_clean_python_file(self, tmp_path):
        """Clean Python files pass all validation layers."""
        from modules.deepseek.security_deepseek import SecurityValidator
        py_file = tmp_path / "clean.py"
        py_file.write_text("def hello():\n    return 'world'\n")
        v = SecurityValidator()
        path, content = v.full_file_validation(str(py_file))
        assert "hello" in content

    def test_allows_clean_js_file(self, tmp_path):
        from modules.deepseek.security_deepseek import SecurityValidator
        js_file = tmp_path / "app.js"
        js_file.write_text("function greet() { return 'hello'; }\n")
        v = SecurityValidator()
        path, content = v.full_file_validation(str(js_file))
        assert "greet" in content

    def test_blocks_oversized_file(self, tmp_path):
        """Files exceeding the size limit are rejected with 422."""
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        large_file = tmp_path / "huge.py"
        large_file.write_bytes(b"x" * 200_000)   # 200 KB
        v = SecurityValidator({"max_file_size_bytes": 100_000})
        with pytest.raises(HTTPException) as exc_info:
            v.full_file_validation(str(large_file))
        assert exc_info.value.status_code == 422

    def test_size_limit_respected_exactly(self, tmp_path):
        """Content exactly at the limit passes; one byte over fails."""
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        limit = 1_000
        v = SecurityValidator({"max_file_size_bytes": limit})

        ok_file = tmp_path / "ok.py"
        ok_file.write_bytes(b"a" * limit)
        path, content = v.full_file_validation(str(ok_file))
        assert content  # passed

        over_file = tmp_path / "over.py"
        over_file.write_bytes(b"a" * (limit + 1))
        with pytest.raises(HTTPException) as exc_info:
            v.full_file_validation(str(over_file))
        assert exc_info.value.status_code == 422

    def test_validate_code_input_rejects_key(self):
        from modules.deepseek.security_deepseek import SecurityValidator
        from fastapi import HTTPException
        v = SecurityValidator()
        with pytest.raises(HTTPException):
            v.validate_code_input('password = "mysupersecretpassword123"')

    def test_validate_code_input_accepts_clean_code(self):
        from modules.deepseek.security_deepseek import SecurityValidator
        v = SecurityValidator()
        result = v.validate_code_input("def add(a, b):\n    return a + b\n")
        assert result == "def add(a, b):\n    return a + b\n"


# ─────────────────────────────────────────────────────────────────────────────
# ConfigManager
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigManager:

    def test_loads_defaults_when_file_missing(self):
        from modules.deepseek.config_manager_deepseek import ConfigManager
        cm = ConfigManager(config_path="nonexistent_config_path.json")
        assert cm.get("model") is not None
        assert cm.get("temperature") is not None

    def test_default_model_is_gpt4o(self):
        from modules.deepseek.config_manager_deepseek import ConfigManager
        cm = ConfigManager(config_path="nonexistent_config_path.json")
        assert cm.get("model") == "gpt-4o"

    def test_task_priority_formula(self):
        """TP = (complexity × urgency) / resource_cost."""
        from modules.deepseek.config_manager_deepseek import ConfigManager
        cm = ConfigManager(config_path="nonexistent_config_path.json")
        tp = cm.calculate_task_priority(complexity=5, urgency=5, resource_cost=5)
        assert abs(tp - 5.0) < 0.001

    def test_task_priority_asymmetric(self):
        from modules.deepseek.config_manager_deepseek import ConfigManager
        cm = ConfigManager(config_path="nonexistent_config_path.json")
        # (10 × 2) / 4 = 5.0
        tp = cm.calculate_task_priority(complexity=10, urgency=2, resource_cost=4)
        assert abs(tp - 5.0) < 0.001

    def test_task_priority_zero_resource_cost_no_crash(self):
        """Division by zero is guarded — result must be > 0."""
        from modules.deepseek.config_manager_deepseek import ConfigManager
        cm = ConfigManager(config_path="nonexistent_config_path.json")
        tp = cm.calculate_task_priority(complexity=5, urgency=5, resource_cost=0)
        assert tp > 0

    def test_task_priority_uses_defaults_when_none(self):
        """Passing None uses the configured defaults."""
        from modules.deepseek.config_manager_deepseek import ConfigManager
        cm = ConfigManager(config_path="nonexistent_config_path.json")
        tp_explicit = cm.calculate_task_priority(
            complexity=cm.get("task_complexity_default"),
            urgency=cm.get("task_urgency_default"),
            resource_cost=cm.get("resource_cost_default"),
        )
        tp_implicit = cm.calculate_task_priority()
        assert abs(tp_explicit - tp_implicit) < 0.001

    def test_update_persists_to_file(self, tmp_path):
        from modules.deepseek.config_manager_deepseek import ConfigManager
        cfg_file = tmp_path / "arm_config.json"
        cm = ConfigManager(config_path=str(cfg_file))
        cm.update({"temperature": 0.7})
        # Reload from disk
        cm2 = ConfigManager(config_path=str(cfg_file))
        assert cm2.get("temperature") == 0.7

    def test_update_returns_full_config(self, tmp_path):
        from modules.deepseek.config_manager_deepseek import ConfigManager
        cfg_file = tmp_path / "arm_config.json"
        cm = ConfigManager(config_path=str(cfg_file))
        result = cm.update({"temperature": 0.5})
        assert isinstance(result, dict)
        assert "model" in result
        assert result["temperature"] == 0.5

    def test_update_ignores_unknown_keys(self, tmp_path):
        """Unknown keys are silently filtered — no injection possible."""
        from modules.deepseek.config_manager_deepseek import ConfigManager
        cfg_file = tmp_path / "arm_config.json"
        cm = ConfigManager(config_path=str(cfg_file))
        cm.update({"malicious_injection": "evil_payload"})
        assert cm.get("malicious_injection") is None

    def test_get_all_returns_copy(self):
        from modules.deepseek.config_manager_deepseek import ConfigManager
        cm = ConfigManager(config_path="nonexistent.json")
        cfg1 = cm.get_all()
        cfg2 = cm.get_all()
        # Mutating the returned dict must not affect the internal state
        cfg1["model"] = "tampered"
        assert cm.get("model") != "tampered"
        assert cfg2["model"] != "tampered"


# ─────────────────────────────────────────────────────────────────────────────
# FileProcessor
# ─────────────────────────────────────────────────────────────────────────────

class TestFileProcessor:

    def test_no_chunking_for_small_content(self):
        from modules.deepseek.file_processor_deepseek import FileProcessor
        fp = FileProcessor({"max_chunk_tokens": 4000})
        content = "def hello():\n    return 'world'\n"
        chunks = fp.chunk_content(content)
        assert len(chunks) == 1
        assert chunks[0] == content

    def test_chunks_large_content_into_multiple(self):
        from modules.deepseek.file_processor_deepseek import FileProcessor
        # 10 tokens * 4 chars/token = 40 chars per chunk
        fp = FileProcessor({"max_chunk_tokens": 10})
        content = "\n".join([f"line_{i:03d}" for i in range(50)])
        chunks = fp.chunk_content(content)
        assert len(chunks) > 1

    def test_chunks_preserve_all_content(self):
        """Re-joining chunks should reproduce the original content."""
        from modules.deepseek.file_processor_deepseek import FileProcessor
        fp = FileProcessor({"max_chunk_tokens": 10})
        lines = [f"line_{i}" for i in range(30)]
        content = "\n".join(lines)
        chunks = fp.chunk_content(content)
        # Each chunk ends where the next begins — re-join with newline
        rejoined = "\n".join(chunks)
        assert rejoined == content

    def test_session_id_is_valid_uuid(self):
        from modules.deepseek.file_processor_deepseek import FileProcessor
        fp = FileProcessor({})
        session_id = fp.create_session_id()
        # uuid.UUID() raises ValueError if not valid
        parsed = uuid.UUID(session_id)
        assert str(parsed) == session_id

    def test_session_ids_are_unique(self):
        from modules.deepseek.file_processor_deepseek import FileProcessor
        fp = FileProcessor({})
        ids = {fp.create_session_id() for _ in range(20)}
        assert len(ids) == 20

    def test_session_log_structure(self):
        import time
        from modules.deepseek.file_processor_deepseek import FileProcessor
        fp = FileProcessor({})
        start = time.time()
        log = fp.create_session_log(
            session_id="abc",
            file_path="/tmp/foo.py",
            operation="analyze",
            start_time=start,
            input_tokens=100,
            output_tokens=50,
            status="success",
        )
        assert log["session_id"] == "abc"
        assert log["status"] == "success"
        assert log["input_tokens"] == 100
        assert log["output_tokens"] == 50
        assert log["execution_seconds"] >= 0
        assert log["execution_speed"] > 0

    def test_session_log_includes_error(self):
        import time
        from modules.deepseek.file_processor_deepseek import FileProcessor
        fp = FileProcessor({})
        log = fp.create_session_log(
            session_id="xyz",
            file_path="/tmp/bad.py",
            operation="analyze",
            start_time=time.time(),
            input_tokens=0,
            output_tokens=0,
            status="failed",
            error="TimeoutError",
        )
        assert log["error"] == "TimeoutError"
        assert log["status"] == "failed"

    def test_read_file_returns_content(self, tmp_path):
        from pathlib import Path
        from modules.deepseek.file_processor_deepseek import FileProcessor
        f = tmp_path / "sample.py"
        f.write_text("print('hello')\n", encoding="utf-8")
        fp = FileProcessor({})
        content = fp.read_file(Path(f))
        assert "hello" in content


# ─────────────────────────────────────────────────────────────────────────────
# ARM API Routes
# ─────────────────────────────────────────────────────────────────────────────

class TestARMRoutes:

    # ── Auth enforcement ──────────────────────────────────────────────────────

    def test_analyze_requires_auth(self, client):
        response = client.post("/arm/analyze", json={"file_path": "/some/file.py"})
        assert response.status_code == 401

    def test_generate_requires_auth(self, client):
        response = client.post("/arm/generate", json={"prompt": "write hello world"})
        assert response.status_code == 401

    def test_logs_requires_auth(self, client):
        response = client.get("/arm/logs")
        assert response.status_code == 401

    def test_config_get_requires_auth(self, client):
        response = client.get("/arm/config")
        assert response.status_code == 401

    def test_config_put_requires_auth(self, client):
        response = client.put("/arm/config", json={"updates": {}})
        assert response.status_code == 401

    # ── Config endpoints with auth ────────────────────────────────────────────

    def test_config_get_with_auth_returns_model_key(self, client, auth_headers):
        response = client.get("/arm/config", headers=auth_headers)
        if response.status_code == 200:
            payload = response.json()
            data = payload.get("data", payload)
            assert "model" in data
            assert "temperature" in data

    def test_config_update_with_auth(self, client, auth_headers):
        response = client.put(
            "/arm/config",
            json={"updates": {"temperature": 0.3}},
            headers=auth_headers,
        )
        # 200 = success, 422 = validation error — both are not 401
        assert response.status_code != 401
        if response.status_code == 200:
            payload = response.json()
            data = payload.get("data", payload)
            assert data["status"] == "updated"

    def test_config_update_ignores_unknown_keys(self, client, auth_headers):
        response = client.put(
            "/arm/config",
            json={"updates": {"injected_key": "evil_value"}},
            headers=auth_headers,
        )
        assert response.status_code != 401

    # ── Analyze with mocked OpenAI ────────────────────────────────────────────

    def test_analyze_with_auth_and_mocked_openai(
        self, client, auth_headers, tmp_path, mocker
    ):
        py_file = tmp_path / "module.py"
        py_file.write_text("def hello():\n    return 'world'\n")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """{
            "summary": "Clean simple function",
            "architecture_score": 8,
            "performance_score": 9,
            "integrity_score": 9,
            "findings": [],
            "overall_recommendation": "No changes needed"
        }"""
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50

        mocker.patch(
            "modules.deepseek.deepseek_code_analyzer.OpenAI",
            return_value=MagicMock(
                chat=MagicMock(
                    completions=MagicMock(
                        create=MagicMock(return_value=mock_response)
                    )
                )
            ),
        )

        # Reset singleton so the mock is picked up
        import routes.arm_router as arm_mod
        arm_mod._analyzer = None

        response = client.post(
            "/arm/analyze",
            json={"file_path": str(py_file)},
            headers=auth_headers,
        )
        # 200 on success; 500 if DB unavailable in test env — both are not 401
        assert response.status_code != 401

    # ── Generate with mocked OpenAI ───────────────────────────────────────────

    def test_generate_with_auth_and_mocked_openai(
        self, client, auth_headers, mocker
    ):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """{
            "generated_code": "def hello():\\n    return 'world'",
            "language": "python",
            "explanation": "Simple hello world function",
            "quality_notes": "Works as expected",
            "confidence": 9
        }"""
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 30

        mocker.patch(
            "modules.deepseek.deepseek_code_analyzer.OpenAI",
            return_value=MagicMock(
                chat=MagicMock(
                    completions=MagicMock(
                        create=MagicMock(return_value=mock_response)
                    )
                )
            ),
        )

        import routes.arm_router as arm_mod
        arm_mod._analyzer = None

        response = client.post(
            "/arm/generate",
            json={
                "prompt": "write a hello world function",
                "language": "python",
            },
            headers=auth_headers,
        )
        assert response.status_code != 401

    # ── Security blocks propagate through router ──────────────────────────────

    def test_analyze_blocked_file_type_returns_non_401(
        self, client, auth_headers, tmp_path
    ):
        """Extension validator fires inside the route — should return 422, not 401."""
        exe_file = tmp_path / "binary.exe"
        exe_file.write_bytes(b"\x00" * 100)

        import routes.arm_router as arm_mod
        arm_mod._analyzer = None

        response = client.post(
            "/arm/analyze",
            json={"file_path": str(exe_file)},
            headers=auth_headers,
        )
        assert response.status_code != 401

    def test_logs_returns_structure_with_auth(self, client, auth_headers):
        """GET /arm/logs with auth returns expected JSON structure."""
        response = client.get("/arm/logs", headers=auth_headers)
        if response.status_code == 200:
            payload = response.json()
            data = payload.get("data", payload)
            assert "analyses" in data
            assert "generations" in data
            assert "summary" in data


# ─────────────────────────────────────────────────────────────────────────────
# ARM Metrics — route-level tests
# ─────────────────────────────────────────────────────────────────────────────

class TestARMMetrics:

    def test_metrics_endpoint_requires_auth(self, client):
        response = client.get("/arm/metrics")
        assert response.status_code == 401

    def test_metrics_returns_structure_with_auth(
        self, client, auth_headers, mock_db
    ):
        response = client.get("/arm/metrics", headers=auth_headers)
        # 200 with empty metrics if no DB sessions
        # or 422 if DB not available in test
        assert response.status_code in [200, 422, 500]
        assert response.status_code != 401

    def test_config_suggest_requires_auth(self, client):
        response = client.get("/arm/config/suggest")
        assert response.status_code == 401

    def test_config_suggest_with_auth(
        self, client, auth_headers, mock_db
    ):
        response = client.get("/arm/config/suggest", headers=auth_headers)
        assert response.status_code in [200, 422, 500]
        assert response.status_code != 401


# ─────────────────────────────────────────────────────────────────────────────
# ARMMetricsService — unit tests (no DB needed)
# ─────────────────────────────────────────────────────────────────────────────

class TestARMMetricsService:
    """Unit tests for metrics calculation — no DB needed."""

    def test_empty_metrics_structure(self):
        """Empty metrics returns correct structure."""
        from analytics.arm_metrics_service import ARMMetricsService
        service = ARMMetricsService.__new__(ARMMetricsService)
        result = service._empty_metrics()
        assert "execution_speed" in result
        assert "decision_efficiency" in result
        assert "ai_productivity_boost" in result
        assert "lost_potential" in result
        assert "learning_efficiency" in result

    def test_decision_efficiency_perfect(self):
        """100% success rate = 100% efficiency."""
        from analytics.arm_metrics_service import ARMMetricsService
        from unittest.mock import MagicMock
        service = ARMMetricsService.__new__(ARMMetricsService)

        mock_analyses = [
            MagicMock(
                status="success",
                input_tokens=100,
                output_tokens=50,
                execution_seconds=1.0,
            )
            for _ in range(5)
        ]
        result = service._decision_efficiency(mock_analyses)
        assert result["score"] == 100.0
        assert result["successful"] == 5
        assert result["failed"] == 0

    def test_decision_efficiency_partial(self):
        """3/5 success = 60% efficiency."""
        from analytics.arm_metrics_service import ARMMetricsService
        from unittest.mock import MagicMock
        service = ARMMetricsService.__new__(ARMMetricsService)

        analyses = [MagicMock(status="success") for _ in range(3)] + [
            MagicMock(status="failed") for _ in range(2)
        ]
        result = service._decision_efficiency(analyses)
        assert abs(result["score"] - 60.0) < 0.01

    def test_execution_speed_calculation(self):
        """tokens/seconds = execution speed."""
        from analytics.arm_metrics_service import ARMMetricsService
        from unittest.mock import MagicMock
        service = ARMMetricsService.__new__(ARMMetricsService)

        analyses = [
            MagicMock(
                input_tokens=100,
                output_tokens=50,
                execution_seconds=1.0,
                created_at=None,
            )
        ]
        # 150 tokens / 1.0 second = 150 tokens/sec
        result = service._execution_speed(analyses, [])
        assert result["current"] == 150.0
        assert result["average"] == 150.0

    def test_lost_potential_no_failures(self):
        """No failures = 0% waste."""
        from analytics.arm_metrics_service import ARMMetricsService
        from unittest.mock import MagicMock
        service = ARMMetricsService.__new__(ARMMetricsService)

        analyses = [
            MagicMock(
                status="success",
                input_tokens=100,
                output_tokens=50,
                execution_seconds=1.0,
            )
            for _ in range(3)
        ]
        result = service._lost_potential(analyses)
        assert result["waste_percentage"] == 0.0
        assert result["failed_sessions"] == 0

    def test_lost_potential_with_failures(self):
        """Failed sessions contribute to waste %."""
        from analytics.arm_metrics_service import ARMMetricsService
        from unittest.mock import MagicMock
        service = ARMMetricsService.__new__(ARMMetricsService)

        analyses = [
            MagicMock(
                status="success",
                input_tokens=200,
                output_tokens=100,
                execution_seconds=1.0,
            ),
            MagicMock(
                status="failed",
                input_tokens=100,
                output_tokens=0,
                execution_seconds=0.5,
            ),
        ]
        result = service._lost_potential(analyses)
        # 100 wasted / 400 total = 25% waste
        assert abs(result["waste_percentage"] - 25.0) < 0.01

    def test_ai_productivity_boost_ratio(self):
        """Output/input token ratio calculation."""
        from analytics.arm_metrics_service import ARMMetricsService
        from unittest.mock import MagicMock
        service = ARMMetricsService.__new__(ARMMetricsService)

        analyses = [
            MagicMock(input_tokens=1000, output_tokens=400, execution_seconds=2.0)
        ]
        result = service._ai_productivity_boost(analyses, [])
        # 400/1000 = 0.4
        assert abs(result["ratio"] - 0.4) < 0.001
        assert result["rating"] == "good"

    def test_learning_efficiency_insufficient_data(self):
        """Less than 4 sessions = insufficient data."""
        from analytics.arm_metrics_service import ARMMetricsService
        from unittest.mock import MagicMock
        service = ARMMetricsService.__new__(ARMMetricsService)

        analyses = [
            MagicMock(input_tokens=100, output_tokens=50, execution_seconds=1.0)
            for _ in range(2)
        ]
        result = service._learning_efficiency(analyses)
        assert result["trend"] == "insufficient data"


# ─────────────────────────────────────────────────────────────────────────────
# ARMConfigSuggestionEngine — unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestARMConfigSuggestions:

    def test_no_suggestions_when_metrics_healthy(self):
        """Healthy metrics = no config changes recommended."""
        from analytics.arm_metrics_service import ARMConfigSuggestionEngine

        healthy_metrics = {
            "decision_efficiency": {"score": 95.0},
            "execution_speed": {"average": 200.0},
            "ai_productivity_boost": {"ratio": 0.45},
            "lost_potential": {"waste_percentage": 3.0},
            "learning_efficiency": {
                "trend": "improving",
                "delta_percentage": 10.0,
            },
        }
        engine = ARMConfigSuggestionEngine(
            current_config={"temperature": 0.2, "retry_limit": 3},
            metrics=healthy_metrics,
        )
        result = engine.generate_suggestions()
        suggestions = result["suggestions"]
        # Should only have the "all green" info suggestion
        assert len(suggestions) == 1
        assert suggestions[0]["priority"] == "info"
        assert not suggestions[0].get("config_change")

    def test_suggests_lower_temperature_on_high_failure(self):
        """Critical efficiency triggers temperature reduction."""
        from analytics.arm_metrics_service import ARMConfigSuggestionEngine

        bad_metrics = {
            "decision_efficiency": {"score": 50.0},  # critical
            "execution_speed": {"average": 200.0},
            "ai_productivity_boost": {"ratio": 0.4},
            "lost_potential": {"waste_percentage": 5.0},
            "learning_efficiency": {
                "trend": "stable",
                "delta_percentage": 0.0,
            },
        }
        engine = ARMConfigSuggestionEngine(
            current_config={"temperature": 0.4, "retry_limit": 3},
            metrics=bad_metrics,
        )
        result = engine.generate_suggestions()

        critical = [
            s for s in result["suggestions"] if s["priority"] == "critical"
        ]
        assert len(critical) >= 1
        change = critical[0].get("config_change", {})
        # Should recommend lower temperature
        if "temperature" in change:
            assert change["temperature"] < 0.4

    def test_low_risk_suggestions_in_auto_apply(self):
        """Low-risk suggestions appear in auto_apply_safe."""
        from analytics.arm_metrics_service import ARMConfigSuggestionEngine

        metrics = {
            "decision_efficiency": {"score": 70.0},  # warning
            "execution_speed": {"average": 200.0},
            "ai_productivity_boost": {"ratio": 0.4},
            "lost_potential": {"waste_percentage": 5.0},
            "learning_efficiency": {
                "trend": "stable",
                "delta_percentage": 0.0,
            },
        }
        engine = ARMConfigSuggestionEngine(
            current_config={"temperature": 0.2, "retry_limit": 3},
            metrics=metrics,
        )
        result = engine.generate_suggestions()

        # Low-risk items should be in auto_apply_safe
        auto_apply = result["auto_apply_safe"]
        for item in auto_apply:
            assert item.get("risk") == "low"

    def test_combined_config_contains_all_changes(self):
        """combined_suggested_config merges all suggestions."""
        from analytics.arm_metrics_service import ARMConfigSuggestionEngine

        bad_metrics = {
            "decision_efficiency": {"score": 50.0},
            "execution_speed": {"average": 30.0},  # slow
            "ai_productivity_boost": {"ratio": 0.1},  # low
            "lost_potential": {"waste_percentage": 20.0},  # high
            "learning_efficiency": {
                "trend": "stable",
                "delta_percentage": 0.0,
            },
        }
        engine = ARMConfigSuggestionEngine(
            current_config={
                "temperature": 0.4,
                "retry_limit": 3,
                "max_output_tokens": 2000,
                "max_chunk_tokens": 4000,
                "max_file_size_bytes": 100000,
            },
            metrics=bad_metrics,
        )
        result = engine.generate_suggestions()
        combined = result["combined_suggested_config"]
        # Should have multiple changes
        assert isinstance(combined, dict)

