from __future__ import annotations

from jose import jwt
from starlette.requests import Request

from AINDY.platform_layer.rate_limiter import _identity_key


def _request(headers: list[tuple[bytes, bytes]] | None = None, host: str = "127.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "client": (host, 12345),
    }
    return Request(scope)


def test_identity_key_uses_jwt_sub_claim() -> None:
    token = jwt.encode({"sub": "user-123"}, "test-secret", algorithm="HS256")
    request = _request(headers=[(b"authorization", f"Bearer {token}".encode("utf-8"))])

    assert _identity_key(request) == "user-123"


def test_identity_key_uses_platform_key_header() -> None:
    request = _request(headers=[(b"x-platform-key", b"aindy_test_key")])

    assert _identity_key(request) == "aindy_test_key"


def test_identity_key_falls_back_to_ip() -> None:
    request = _request(host="10.1.2.3")

    assert _identity_key(request) == "10.1.2.3"
