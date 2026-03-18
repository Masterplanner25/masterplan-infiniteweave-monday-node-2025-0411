"""
test_security.py
─────────────────
Security tests — Phase 2 + Phase 3 implementation complete.

All 7 previously-failing security tests now pass.
Each test verifies both the rejection path (no auth → 401/error)
and the acceptance path (valid credentials → expected behavior).

Phase 3 additions: SEO, Authorship, ARM, RippleTrace, Freelance,
Research, Dashboard, Social route protection tests.
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


class TestPhase3RouteProtection:
    """Phase 3: verify newly protected routers reject unauthenticated requests."""

    def test_seo_analyze_requires_auth(self, client):
        """POST /seo/analyze must return 401 without a token."""
        response = client.post("/seo/analyze", json={"text": "test", "top_n": 3})
        assert response.status_code == 401, (
            f"POST /seo/analyze returned {response.status_code}. Expected 401."
        )

    def test_authorship_reclaim_requires_auth(self, client):
        """POST /authorship/reclaim must return 401 without a token."""
        response = client.post("/authorship/reclaim?content=test&author=Me")
        assert response.status_code == 401, (
            f"POST /authorship/reclaim returned {response.status_code}. Expected 401."
        )

    def test_arm_analyze_requires_auth(self, client):
        """POST /arm/analyze must return 401 without a token (DeepSeek AI endpoint)."""
        response = client.post("/arm/analyze", json={"file_path": "test.py"})
        assert response.status_code == 401, (
            f"POST /arm/analyze returned {response.status_code}. Expected 401."
        )

    def test_rippletrace_requires_auth(self, client):
        """RippleTrace write endpoints must return 401 without a token."""
        response = client.get("/rippletrace/recent")
        assert response.status_code == 401, (
            f"GET /rippletrace/recent returned {response.status_code}. Expected 401."
        )

    def test_freelance_requires_auth(self, client):
        """Freelance endpoints must return 401 without a token."""
        response = client.get("/freelance/orders")
        assert response.status_code == 401, (
            f"GET /freelance/orders returned {response.status_code}. Expected 401."
        )

    def test_research_requires_auth(self, client):
        """Research endpoints must return 401 without a token."""
        response = client.get("/research/")
        assert response.status_code == 401, (
            f"GET /research/ returned {response.status_code}. Expected 401."
        )

    def test_dashboard_requires_auth(self, client):
        """Dashboard overview must return 401 without a token."""
        response = client.get("/dashboard/overview")
        assert response.status_code == 401, (
            f"GET /dashboard/overview returned {response.status_code}. Expected 401."
        )

    def test_social_requires_auth(self, client):
        """Social endpoints must return 401 without a token."""
        response = client.get("/social/feed")
        assert response.status_code == 401, (
            f"GET /social/feed returned {response.status_code}. Expected 401."
        )

    def test_db_verify_requires_api_key(self, client):
        """GET /db/verify must return 401 without an API key (admin endpoint)."""
        response = client.get("/db/verify")
        assert response.status_code == 401, (
            f"GET /db/verify returned {response.status_code}. Expected 401."
        )

    def test_db_verify_accepts_valid_api_key(self, client, api_key_headers):
        """GET /db/verify must not return 401 with a valid API key."""
        response = client.get("/db/verify", headers=api_key_headers)
        assert response.status_code != 401, (
            f"GET /db/verify returned 401 with valid API key — API key auth is broken."
        )

    def test_network_bridge_requires_api_key(self, client):
        """POST /network_bridge/connect must return 401 without an API key."""
        response = client.post("/network_bridge/connect", json={
            "author_name": "Test", "platform": "TestPlatform"
        })
        assert response.status_code == 401, (
            f"POST /network_bridge/connect returned {response.status_code}. Expected 401."
        )

    def test_phase3_routes_accept_valid_token(self, client, auth_headers):
        """Phase 3 JWT-protected routes accept a valid token (not 401)."""
        for method, path, body in [
            ("GET", "/rippletrace/recent", None),
            ("GET", "/freelance/orders", None),
            ("GET", "/research/", None),
        ]:
            if method == "GET":
                r = client.get(path, headers=auth_headers)
            else:
                r = client.post(path, json=body, headers=auth_headers)
            assert r.status_code != 401, (
                f"{method} {path} returned 401 with valid token — auth is broken."
            )


class TestSprintFourAuthHardening:
    """Sprint 4: verify newly-protected routes and ownership enforcement."""

    # --- Calc endpoints (main_router) now require JWT ---
    def test_calculate_twr_requires_auth(self, client):
        """POST /calculate_twr must return 401 without JWT."""
        response = client.post("/calculate_twr", json={})
        assert response.status_code == 401, (
            f"POST /calculate_twr returned {response.status_code}. Expected 401."
        )

    def test_calculate_engagement_requires_auth(self, client):
        """POST /calculate_engagement must return 401 without JWT."""
        response = client.post("/calculate_engagement", json={})
        assert response.status_code == 401, (
            f"POST /calculate_engagement returned {response.status_code}. Expected 401."
        )

    def test_get_results_requires_auth(self, client):
        """GET /results must return 401 without JWT."""
        response = client.get("/results")
        assert response.status_code == 401, (
            f"GET /results returned {response.status_code}. Expected 401."
        )

    def test_get_masterplans_requires_auth(self, client):
        """GET /masterplans must return 401 without JWT."""
        response = client.get("/masterplans")
        assert response.status_code == 401, (
            f"GET /masterplans returned {response.status_code}. Expected 401."
        )

    def test_create_masterplan_requires_auth(self, client):
        """POST /create_masterplan must return 401 without JWT."""
        response = client.post("/create_masterplan", json={})
        assert response.status_code == 401, (
            f"POST /create_masterplan returned {response.status_code}. Expected 401."
        )

    def test_calc_endpoints_accept_valid_token(self, client, auth_headers):
        """Calc endpoints accept a valid JWT (not 401)."""
        response = client.get("/results", headers=auth_headers)
        assert response.status_code != 401, (
            f"GET /results returned 401 with valid token — auth is broken."
        )

    # --- Bridge nodes now require JWT ---
    def test_bridge_get_nodes_requires_auth(self, client):
        """GET /bridge/nodes must return 401 without JWT."""
        response = client.get("/bridge/nodes")
        assert response.status_code == 401, (
            f"GET /bridge/nodes returned {response.status_code}. Expected 401."
        )

    def test_bridge_post_nodes_requires_auth(self, client):
        """POST /bridge/nodes must return 401 without JWT."""
        response = client.post("/bridge/nodes", json={"content": "test", "permission": {}})
        assert response.status_code == 401, (
            f"POST /bridge/nodes returned {response.status_code}. Expected 401."
        )

    def test_bridge_post_link_requires_auth(self, client):
        """POST /bridge/link must return 401 without JWT."""
        response = client.post("/bridge/link", json={
            "source_id": "00000000-0000-0000-0000-000000000001",
            "target_id": "00000000-0000-0000-0000-000000000002",
        })
        assert response.status_code == 401, (
            f"POST /bridge/link returned {response.status_code}. Expected 401."
        )

    # --- Bridge user_event requires API key ---
    def test_bridge_user_event_requires_api_key(self, client):
        """POST /bridge/user_event must return 401 without API key."""
        response = client.post("/bridge/user_event", json={"user": "x", "origin": "y"})
        assert response.status_code == 401, (
            f"POST /bridge/user_event returned {response.status_code}. Expected 401."
        )

    def test_bridge_user_event_accepts_api_key(self, client, api_key_headers):
        """POST /bridge/user_event must accept a valid API key."""
        response = client.post("/bridge/user_event", json={
            "user": "security_test_user",
            "origin": "pytest",
        }, headers=api_key_headers)
        assert response.status_code == 200, (
            f"POST /bridge/user_event returned {response.status_code} with valid API key."
        )

    # --- Analytics masterplan ownership ---
    def test_analytics_masterplan_requires_auth(self, client):
        """GET /analytics/masterplan/{id} must return 401 without JWT."""
        response = client.get("/analytics/masterplan/1")
        assert response.status_code == 401, (
            f"GET /analytics/masterplan/1 returned {response.status_code}. Expected 401."
        )

    def test_analytics_masterplan_accepts_valid_token(self, client, auth_headers):
        """GET /analytics/masterplan/{id} must not return 401 with valid JWT."""
        response = client.get("/analytics/masterplan/1", headers=auth_headers)
        assert response.status_code != 401, (
            f"GET /analytics/masterplan/1 returned 401 with valid token — auth is broken."
        )

    # --- Memory node ownership ---
    def test_memory_node_get_requires_auth(self, client):
        """GET /memory/nodes/{id} must return 401 without JWT."""
        response = client.get("/memory/nodes/00000000-0000-0000-0000-000000000001")
        assert response.status_code == 401, (
            f"GET /memory/nodes/{id} returned {response.status_code}. Expected 401."
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
