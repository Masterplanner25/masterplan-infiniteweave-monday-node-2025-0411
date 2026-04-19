# routes/db_verify_router.py
from fastapi import APIRouter, Depends, Request
from sqlalchemy import inspect
from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import engine
from AINDY.services.auth_service import verify_api_key
from AINDY.platform_layer.rate_limiter import limiter


router = APIRouter(prefix="/db", tags=["Database Verification"], dependencies=[Depends(verify_api_key)])


def _execute_db_verify(request: Request, route_name: str, handler):
    return execute_with_pipeline_sync(request=request, route_name=route_name, handler=handler)

@router.get("/verify")
@limiter.limit("60/minute")
def verify_database_schema(request: Request):
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

    def handler(_ctx):
        return {"database_schema": result}
    return _execute_db_verify(request, "db.verify", handler)
