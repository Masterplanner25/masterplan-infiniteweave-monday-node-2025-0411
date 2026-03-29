import os
import logging
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from config import settings

# Configuration
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "aindy_social_layer")
logger = logging.getLogger(__name__)

_client = None


def init_mongo() -> MongoClient:
    """Initialize and verify the singleton MongoDB client eagerly."""
    global _client
    if _client is not None:
        return _client

    mongo_url = settings.MONGO_URL
    if not mongo_url:
        raise RuntimeError("MONGO_URL is required for runtime")

    try:
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        _client = client
        logger.info("Mongo connected successfully")
        return _client
    except PyMongoError as exc:
        _client = None
        raise RuntimeError(
            "Mongo connection failed. Verify MONGO_URL and that the MongoDB server is reachable."
        ) from exc

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
    """
    client = get_mongo_client()
    if client:
        yield client[MONGO_DB_NAME]
        return
    raise RuntimeError("Mongo connection failed. Could not access configured database.")
