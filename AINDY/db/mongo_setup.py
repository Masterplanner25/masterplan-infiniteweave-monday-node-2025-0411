import os
import logging
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from AINDY.config import settings
from AINDY.platform_layer.metrics import mongo_health_status

# Configuration
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "aindy_default")
logger = logging.getLogger(__name__)

_client = None


def ensure_mongo_ready(*, required: bool | None = None) -> MongoClient | None:
    """Initialize Mongo when available and enforce fail-fast only when required."""
    global _client
    if _client is not None:
        mongo_health_status.set(1)
        return _client

    mongo_required = settings.MONGO_REQUIRED if required is None else required
    mongo_url = settings.MONGO_URL
    if settings.SKIP_MONGO_PING:
        _client = None
        mongo_health_status.set(0)
        if mongo_required and not settings.is_testing:
            raise RuntimeError(
                "Mongo is required but SKIP_MONGO_PING is enabled. "
                "Disable the skip flag or provide a reachable MONGO_URL."
            )
        logger.warning("Skipping Mongo connection (SKIP_MONGO_PING enabled)")
        return _client

    if not mongo_url:
        _client = None
        mongo_health_status.set(0)
        if mongo_required:
            raise RuntimeError("Mongo is required but MONGO_URL is not configured")
        logger.warning("Mongo is not configured; continuing without Mongo-backed features")
        return _client

    try:
        client = MongoClient(
            mongo_url,
            connectTimeoutMS=settings.MONGO_CONNECT_TIMEOUT_MS,
            socketTimeoutMS=settings.MONGO_SOCKET_TIMEOUT_MS,
            serverSelectionTimeoutMS=settings.MONGO_SERVER_SELECTION_TIMEOUT_MS,
            maxPoolSize=settings.MONGO_MAX_POOL_SIZE,
            minPoolSize=settings.MONGO_MIN_POOL_SIZE,
        )
        client.admin.command("ping")
        _client = client
        mongo_health_status.set(1)
        logger.info("Mongo connected successfully")
        return _client
    except PyMongoError as exc:
        _client = None
        mongo_health_status.set(0)
        if mongo_required:
            raise RuntimeError(
                "Mongo connection failed. Verify MONGO_URL and that the MongoDB server is reachable."
            ) from exc
        logger.warning("Mongo unavailable; continuing without Mongo-backed features: %s", exc)
        return _client


def init_mongo(*, required: bool | None = None) -> MongoClient | None:
    """Backward-compatible startup entrypoint."""
    return ensure_mongo_ready(required=required)


def close_mongo_client() -> None:
    """Close the process-level MongoDB client if one was opened.

    Safe to call multiple times — no-ops if no client is open.
    """
    global _client
    if _client is None:
        return
    try:
        _client.close()
        logger.info("MongoDB client closed.")
    except Exception as exc:
        logger.warning("MongoDB client close failed (non-fatal): %s", exc)
    finally:
        _client = None


shutdown_mongo = close_mongo_client

def get_mongo_client():
    """
    Singleton pattern to create a single MongoDB client instance.
    Prevents creating multiple expensive connections.
    """
    global _client
    if _client is None:
        return init_mongo()
    return _client


def ping_mongo() -> dict:
    """
    Returns MongoDB reachability without raising.
    """
    try:
        if _client is None:
            if not settings.MONGO_URL:
                return {"status": "degraded", "reason": "mongo not configured"}
            return {"status": "degraded", "reason": "mongo client not initialized"}
        _client.admin.command("ping")
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "degraded", "reason": str(exc)}


def get_mongo_db():
    """
    FastAPI Dependency to yield the specific database object.
    Use this in your routes:
        def my_route(db = Depends(get_mongo_db)): ...

    Raises HTTP 503 (not RuntimeError) when Mongo is unavailable or skipped,
    so the error surfaces as a structured API response rather than a 500
    traceback, and routes that do not depend on Mongo are not affected.
    """
    from fastapi import HTTPException
    client = get_mongo_client()
    if client:
        yield client[MONGO_DB_NAME]
        return
    raise HTTPException(
        status_code=503,
        detail=(
            "MongoDB is not available. "
            "Set MONGO_URL and ensure the server is reachable, "
            "or set SKIP_MONGO_PING=true only in non-production environments."
        ),
    )


def get_optional_mongo_db():
    """
    Yield the configured Mongo database when available, otherwise yield None.
    Intended for graceful-degradation routes that must not fail the request.
    """
    client = get_mongo_client()
    if client:
        yield client[MONGO_DB_NAME]
        return
    yield None
