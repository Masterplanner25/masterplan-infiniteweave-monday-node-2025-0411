# routes/arm_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from services.deepseek_arm_service import (
    run_analysis,
    generate_code,
    get_reasoning_logs,
    get_config,
    update_config,
)
from pydantic import BaseModel


router = APIRouter(prefix="/arm", tags=["Autonomous Reasoning Module"])


# -----------------------------
# Pydantic Inputs
# -----------------------------
class AnalyzeInput(BaseModel):
    file_path: str
    analysis_type: str | None = "full"


class GenerateInput(BaseModel):
    file_path: str
    instructions: str | None = None


class ConfigUpdate(BaseModel):
    parameter: str
    value: str | int | float | bool


# -----------------------------
# Endpoints
# -----------------------------

@router.post("/analyze")
async def analyze_file(data: AnalyzeInput, db: Session = Depends(get_db)):
    """
    Run DeepSeek reasoning analysis on a codebase or logic file.
    """
    try:
        result = run_analysis(db, data.file_path, data.analysis_type)
        return {"status": "success", "analysis": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ARM analysis error: {e}")


@router.post("/generate")
async def generate_logic(data: GenerateInput, db: Session = Depends(get_db)):
    """
    Generate or refactor code using DeepSeek logic synthesis.
    """
    try:
        output = generate_code(db, data.file_path, data.instructions)
        return {"status": "success", "generated_code": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ARM generation error: {e}")


@router.get("/logs")
async def fetch_logs(db: Session = Depends(get_db)):
    """
    Retrieve reasoning logs from ARM sessions.
    """
    return get_reasoning_logs(db)


@router.get("/config")
async def read_config(db: Session = Depends(get_db)):
    """
    View current DeepSeek ARM configuration parameters.
    """
    return get_config(db)


@router.put("/config")
async def modify_config(update: ConfigUpdate, db: Session = Depends(get_db)):
    """
    Dynamically update DeepSeek ARM configuration parameters.
    """
    return update_config(db, update.parameter, update.value)
