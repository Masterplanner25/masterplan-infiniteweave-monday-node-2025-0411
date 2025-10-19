# routes/db_verify_router.py
from fastapi import APIRouter
from sqlalchemy import inspect
from config import engine

router = APIRouter(prefix="/db", tags=["Database Verification"])

@router.get("/verify")
def verify_database_schema():
    """
    Returns a live inspection of database tables and column types.
    Especially useful after Alembic migrations.
    """
    insp = inspect(engine)
    result = {}

    for table_name in insp.get_table_names():
        columns = insp.get_columns(table_name)
        result[table_name] = [
            {"name": col["name"], "type": str(col["type"]), "nullable": col["nullable"]}
            for col in columns
        ]

    return {"database_schema": result}
