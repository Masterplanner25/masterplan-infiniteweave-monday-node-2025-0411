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
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=settings.MONGO_HEALTH_TIMEOUT_MS)
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

def get_mongo_client():
    """
    Singleton pattern to create a single MongoDB client instance.
    Prevents creating multiple expensive connections.
    """
    global _client
    if _client is None:
        return init_mongo()
    return _client

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
