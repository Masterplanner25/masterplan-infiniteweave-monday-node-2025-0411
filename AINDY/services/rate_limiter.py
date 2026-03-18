"""
services/rate_limiter.py — Shared SlowAPI limiter instance.

Defined here (not in main.py) so route modules can import it
without creating circular imports.

Usage in routes:
    from services.rate_limiter import limiter
    from fastapi import Request

    @router.post("/endpoint")
    @limiter.limit("10/minute")
    async def my_route(request: Request, ...):
        ...

The limiter must also be attached to app.state in main.py:
    from services.rate_limiter import limiter
    app.state.limiter = limiter
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
