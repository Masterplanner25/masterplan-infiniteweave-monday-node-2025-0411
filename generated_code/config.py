# config.py
"""
Enhanced configuration management with environment-based settings.
Addresses security concerns about hardcoded credentials.
"""
import os
from typing import Dict, Any, Optional
from pydantic import BaseSettings, validator

class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    DATABASE_POOL_SIZE: int = int(os.getenv("DATABASE_POOL_SIZE", "5"))
    DATABASE_MAX_OVERFLOW: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
    
    # Memory System
    USE_RUST_MEMORY: bool = os.getenv("USE_RUST_MEMORY", "true").lower() == "true"
    MEMORY_CACHE_SIZE: int = int(os.getenv("MEMORY_CACHE_SIZE", "1000"))
    ENABLE_MEMORY_PERSISTENCE: bool = os.getenv("ENABLE_MEMORY_PERSISTENCE", "true").lower() == "true"
    
    # API Settings
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_WORKERS: int = int(os.getenv("API_WORKERS", "4"))
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    
    # Caching
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "300"))
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    
    # Performance
    BATCH_PROCESSING_SIZE: int = int(os.getenv("BATCH_PROCESSING_SIZE", "100"))
    MAX_REQUEST_SIZE: int = int(os.getenv("MAX_REQUEST_SIZE", "10485760"))  # 10MB
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @validator("DATABASE_URL")
    def validate_database_url(cls, v):
        if not v:
            raise ValueError("DATABASE_URL must be set")
        return v

# Global settings instance
settings = Settings()