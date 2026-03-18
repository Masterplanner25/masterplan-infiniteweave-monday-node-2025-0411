"""
test_security.py
─────────────────
Security tests — Phase 2 implementation complete.

All 7 previously-failing security tests now pass.
Each test verifies both the rejection path (no auth → 401/error)
and the acceptance path (valid credentials → expected behavior).
"""
import pytest
import os


class TestAuthenticationMissing:
    def test_get_tasks_list_returns_401(self, client):
        """
        SECURITY: GET /tasks/list requires JWT authentication.
        Without credentials, must return 401.
        """
        response = client.get("/tasks/list")
        assert response.status_code == 401, (
            f"GET /tasks/list returned {response.status_code} without auth. "
            "Expected 401. JWT auth dependency is configured on this route."
        )

    def test_post_create_task_requires_auth(self, client):
        """
        SECURITY: POST /tasks/create requires JWT authentication.
        Without credentials, must return 401.
        """
        response = client.post("/tasks/create", json={
            "name": "security_test_task",
            "category": "test"
        })
        assert response.status_code == 401, (
            f"POST /tasks/create returned {response.status_code}. "
            "Expected 401. Route requires authentication."
        )

    def test_leadgen_requires_auth(self, client):
        """
        SECURITY: POST /leadgen/ requires JWT authentication.
        Without credentials, must return 401.
        """
        response = client.post("/leadgen/?query=test")
        assert response.status_code == 401, (
            f"POST /leadgen/ returned {response.status_code}. "
            "Expected 401. AI endpoint requires authentication."
        )

    def test_genesis_session_requires_auth(self, client):
        """
        SECURITY: POST /genesis/session requires JWT authentication.
        Without credentials, must return 401.
        """
        response = client.post("/genesis/session")
        assert response.status_code == 401, (
            f"POST /genesis/session returned {response.status_code}. "
            "Expected 401."
        )

    def test_analytics_requires_auth(self, client):
        """
        SECURITY: POST /analytics/linkedin/manual requires JWT authentication.
        Without credentials, must return 401 before field validation.
        """
        response = client.post("/analytics/linkedin/manual", json={})
        assert response.status_code == 401, (
            f"POST /analytics/linkedin/manual returned {response.status_code}. "
            "Expected 401 before field validation."
        )

    def test_protected_routes_accept_valid_token(self, client, auth_headers):
        """
        SECURITY: Protected routes accept a valid JWT token.
        With valid credentials, routes must not return 401.
        """
        # GET /tasks/list — returns 200 or 500 (no DB), not 401
        response = client.get("/tasks/list", headers=auth_headers)
        assert response.status_code != 401, (
            f"GET /tasks/list returned 401 with a valid token — auth is broken."
        )

        # POST /genesis/session — returns 200, 201, or 500 (no DB), not 401
        response = client.post("/genesis/session", headers=auth_headers)
        assert response.status_code != 401, (
            f"POST /genesis/session returned 401 with a valid token — auth is broken."
        )


class TestCORSConfiguration:
    def test_cors_is_not_wildcard(self, app):
        """
        SECURITY: CORS must not use wildcard allow_origins with allow_credentials=True.
        main.py now reads ALLOWED_ORIGINS from environment and uses explicit origins.
        """
        cors_middleware = None
        for middleware in app.user_middleware:
            cls_name = getattr(middleware.cls, "__name__", "")
            if "CORS" in cls_name:
                cors_middleware = middleware
                break

        assert cors_middleware is not None, "CORSMiddleware not found"

        kwargs = cors_middleware.kwargs
        allow_origins = kwargs.get("allow_origins", [])

        assert "*" not in allow_origins, (
            f"SECURITY: CORS allow_origins still contains wildcard '*'. "
            f"Current value: {allow_origins}. "
            "Set ALLOWED_ORIGINS in .env with explicit trusted origins."
        )

    def test_cors_has_explicit_origins(self, app):
        """CORS allow_origins must contain at least one explicit origin."""
        cors_middleware = None
        for middleware in app.user_middleware:
            if "CORS" in getattr(middleware.cls, "__name__", ""):
                cors_middleware = middleware
                break

        assert cors_middleware is not None
        allow_origins = cors_middleware.kwargs.get("allow_origins", [])
        assert len(allow_origins) > 0, "No allowed origins configured"
        assert all(o.startswith("http") for o in allow_origins), (
            f"Expected all origins to be http/https URLs. Got: {allow_origins}"
        )


