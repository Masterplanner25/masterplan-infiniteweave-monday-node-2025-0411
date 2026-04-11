"""
verify_env_config.py – Full-stack diagnostic for A.I.N.D.Y.
Checks environment configuration, DB connection, Alembic metadata sync,
and FastAPI runtime endpoint availability.

Usage:
    python verify_env_config.py
"""

import os
import sys
import time
import requests
from sqlalchemy import create_engine, text
from AINDY.alembic.config import Config as AlembicConfig
from AINDY.alembic import command

# Ensure local imports work
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from AINDY.config import settings
from AINDY.db.database import Base


# ------------------------------------------------------
# ENVIRONMENT CONSISTENCY
# ------------------------------------------------------
def check_env_consistency():
    print("\n🧩 ENVIRONMENT CONSISTENCY CHECK")
    print("--------------------------------------")
    print(f"ENV: {settings.ENV}")
    print(f"DATABASE_URL: {settings.DATABASE_URL}")
    print(f"PERMISSION_SECRET: {'✅ set' if settings.PERMISSION_SECRET else '❌ missing'}")
    print(f"OpenAI Key: {'✅ set' if settings.OPENAI_API_KEY else '⚠️ not set'}")
    print(f"Loaded from: {settings.__config__.env_file}\n")


# ------------------------------------------------------
# DATABASE CONNECTION
# ------------------------------------------------------
def check_database_connection():
    print("🧠 DATABASE CONNECTION TEST")
    print("--------------------------------------")
    try:
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version();")).scalar()
            print(f"✅ Connected successfully: {version}")
        print()
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}\n")
        return False


# ------------------------------------------------------
# ALEMBIC METADATA SYNC
# ------------------------------------------------------
def check_alembic_metadata():
    print("📜 ALEMBIC METADATA SYNC CHECK")
    print("--------------------------------------")
    try:
        alembic_cfg = AlembicConfig("alembic.ini")
        tables = [t.name for t in Base.metadata.sorted_tables]
        print(f"Detected {len(tables)} tables: {tables}")
        print("Running Alembic autogenerate dry run (no file created)...")
        command.revision(
            alembic_cfg, message="verify_metadata_sync", autogenerate=True, head="head", sql=True
        )
        print("✅ Alembic metadata check completed\n")
    except Exception as e:
        print(f"❌ Alembic metadata sync failed: {e}\n")


# ------------------------------------------------------
# FASTAPI RUNTIME ENDPOINT
# ------------------------------------------------------
def check_fastapi_endpoint(url: str = "http://127.0.0.1:8000/"):
    print("🌐 FASTAPI ENDPOINT CHECK")
    print("--------------------------------------")
    try:
        print("Waiting 2 seconds for local server startup (if running in another terminal)...")
        time.sleep(2)
        response = requests.get(url, timeout=5)
        if response.status_code == 200 and "A.I.N.D.Y" in response.text:
            print(f"✅ FastAPI endpoint reachable: {url}")
            print(f"Response: {response.json()}")
        else:
            print(f"⚠️ FastAPI responded but unexpected data: {response.status_code}")
            print(f"Body: {response.text}")
        print()
    except requests.ConnectionError:
        print(f"❌ Could not connect to FastAPI at {url}. Is the server running?\n")
    except Exception as e:
        print(f"❌ FastAPI endpoint check failed: {e}\n")


# ------------------------------------------------------
# MAIN EXECUTION
# ------------------------------------------------------
def main():
    print("\n=== 🔍 A.I.N.D.Y. FULL-STACK DIAGNOSTIC ===")
    check_env_consistency()

    db_ok = check_database_connection()
    if db_ok:
        check_alembic_metadata()

    # FastAPI check always last
    check_fastapi_endpoint()
    print("=== ✅ Verification complete ===\n")


if __name__ == "__main__":
    main()
