"""
Shared SlowAPI limiter instance.

Defined here (not in main.py) so route modules can import it
without creating circular imports.

Usage in routes:
    from AINDY.platform_layer.rate_limiter import limiter
    from fastapi import Request

    @router.post("/endpoint")
    @limiter.limit("10/minute")
    async def my_route(request: Request, ...):
        ...

The limiter must also be attached to app.state in main.py:
    from AINDY.platform_layer.rate_limiter import limiter
    app.state.limiter = limiter
"""
import os

from fastapi import Request
from jose import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address


def _identity_key(request: Request) -> str:
    """
    Rate-limit key: authenticated identity when available, IP otherwise.
    - JWT: extracts sub claim from Bearer token without full verification
          (verification happens in get_current_user — this is for bucketing only)
    - Platform key: uses the raw key string as the bucket identity
    - Unauthenticated: falls back to IP address
    """
    try:
        platform_key = (request.headers.get("X-Platform-Key") or "").strip()
        if platform_key:
            return platform_key

        auth_header = (request.headers.get("Authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            if token:
                payload = jwt.decode(
                    token,
                    key="",
                    options={
                        "verify_signature": False,
                        "verify_aud": False,
                        "verify_exp": False,
                    },
                )
                subject = str(payload.get("sub") or "").strip()
                if subject:
                    return subject
    except Exception:
        pass
    return get_remote_address(request)


_test_mode = os.environ.get("TEST_MODE", "false").lower() in ("1", "true", "yes")
limiter = Limiter(
    key_func=_identity_key,
    default_limits=["300/minute"],
    enabled=not _test_mode,
)
