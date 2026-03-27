import os
import logging
from pymongo import MongoClient

# Configuration
MONGO_URL = os.getenv("MONGO_URL")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "aindy_social_layer")
logger = logging.getLogger(__name__)

_client = None

def get_mongo_client():
    """
    Singleton pattern to create a single MongoDB client instance.
    Prevents creating multiple expensive connections.
    """
    global _client
    if _client is None:
        if not MONGO_URL:
            raise RuntimeError("MONGO_URL is not configured")
        try:
            _client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
            _client.server_info()
            logger.info("Connected to MongoDB database %s", MONGO_DB_NAME)
        except Exception as e:
            logger.error("MongoDB connection failed: %s", e)
            _client = None
    return _client

def get_mongo_db():
    """
    FastAPI Dependency to yield the specific database object.
    Use this in your routes: 
    def my_route(db = Depends(get_mongo_db)): ...
    """
    client = get_mongo_client()
    if client:
        # Return the specific database object
        yield client[MONGO_DB_NAME]
    else:
        raise RuntimeError("Could not connect to MongoDB.")
