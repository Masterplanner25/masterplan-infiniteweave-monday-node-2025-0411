"""
test_security.py
─────────────────
Security diagnostic tests.

THESE TESTS ARE INTENTIONALLY WRITTEN TO FAIL.
Each failing test documents a known security vulnerability.
Do not "fix" these tests by changing assertions — fix the underlying code.

Known security issues documented here:
1. No authentication on any route
2. CORS wildcard with credentials
3. PERMISSION_SECRET is a non-production default
4. No API key hardcoded checks
5. No rate limiting
"""
import pytest
import os


class TestAuthenticationMissing:
    def test_get_tasks_list_returns_401_WILL_FAIL(self, client):
        """
        SECURITY BUG — INTENTIONAL FAIL.

        GET /tasks/list has no authentication middleware.
        A secure API would return 401 Unauthorized for unauthenticated requests.
        Currently returns 200 (or 500 from DB), confirming no auth is enforced.

        Fix: Add authentication middleware or dependency to task routes.
        """
        response = client.get("/tasks/list")
        assert response.status_code == 401, (
            f"SECURITY BUG: GET /tasks/list returned {response.status_code} without auth. "
            "Expected 401. No authentication middleware is configured on this route."
        )

    def test_post_create_task_requires_auth_WILL_FAIL(self, client):
        """
        SECURITY BUG — INTENTIONAL FAIL.

        POST /tasks/create allows writes without any authentication.
        """
        response = client.post("/tasks/create", json={
            "name": "security_test_task",
            "category": "test"
        })
        assert response.status_code == 401, (
            f"SECURITY BUG: POST /tasks/create returned {response.status_code}. "
            "Expected 401. Route accepts writes without authentication."
        )

    def test_leadgen_requires_auth_WILL_FAIL(self, client):
        """
        SECURITY BUG — INTENTIONAL FAIL.

        POST /leadgen/ makes OpenAI API calls and creates DB records.
        It should require authentication before executing.
        """
        response = client.post("/leadgen/?query=test")
        assert response.status_code == 401, (
            f"SECURITY BUG: POST /leadgen/ returned {response.status_code}. "
            "Expected 401. Endpoint triggers AI calls without authentication."
        )

    def test_genesis_session_requires_auth_WILL_FAIL(self, client):
        """
        SECURITY BUG — INTENTIONAL FAIL.

        POST /genesis/session creates DB records without authentication.
        """
        response = client.post("/genesis/session")
        assert response.status_code == 401, (
            f"SECURITY BUG: POST /genesis/session returned {response.status_code}. "
            "Expected 401."
        )

    def test_analytics_requires_auth_WILL_FAIL(self, client):
        """
        SECURITY BUG — INTENTIONAL FAIL.

        POST /analytics/linkedin/manual writes business metrics without authentication.
        """
        response = client.post("/analytics/linkedin/manual", json={})
        # 422 is expected from missing fields — but first it should check auth
        # Without auth middleware, it goes directly to validation
        assert response.status_code == 401, (
            f"SECURITY BUG: POST /analytics/linkedin/manual returned {response.status_code}. "
            "Expected 401 before field validation."
        )


class TestCORSConfiguration:
    def test_cors_is_not_wildcard_WILL_FAIL(self, app):
        """
        SECURITY BUG — INTENTIONAL FAIL.

        main.py configures CORS with allow_origins=["*"] AND allow_credentials=True.
        This combination is a security violation — browsers reject this configuration
        and it exposes the API to cross-origin credential theft.

        Fix: Set allow_origins to specific trusted domains, not wildcard.
        """
        # Find the CORSMiddleware configuration
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
            f"SECURITY BUG: CORS allow_origins contains wildcard '*'. "
            f"Current value: {allow_origins}. "
            "With allow_credentials=True, this is a security misconfiguration. "
            "Fix: Replace '*' with specific trusted origin domains."
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
        # DeepSeek keys look like: sk-[hex string]
        import re
        pattern = re.compile(r'sk-[0-9a-f]{32,}')

        for filepath in py_files:
            if "tests/" in filepath.replace("\\", "/"):
                continue
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                # Skip lines that just do os.getenv
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
    def test_rate_limiting_exists_WILL_FAIL(self, app):
        """
        SECURITY BUG — INTENTIONAL FAIL.

        No rate limiting middleware is configured on any route.
        This leaves the API vulnerable to abuse and DoS attacks.

        Fix: Add rate limiting middleware (e.g., slowapi, fastapi-limiter).
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
            f"SECURITY BUG: No rate limiting middleware found. "
            f"Active middleware: {middleware_names}. "
            "Add rate limiting to protect against API abuse."
        )
