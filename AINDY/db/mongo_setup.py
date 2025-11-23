import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration (Defaults to local if not set in .env)
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "aindy_social_layer")

_client = None

def get_mongo_client():
    """
    Singleton pattern to create a single MongoDB client instance.
    Prevents creating multiple expensive connections.
    """
    global _client
    if _client is None:
        try:
            # Create client with a 5-second timeout so it doesn't hang if Mongo is down
            _client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
            
            # The 'server_info' call forces a connection check
            _client.server_info()
            print(f"✅ [MongoDB] Connected to database: {MONGO_DB_NAME}")
        except Exception as e:
            print(f"❌ [MongoDB] Connection failed: {e}")
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