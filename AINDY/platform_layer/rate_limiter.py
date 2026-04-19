"""
services/rate_limiter.py â€” Shared SlowAPI limiter instance.

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

from slowapi import Limiter
from slowapi.util import get_remote_address

_test_mode = os.environ.get("TEST_MODE", "false").lower() in ("1", "true", "yes")
limiter = Limiter(key_func=get_remote_address, enabled=not _test_mode)
