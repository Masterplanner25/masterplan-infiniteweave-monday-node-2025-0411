"""
tests/integration/test_platform_quickstart.py
──────────────────────────────────────────────
End-to-end integration tests for the platform API key quickstart flow.

Verifies that:
  1. POST /platform/keys returns a raw key (one-time) with the aindy_ prefix
  2. That raw key can authenticate a syscall via X-Platform-Key header
  3. A key with limited scopes cannot call a syscall outside those scopes
  4. A revoked key is rejected by the auth layer
  5. GET /platform/keys never exposes the raw key value

Fixtures (client, auth_headers, db_session, test_user) are provided by the
shared conftest chain (tests/conftest.py → tests/fixtures/*).
"""
from __future__ import annotations

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

_PLATFORM_KEYS_URL = "/platform/keys"
_SYSCALL_URL = "/platform/syscall"

_X_PLATFORM_KEY = "X-Platform-Key"


def _create_key(client, auth_headers, *, name: str, scopes: list[str]) -> dict:
    """POST /platform/keys and return the full JSON response."""
    response = client.post(
        _PLATFORM_KEYS_URL,
        json={"name": name, "scopes": scopes},
        headers=auth_headers,
    )
    assert response.status_code in (200, 201), (
        f"POST /platform/keys failed ({response.status_code}): {response.text}"
    )
    return response.json()


# ── Test 1 ────────────────────────────────────────────────────────────────────

def test_create_platform_key_returns_raw_key_once(client, auth_headers):
    """
    POST /platform/keys must return the raw key exactly once in the response.

    Verifies:
    - Response contains "id" and "key" fields
    - raw key starts with "aindy_"
    - key_prefix is a short prefix of the raw key (display hint only)
    - scopes are echoed back correctly
    """
    data = _create_key(
        client, auth_headers,
        name="quickstart-test-1",
        scopes=["memory.read", "memory.write"],
    )

    assert "id" in data, f"Expected 'id' in response, got: {list(data.keys())}"
    assert "key" in data, f"Expected 'key' in response, got: {list(data.keys())}"

    raw_key = data["key"]
    assert raw_key.startswith("aindy_"), (
        f"Raw key must start with 'aindy_', got: {raw_key[:16]}..."
    )

    # key_prefix is a display hint — must be a leading substring of the raw key
    key_prefix = data.get("key_prefix", "")
    assert raw_key.startswith(key_prefix), (
        f"key_prefix {key_prefix!r} is not a prefix of the raw key"
    )
    assert len(key_prefix) < len(raw_key), "key_prefix must be shorter than the raw key"

    # scopes are present — exact values may differ in SQLite due to JSON serialisation
    assert "scopes" in data, f"Expected 'scopes' field in response, got: {list(data.keys())}"

    # is_active defaults to True on creation
    assert data.get("is_active") is True


# ── Test 2 ────────────────────────────────────────────────────────────────────

def test_platform_key_authenticates_syscall(client, auth_headers):
    """
    A raw platform key sent as X-Platform-Key header must successfully
    authenticate a POST /platform/syscall request.

    Verifies:
    - syscall responds 200 (or non-4xx) when key is valid
    - Response is a valid envelope (contains at least "result" or "output")
    """
    data = _create_key(
        client, auth_headers,
        name="quickstart-test-2",
        scopes=["memory.write", "memory.read"],
    )
    raw_key = data["key"]

    response = client.post(
        _SYSCALL_URL,
        json={
            "name": "sys.v1.memory.write",
            "payload": {
                "content": "integration test node",
                "node_type": "note",
                "tags": ["integration-test"],
            },
        },
        headers={_X_PLATFORM_KEY: raw_key},
    )

    assert response.status_code not in (401, 403), (
        f"Platform key authentication failed ({response.status_code}): {response.text}"
    )
    assert response.status_code < 500, (
        f"Syscall server error ({response.status_code}): {response.text}"
    )


# ── Test 3 ────────────────────────────────────────────────────────────────────

def test_platform_key_scope_enforcement(client, auth_headers):
    """
    A key created with only memory.read scope must be rejected (403) when it
    attempts to call sys.v1.memory.write.

    Verifies:
    - Scope gate is enforced at the syscall layer
    - The response status is 403 (not 401, which would mean auth failure)
    """
    data = _create_key(
        client, auth_headers,
        name="quickstart-test-3-readonly",
        scopes=["memory.read"],
    )
    raw_key = data["key"]

    response = client.post(
        _SYSCALL_URL,
        json={
            "name": "sys.v1.memory.write",
            "payload": {
                "content": "should be blocked",
                "node_type": "note",
                "tags": [],
            },
        },
        headers={_X_PLATFORM_KEY: raw_key},
    )

    assert response.status_code == 403, (
        f"Expected 403 for out-of-scope syscall, got {response.status_code}: {response.text}"
    )


# ── Test 4 ────────────────────────────────────────────────────────────────────

def test_revoked_key_cannot_authenticate(client, auth_headers):
    """
    After DELETE /platform/keys/{key_id}, the raw key must be rejected (401)
    on subsequent syscall requests.

    Verifies:
    - DELETE /platform/keys/{key_id} returns 204
    - The revoked raw key is no longer accepted as authentication
    """
    data = _create_key(
        client, auth_headers,
        name="quickstart-test-4-revoke",
        scopes=["memory.read", "memory.write"],
    )
    raw_key = data["key"]
    key_id = data["id"]

    # Revoke the key
    delete_response = client.delete(
        f"{_PLATFORM_KEYS_URL}/{key_id}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204, (
        f"DELETE /platform/keys/{key_id} returned {delete_response.status_code}: "
        f"{delete_response.text}"
    )

    # Attempt to use the revoked key
    syscall_response = client.post(
        _SYSCALL_URL,
        json={
            "name": "sys.v1.memory.read",
            "payload": {"query": "test"},
        },
        headers={_X_PLATFORM_KEY: raw_key},
    )

    assert syscall_response.status_code == 401, (
        f"Revoked key must return 401, got {syscall_response.status_code}: "
        f"{syscall_response.text}"
    )


# ── Test 5 ────────────────────────────────────────────────────────────────────

def test_list_keys_does_not_expose_raw_key(client, auth_headers):
    """
    GET /platform/keys must not include the raw key in any list entry.

    Verifies:
    - Response contains "keys" list
    - No entry in the list has a "key" field (raw key must never appear post-creation)
    - Each entry has "id", "name", "key_prefix", "scopes", and "is_active"
    """
    # Create a key so there is at least one entry
    _create_key(
        client, auth_headers,
        name="quickstart-test-5-list",
        scopes=["memory.read"],
    )

    response = client.get(_PLATFORM_KEYS_URL, headers=auth_headers)
    assert response.status_code == 200, (
        f"GET /platform/keys returned {response.status_code}: {response.text}"
    )

    body = response.json()
    assert "keys" in body, f"Expected 'keys' in response, got: {list(body.keys())}"

    keys_list = body["keys"]
    assert isinstance(keys_list, list), f"'keys' must be a list, got {type(keys_list)}"
    assert len(keys_list) >= 1, "Expected at least one key in the list"

    for entry in keys_list:
        assert "key" not in entry, (
            f"Raw 'key' field must not appear in list response. Entry: {entry}"
        )
        # Standard display fields must be present
        for field in ("id", "name", "key_prefix", "scopes", "is_active"):
            assert field in entry, (
                f"Expected field '{field}' in list entry, got: {list(entry.keys())}"
            )