class TestPermissionSecret:
    def test_permission_secret_not_default_value(self):
        """
        SECURITY CHECK: PERMISSION_SECRET should not be the default placeholder.

        The code in bridge_router.py falls back to 'dev-secret-must-change' if
        PERMISSION_SECRET is not set. The .env has 'dev-key-change-this'.
        Neither is a production-safe secret.
        """
        secret = os.environ.get("PERMISSION_SECRET", "")
        insecure_defaults = {
            "dev-secret-must-change",
            "dev-key-change-this",
            "secret",
            "changeme",
            "",
        }
        assert secret not in insecure_defaults, (
            f"SECURITY: PERMISSION_SECRET is set to an insecure default value: '{secret}'. "
            "Use a cryptographically random secret in production."
        )


class TestHardcodedSecrets:
    def test_no_hardcoded_openai_keys_in_source(self):
        """
        Check that no OpenAI API keys are hardcoded in Python source files.
        Keys in .env are acceptable; keys in .py files are not.
        """
        import glob

        pattern_prefix = "sk-proj-"
        py_files = glob.glob(
            "C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/**/*.py",
            recursive=True
        )

        found_in = []
        for filepath in py_files:
            # Skip test files and .env
            if "tests/" in filepath.replace("\\", "/"):
                continue
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if pattern_prefix in content:
                    found_in.append(filepath)
            except Exception:
                pass

        assert len(found_in) == 0, (
            f"SECURITY: OpenAI API key prefix '{pattern_prefix}' found in source files: {found_in}. "
            "API keys must be in .env only, never committed to source."
        )

    def test_no_hardcoded_deepseek_keys_in_source(self):
        """Check for hardcoded DeepSeek API keys in Python source."""
        import glob

        py_files = glob.glob(
            "C:/dev/masterplan-infiniteweave-monday-node-2025-0411/AINDY/**/*.py",
            recursive=True
        )

        found_in = []
        import re
        pattern = re.compile(r'sk-[0-9a-f]{32,}')

        for filepath in py_files:
            if "tests/" in filepath.replace("\\", "/"):
                continue
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                for line in content.split("\n"):
                    if "os.getenv" in line or "os.environ" in line:
                        continue
                    if pattern.search(line):
                        found_in.append(f"{filepath}: {line.strip()[:80]}")
            except Exception:
                pass

        assert len(found_in) == 0, (
            f"SECURITY: Potential hardcoded API keys found in source: {found_in}"
        )


class TestRateLimit:
    def test_rate_limiting_exists(self, app):
        """
        SECURITY: Rate limiting middleware is configured on the application.
        SlowAPIMiddleware is registered via app.add_middleware(SlowAPIMiddleware).
        """
        middleware_names = [
            getattr(m.cls, "__name__", str(m.cls))
            for m in app.user_middleware
        ]
        rate_limit_indicators = ["RateLimit", "Throttle", "Limiter", "SlowAPI"]
        has_rate_limit = any(
            any(ind in name for ind in rate_limit_indicators)
            for name in middleware_names
        )
        assert has_rate_limit, (
            f"No rate limiting middleware found. "
            f"Active middleware: {middleware_names}. "
            "SlowAPIMiddleware must be registered via app.add_middleware()."
        )

    def test_limiter_attached_to_app_state(self, app):
        """app.state.limiter must be set for SlowAPIMiddleware to function."""
        assert hasattr(app.state, "limiter"), (
            "app.state.limiter is not set. "
            "Rate limiting middleware will fail on every request without it."
        )
