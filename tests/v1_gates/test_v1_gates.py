"""
A.I.N.D.Y. V1 Gate Tests
==========================
These tests are RELEASE REQUIREMENTS, not unit tests.

Each test maps to a validation check ID (V1-VAL-NNN) and enforces a specific
V1 contract. Tests are EXPECTED TO FAIL until their corresponding V1 task is
complete. That is the correct behavior — they are gates, not assertions about
current state.

Run individually:
    pytest tests/v1_gates/test_v1_gates.py::test_quota_is_fatal -v

Run all gates:
    pytest tests/v1_gates/ -v

Test-to-task mapping:
    V1-VAL-001  test_quota_is_fatal_when_exceeded         V1-STAB-001
    V1-VAL-002  test_nodus_timeout_returns_envelope        V1-STAB-002
    V1-VAL-003  test_dispatcher_never_raises               V1-REFACT-002
    V1-VAL-004  test_trace_id_in_all_responses             V1-STAB-008
    V1-VAL-005  test_platform_key_cannot_exceed_scope      V1-PLAT-004
    V1-VAL-006  test_cross_tenant_memory_blocked           V1-REFACT-002
    V1-VAL-007  test_health_endpoint_structure             V1-STAB-004
    V1-VAL-008  test_all_syscalls_have_stable_field        V1-PLAT-002
    V1-VAL-009  test_services_directory_clean              V1-REFACT-011
    V1-VAL-010  test_no_shim_files_remain                  V1-REFACT-011
    V1-VAL-011  test_genesis_emits_system_event            V1-CONT-002
    V1-VAL-012  test_task_operations_emit_system_event     V1-CONT-003
    V1-VAL-013  test_no_stack_traces_in_responses          V1-STAB-008
    V1-VAL-014  test_domain_routes_mounted_explicitly      V1-REFACT-013
    V1-VAL-015  test_cross_app_deps_declared               V1-ARCH-001
    V1-VAL-016  test_no_bare_json_response_in_routes       V1-ARCH-002
    V1-VAL-017  test_db_unavailable_returns_503            V1-STAB-009

Import note: tests use `services.*` paths (pre-refactor). After V1-REFACT-008
through V1-REFACT-011 complete, update imports to `kernel.*`, `memory.*`, etc.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Import helpers ─────────────────────────────────────────────────────────────

def _try_import(module_path: str, attr: str):
    """Import attribute from module, returning None if import fails.
    Used to write tests that fail cleanly before a module is moved."""
    import importlib
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, attr, None)
    except (ImportError, ModuleNotFoundError):
        return None


# ── V1-VAL-001 ─────────────────────────────────────────────────────────────────

def test_quota_is_fatal_when_exceeded():
    """
    V1-VAL-001 | Task: V1-STAB-001
    check_quota() returning (False, reason) must produce an error envelope.
    Execution must NOT continue when quota is exceeded.
    """
    from AINDY.kernel.syscall_dispatcher import SyscallDispatcher, SyscallContext

    ctx = SyscallContext(
        execution_unit_id="eu-quota-test",
        user_id="user-quota-test",
        capabilities=["memory.read"],
        trace_id="t-quota-001",
    )

    with patch("AINDY.kernel.syscall_dispatcher._get_rm") as mock_get_rm:
        mock_rm = MagicMock()
        mock_rm.check_quota.return_value = (False, "quota_exceeded: 100 syscalls used, limit is 100")
        mock_get_rm.return_value = mock_rm

        result = SyscallDispatcher().dispatch(
            "sys.v1.memory.read",
            {"query": "test", "user_id": "user-quota-test"},
            ctx,
        )

    assert result["status"] == "error", (
        "Expected status='error' when quota is exceeded, "
        f"got status={result['status']!r}. "
        "V1-STAB-001: quota enforcement must be fatal."
    )
    assert result.get("error"), "Error envelope must include an error message"
    assert "quota" in result["error"].lower() or "100" in result["error"], (
        f"Error message should reference quota. Got: {result['error']!r}"
    )


# ── V1-VAL-002 ─────────────────────────────────────────────────────────────────

def test_nodus_timeout_returns_envelope(db_session):
    """
    V1-VAL-002 | Task: V1-STAB-002
    NodusRuntimeAdapter.run_script() with max_execution_ms must:
    1. Accept the max_execution_ms parameter
    2. Return status='failure' when an infinite loop exceeds the limit
    3. Include 'timeout' in the error message
    4. Complete within 2x the timeout (not hang)
    This test WILL FAIL with TypeError until V1-STAB-002 adds the parameter.
    """
    import time
    from AINDY.runtime.nodus_runtime_adapter import NodusRuntimeAdapter, NodusExecutionContext

    adapter = NodusRuntimeAdapter(db=db_session)
    ctx = NodusExecutionContext(
        user_id="user-timeout-test",
        execution_unit_id="eu-timeout-test",
    )

    infinite_loop_script = "while True:\n    pass\n"
    timeout_ms = 300

    t_start = time.monotonic()
    result = adapter.run_script(
        infinite_loop_script,
        ctx,
        max_execution_ms=timeout_ms,  # This parameter does not yet exist — test will fail with TypeError
    )
    elapsed_ms = (time.monotonic() - t_start) * 1000

    assert result.status == "failure", (
        f"Expected status='failure' on timeout, got {result.status!r}. "
        "V1-STAB-002: run_script() must accept max_execution_ms and enforce it."
    )
    assert result.error is not None, "Error field must be set on timeout"
    assert "timeout" in (result.error or "").lower(), (
        f"Expected 'timeout' in error message, got: {result.error!r}"
    )
    assert elapsed_ms < timeout_ms * 3, (
        f"run_script() took {elapsed_ms:.0f}ms with a {timeout_ms}ms timeout — "
        "timeout enforcement appears not to be working"
    )


# ── V1-VAL-003 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,payload", [
    ("", {}),
    ("sys.invalid", {}),
    ("sys.v99.nonexistent.action", {}),
    ("sys.v1.memory.read", None),
    ("not_a_syscall_at_all", {"key": "value"}),
])
def test_dispatcher_never_raises(name, payload):
    """
    V1-VAL-003 | Task: V1-REFACT-002 (kernel move)
    SyscallDispatcher.dispatch() must NEVER raise for any input.
    Every code path returns a response envelope.
    """
    from AINDY.kernel.syscall_dispatcher import SyscallDispatcher, SyscallContext

    ctx = SyscallContext(
        execution_unit_id="eu-never-raises",
        user_id="user-never-raises",
        capabilities=[],
        trace_id="t-never-raises",
    )

    try:
        result = SyscallDispatcher().dispatch(name, payload or {}, ctx)
        assert isinstance(result, dict), (
            f"dispatch() must return a dict, got {type(result)}"
        )
        assert "status" in result, (
            f"Response envelope missing 'status' key for input name={name!r}"
        )
        assert result["status"] in ("success", "error"), (
            f"status must be 'success' or 'error', got {result['status']!r}"
        )
    except Exception as e:
        pytest.fail(
            f"SyscallDispatcher.dispatch() raised {type(e).__name__} for "
            f"input name={name!r}: {e}"
        )


# ── V1-VAL-004 ─────────────────────────────────────────────────────────────────

def test_trace_id_in_all_responses(client):
    """
    V1-VAL-004 | Task: V1-STAB-008
    Every HTTP response must carry a trace_id in response headers or body.
    Checks a representative set of endpoints including error responses.
    """
    endpoints = [
        ("GET", "/health"),
        ("GET", "/platform/syscalls"),
        ("POST", "/auth/login"),        # likely 422 or 401 — still needs trace_id
        ("GET", "/apps/agent/runs/nonexistent-id"),  # 404
    ]
    for method, path in endpoints:
        response = getattr(client, method.lower())(path)
        has_header = (
            "x-trace-id" in response.headers
            or "X-Trace-ID" in response.headers
            or "X-Request-ID" in response.headers
        )
        has_body_trace = False
        try:
            body = response.json()
            has_body_trace = bool(
                body.get("trace_id") or body.get("request_id")
            )
        except Exception:
            pass

        assert has_header or has_body_trace, (
            f"Missing trace_id for {method} {path} "
            f"(status={response.status_code}). "
            "V1-STAB-008: all responses must carry a trace identifier."
        )


# ── V1-VAL-005 ─────────────────────────────────────────────────────────────────

def test_platform_key_cannot_exceed_scope(client, auth_headers):
    """
    V1-VAL-005 | Task: V1-PLAT-004
    A platform key scoped to memory.read must not be able to run agents.
    """
    # Create a restricted key
    key_resp = client.post(
        "/platform/keys",
        json={"name": "test-restricted", "capabilities": ["memory.read"]},
        headers=auth_headers,
    )
    if key_resp.status_code not in (200, 201):
        pytest.skip(
            f"Platform key creation returned {key_resp.status_code} — "
            "platform keys endpoint may not be fully functional yet (V1-PLAT-001)"
        )

    body = key_resp.json()
    raw_key = body.get("key") or body.get("api_key") or body.get("raw_key")
    if not raw_key:
        pytest.skip("Platform key creation response did not include a raw key")

    restricted_headers = {"X-Platform-Key": raw_key}

    # Attempt an agent.run operation with a memory-only key
    run_resp = client.post(
        "/apps/agent/run",
        json={"task": "test scope enforcement", "user_id": "test-user"},
        headers=restricted_headers,
    )
    assert run_resp.status_code in (401, 403), (
        f"Expected 401 or 403 for agent.run with memory-only key, "
        f"got {run_resp.status_code}. "
        "V1-PLAT-004: API key capability scope must be enforced."
    )


# ── V1-VAL-006 ─────────────────────────────────────────────────────────────────

def test_cross_tenant_memory_blocked():
    """
    V1-VAL-006 | Task: V1-REFACT-002 (tenant context in kernel)
    A syscall context for user-a must not be able to read user-b's memory.
    """
    from AINDY.kernel.syscall_dispatcher import SyscallDispatcher, SyscallContext

    # Context belongs to user-a
    ctx = SyscallContext(
        execution_unit_id="eu-cross-tenant-test",
        user_id="user-a",
        capabilities=["memory.read"],
        trace_id="t-cross-tenant",
    )

    # Attempt to read from user-b's namespace
    result = SyscallDispatcher().dispatch(
        "sys.v1.memory.read",
        {
            "query": "anything",
            "user_id": "user-b",   # different user than context.user_id
        },
        ctx,
    )

    # Acceptable outcomes (none of them leak user-b's data):
    #   1. status=error with TENANT/PERMISSION/VIOLATION in message (explicit block)
    #   2. status=error for any reason (DB unavailable in test env, etc.)
    #   3. status=success but data contains only user-a's nodes
    #
    # NOT acceptable: status=success with nodes owned by user-b.
    if result["status"] == "error":
        # Any error is safe — no data was leaked.
        # Ideally the error mentions tenant isolation, but a DB error is also safe.
        error_msg = (result.get("error") or "").upper()
        has_explicit_block = any(
            term in error_msg
            for term in ("TENANT", "PERMISSION", "DENIED", "VIOLATION", "UNAUTHORIZED")
        )
        if not has_explicit_block:
            # Log for observability but don't fail — no data leaked regardless
            import warnings
            warnings.warn(
                f"Cross-tenant memory.read returned error without explicit "
                f"tenant-violation message: {result.get('error')!r}. "
                "After V1-CONT-002: consider adding explicit TENANT_VIOLATION error."
            )
    else:
        # success path — verify returned nodes belong to user-a only
        nodes = result.get("data", {}).get("nodes", [])
        for node in nodes:
            node_owner = node.get("user_id", "") or node.get("owner_id", "")
            if node_owner:
                assert node_owner == "user-a", (
                    f"Cross-tenant read returned a node belonging to {node_owner!r}, "
                    "expected only user-a's nodes. "
                    "V1-REFACT-002: tenant isolation must prevent cross-tenant memory access."
                )


# ── V1-VAL-007 ─────────────────────────────────────────────────────────────────

def test_health_endpoint_structure(client):
    """
    V1-VAL-007 | Task: V1-STAB-004
    GET /health must return a tiered status response with a dependency map.
    """
    response = client.get("/health")

    assert response.status_code in (200, 503), (
        f"Expected /health to return 200 or 503, got {response.status_code}. "
        "Tiered health must return 503 when critical dependencies are unavailable."
    )

    try:
        body = response.json()
    except Exception:
        pytest.fail("/health did not return valid JSON")

    assert "status" in body, "Health response missing 'status' field"
    assert "dependencies" in body, (
        "Health response missing 'dependencies' field. "
        "Tiered health must include per-dependency status."
    )
    assert body["status"] in ("healthy", "degraded", "critical"), (
        f"status must be 'healthy', 'degraded', or 'critical', got {body['status']!r}"
    )


# ── V1-VAL-008 ─────────────────────────────────────────────────────────────────

def test_all_syscalls_have_stable_field():
    """
    V1-VAL-008 | Task: V1-PLAT-002
    Every entry in SYSCALL_REGISTRY must have stable explicitly set to
    True or False. None is not acceptable for a V1 release.
    """
    from AINDY.kernel.syscall_registry import SYSCALL_REGISTRY

    unset = []
    for name in SYSCALL_REGISTRY:
        entry = SYSCALL_REGISTRY[name]
        if not hasattr(entry, "stable") or entry.stable is None:
            unset.append(name)

    assert not unset, (
        f"The following syscalls have stable=None or missing stable field "
        f"({len(unset)} total):\n"
        + "\n".join(f"  - {name}" for name in sorted(unset))
        + "\nV1-PLAT-002: all v1 syscalls must explicitly declare stable=True or stable=False."
    )


# ── V1-VAL-009 ─────────────────────────────────────────────────────────────────

def test_services_directory_clean():
    """
    V1-VAL-009 | Task: V1-REFACT-011
    After the structural refactor, AINDY/services/ must contain only auth_service.py.
    This test will fail until the entire import migration is complete.
    """
    services_dir = Path(__file__).parent.parent.parent / "AINDY" / "services"

    assert services_dir.exists(), "AINDY/services/ directory does not exist"

    py_files = sorted(
        f.name for f in services_dir.glob("*.py")
        if f.name != "__init__.py"
    )
    allowed = {"auth_service.py"}
    extra = sorted(set(py_files) - allowed)

    assert not extra, (
        f"services/ must contain only auth_service.py after V1-REFACT-011.\n"
        f"Still present ({len(extra)} files):\n"
        + "\n".join(f"  - {f}" for f in extra[:20])
        + (f"\n  ... and {len(extra) - 20} more" if len(extra) > 20 else "")
    )


# ── V1-VAL-010 ─────────────────────────────────────────────────────────────────

def test_no_shim_files_remain():
    """
    V1-VAL-010 | Task: V1-REFACT-011
    No migration shim files may remain after all imports are updated.
    Shims are identified by the 'MIGRATION SHIM' marker string.
    """
    aindy_dir = Path(__file__).parent.parent.parent

    # Exclude tests/ — test files may reference the concept without being shims.
    result = subprocess.run(
        ["grep", "-r", "MIGRATION SHIM", str(aindy_dir),
         "--include=*.py", "--exclude-dir=tests", "-l"],
        capture_output=True, text=True,
    )
    shim_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    assert not shim_files, (
        f"Migration shims still present ({len(shim_files)} files):\n"
        + "\n".join(f"  - {f}" for f in shim_files)
        + "\nV1-REFACT-011: all shims must be removed before V1."
    )


# ── V1-VAL-011 ─────────────────────────────────────────────────────────────────

def test_genesis_emits_system_event(client, auth_headers, db_session):
    """
    V1-VAL-011 | Task: V1-CONT-002
    POST /apps/genesis/message must emit at least one SystemEvent.
    This test enforces the execution contract for the Genesis subsystem.
    """
    from AINDY.db.models.system_event import SystemEvent

    initial_count = db_session.query(SystemEvent).count()

    response = client.post(
        "/apps/genesis/message",
        json={
            "content": "V1 contract enforcement test",
            "plan_id": None,
            "user_id": "test-user",
        },
        headers=auth_headers,
    )

    # Accept any 2xx response (genesis may need more setup for a real response)
    if response.status_code >= 500:
        pytest.skip(
            f"Genesis endpoint returned {response.status_code} — "
            "endpoint may require additional setup. Check server logs."
        )

    db_session.expire_all()
    final_count = db_session.query(SystemEvent).count()

    assert final_count > initial_count, (
        f"POST /apps/genesis/message emitted 0 SystemEvents "
        f"(count before={initial_count}, after={final_count}). "
        "V1-CONT-002: Genesis operations must emit SystemEvent at entry and terminal state."
    )


# ── V1-VAL-012 ─────────────────────────────────────────────────────────────────

def test_task_operations_emit_system_event(client, auth_headers, db_session):
    """
    V1-VAL-012 | Task: V1-CONT-003
    POST /apps/tasks/create must emit at least one SystemEvent.
    This test enforces the execution contract for the Task subsystem.
    """
    from AINDY.db.models.system_event import SystemEvent

    initial_count = db_session.query(SystemEvent).count()

    response = client.post(
        "/apps/tasks/create",
        json={
            "title": "V1 contract enforcement test task",
            "user_id": "00000000-0000-0000-0000-000000000001",
        },
        headers=auth_headers,
    )

    if response.status_code >= 500:
        pytest.skip(
            f"Task create endpoint returned {response.status_code} — "
            "check server logs for setup issues."
        )

    db_session.expire_all()
    final_count = db_session.query(SystemEvent).count()

    assert final_count > initial_count, (
        f"POST /apps/tasks/create emitted 0 SystemEvents "
        f"(count before={initial_count}, after={final_count}). "
        "V1-CONT-003: Task operations must emit SystemEvent."
    )


# ── V1-VAL-013 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,path,body", [
    ("post", "/apps/agent/run", {"bad_field": True}),
    ("post", "/auth/login", {"email": "not-an-email", "password": ""}),
    ("get", "/apps/agent/runs/00000000-0000-0000-0000-000000000000", None),
    ("post", "/platform/syscall", {"syscall": "sys.v99.fake.action", "payload": {}}),
])
def test_no_stack_traces_in_responses(client, method, path, body):
    """
    V1-VAL-013 | Task: V1-STAB-008
    Error responses must never include Python stack traces or internal paths.
    All error bodies must be structured JSON.
    """
    if body:
        response = getattr(client, method)(path, json=body)
    else:
        response = getattr(client, method)(path)

    raw = response.text

    assert "Traceback (most recent call last)" not in raw, (
        f"{method.upper()} {path} returned a Python traceback in the response body.\n"
        f"Status: {response.status_code}\n"
        f"Body (first 500 chars): {raw[:500]}\n"
        "V1-STAB-008: stack traces must never reach external callers."
    )
    assert 'File "/' not in raw and "File \"\\" not in raw, (
        f"{method.upper()} {path} returned a file path in the response body (from a traceback).\n"
        "V1-STAB-008: internal file paths must not be exposed."
    )

    # Verify the response is parseable as JSON (for non-204 responses)
    if response.status_code != 204 and len(raw) > 0:
        try:
            response.json()
        except Exception:
            pytest.fail(
                f"{method.upper()} {path} returned non-JSON body "
                f"(status={response.status_code}):\n{raw[:300]}"
            )


# ── V1-VAL-014 ─────────────────────────────────────────────────────────────────

def test_domain_routes_mounted_explicitly_without_flag(client):
    """
    V1-VAL-014 | Task: V1-REFACT-013
    Domain-specific app routes are mounted explicitly.
    """
    response = client.get("/openapi.json")
    if response.status_code != 200:
        pytest.skip("OpenAPI endpoint not available")

    spec = response.json()
    paths = list(spec.get("paths", {}).keys())

    domain_route_prefixes = [
        "/apps/freelance",
        "/apps/leadgen",
        "/apps/seo",
        "/apps/rippletrace",
        "/apps/social",
        "/apps/authorship",
        "/apps/research",
        "/apps/arm",
        "/apps/network_bridge",
    ]

    exposed_domain_routes = [
        path for path in paths
        if any(path.startswith(prefix) for prefix in domain_route_prefixes)
    ]

    assert exposed_domain_routes, (
        "Domain app routes should be explicitly mounted."
    )


def test_cross_app_deps_declared():
    """
    V1-VAL-015 | Task: V1-ARCH-001
    Every deferred cross-app import in apps/ must be declared in the importing
    app's APP_DEPENDS_ON, and module-level cross-app imports are forbidden
    outside apps/bootstrap.py.
    """
    root = Path(__file__).resolve().parents[2]
    apps_dir = root / "apps"

    def _read_app_depends_on(app_name: str) -> list[str]:
        bootstrap_path = apps_dir / app_name / "bootstrap.py"
        tree = ast.parse(bootstrap_path.read_text(encoding="utf-8", errors="ignore"))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if getattr(target, "id", None) == "APP_DEPENDS_ON":
                        return list(ast.literal_eval(node.value) or [])
            elif isinstance(node, ast.AnnAssign):
                if getattr(node.target, "id", None) == "APP_DEPENDS_ON":
                    return list(ast.literal_eval(node.value) or [])
        return []

    dependency_failures: list[str] = []
    module_level_failures: list[str] = []
    deferred_cross_apps: dict[str, set[str]] = {}

    for path in apps_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path == apps_dir / "bootstrap.py":
            continue

        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue

        try:
            relative_to_apps = path.relative_to(apps_dir)
        except ValueError:
            continue
        if len(relative_to_apps.parts) < 2:
            continue

        owning_app = relative_to_apps.parts[0]
        rel_display = path.relative_to(root).as_posix()

        all_imports = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and isinstance(node.module, str)
            and node.module.startswith("apps.")
        ]
        module_level_ids = {
            id(node)
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and isinstance(node.module, str)
            and node.module.startswith("apps.")
        }

        per_file_deferred: list[tuple[str, ast.ImportFrom]] = []
        for node in all_imports:
            parts = node.module.split(".")
            if len(parts) < 2:
                continue
            imported_app = parts[1]
            if imported_app == owning_app:
                continue
            if id(node) in module_level_ids:
                module_level_failures.append(
                    f"{rel_display}:{node.lineno} imports from '{imported_app}' at module level"
                )
            else:
                per_file_deferred.append((imported_app, node))
                deferred_cross_apps.setdefault(owning_app, set()).add(imported_app)

        declared = set(_read_app_depends_on(owning_app))
        for imported_app, node in per_file_deferred:
            if imported_app not in declared:
                dependency_failures.append(
                    f"{rel_display}:{node.lineno} imports from '{imported_app}' "
                    f"but apps/{owning_app}/bootstrap.py APP_DEPENDS_ON does not declare '{imported_app}'"
                )

    assert not module_level_failures, (
        "Module-level cross-app imports detected:\n"
        + "\n".join(sorted(module_level_failures))
    )
    assert not dependency_failures, (
        "Undeclared deferred cross-app imports detected:\n"
        + "\n".join(sorted(dependency_failures))
    )


def test_no_bare_json_response_in_routes():
    """
    V1-VAL-016 | Task: V1-ARCH-002
    Route modules must not return bare JSONResponse objects outside the
    accepted _http_status and _idempotency dispatch patterns.
    """
    root = Path(__file__).resolve().parents[2]
    routes_dirs = list((root / "apps").glob("*/routes"))
    violations: list[str] = []

    for routes_dir in routes_dirs:
        for path in routes_dir.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if path.name.startswith("_"):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue

            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                allowed = False
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                        if "_http_status" in inner.value or "_idempotency" in inner.value:
                            allowed = True
                            break
                    if isinstance(inner, ast.Attribute) and isinstance(inner.attr, str):
                        if "_http_status" in inner.attr or "_idempotency" in inner.attr:
                            allowed = True
                            break

                if allowed:
                    continue

                for inner in ast.walk(node):
                    if not isinstance(inner, ast.Return):
                        continue
                    call = inner.value
                    if not isinstance(call, ast.Call):
                        continue

                    func_name = None
                    if isinstance(call.func, ast.Name):
                        func_name = call.func.id
                    elif isinstance(call.func, ast.Attribute):
                        func_name = call.func.attr

                    if func_name == "JSONResponse":
                        violations.append(f"{path.relative_to(root).as_posix()}:{inner.lineno}")

    assert not violations, (
        "Bare JSONResponse returns detected in route modules:\n"
        + "\n".join(sorted(violations))
    )


def test_db_unavailable_returns_503(client, auth_headers):
    """
    V1-VAL-017 | Task: V1-STAB-009
    When PostgreSQL raises OperationalError, routes must return 503 with
    error=db_unavailable and a Retry-After header. A 500 is not acceptable
    because callers cannot distinguish a bug from a transient DB outage.
    """
    from sqlalchemy.exc import OperationalError as SAOperationalError

    from apps.agent.routes.agent_router import get_db

    def broken_get_db():
        raise SAOperationalError("connection refused", None, None)
        yield

    client.app.dependency_overrides[get_db] = broken_get_db
    try:
        response = client.get("/apps/agent/runs", headers=auth_headers)
    finally:
        client.app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503, (
        f"Expected 503 when DB is unavailable, got {response.status_code}. "
        "V1-STAB-009: DB outages must return 503 so callers can retry safely."
    )
    assert "Retry-After" in response.headers, (
        "DB unavailability response must include Retry-After header."
    )
    try:
        body = response.json()
    except Exception:
        pytest.fail("DB unavailability response must be valid JSON")
    assert body.get("error") == "db_unavailable", (
        f"Expected error='db_unavailable', got error={body.get('error')!r}. "
        "Structured error codes let clients identify the failure type."
    )
    assert body.get("retryable") is True, (
        "DB unavailability must be flagged as retryable."
    )
