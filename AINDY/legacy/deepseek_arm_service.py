# services/deepseek_arm_service.py
import os
import time
from datetime import datetime
from sqlalchemy.orm import Session

from services.memory_persistence import MemoryNodeDAO
from db.models.arm_models import (
    ARMRun,
    ARMLog,
    ARMConfig,
)
from modules.deepseek.security_deepseek import SecurityValidator
from modules.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer
from modules.deepseek.file_processor_deepseek import FileProcessor
from modules.deepseek.config_manager_deepseek import ConfigManager


# -------------------------------------------------------------------
# Initialization
# -------------------------------------------------------------------

CONFIG_PATH = os.getenv("DEEPSEEK_CONFIG_PATH", "deepseek_config.json")

validator = SecurityValidator()
file_processor = FileProcessor()
config_manager = ConfigManager(CONFIG_PATH)


# -------------------------------------------------------------------
# CORE LOGIC FUNCTIONS
# -------------------------------------------------------------------

def run_analysis(db: Session, file_path: str, analysis_type: str = "full"):
    """
    Run DeepSeek reasoning analysis on a file.
    Validates input, executes reasoning, logs output to Memory Bridge and DB.
    """

    # Security check
    validator.validate_file(file_path)

    # Config parameters
    config = config_manager.load()

    # Start performance timer
    start_time = time.time()
    analyzer = DeepSeekCodeAnalyzer(config_path=CONFIG_PATH)

    # Run analysis
    analysis_summary = analyzer.run_analysis(file_path, analysis_type=analysis_type)
    duration = time.time() - start_time

    # Store in DB
    run = ARMRun(
        file_path=file_path,
        operation="analysis",
        result_summary=analysis_summary[:1000],
        runtime=duration,
        created_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Log to Memory Bridge
    try:
        dao = MemoryNodeDAO(db)
        dao.save_memory_node(
            type("MemoryNode", (), {
                "content": f"ARM Analysis: {file_path}",
                "tags": ["deepseek", "analysis"],
                "node_type": "arm_analysis",
                "extra": {"duration": duration, "summary": analysis_summary[:250]},
            })()
        )
    except Exception as bridge_err:
        print(f"[MemoryBridge] ARM log error: {bridge_err}")

    # Write to logs table
    db.add(ARMLog(run_id=run.id, message=f"Completed analysis on {file_path}", level="INFO"))
    db.commit()

    return analysis_summary


def generate_code(db: Session, file_path: str, instructions: str | None = None):
    """
    Generate or refactor code using DeepSeek synthesis engine.
    """
    validator.validate_file(file_path)
    config = config_manager.load()

    analyzer = DeepSeekCodeAnalyzer(config_path=CONFIG_PATH)

    start_time = time.time()
    output_code = analyzer.generate_code(file_path, instructions)
    duration = time.time() - start_time

    run = ARMRun(
        file_path=file_path,
        operation="generation",
        result_summary=output_code[:1000],
        runtime=duration,
        created_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Log to Memory Bridge
    try:
        dao = MemoryNodeDAO(db)
        dao.save_memory_node(
            type("MemoryNode", (), {
                "content": f"ARM Code Generation: {file_path}",
                "tags": ["deepseek", "generation"],
                "node_type": "arm_generation",
                "extra": {"instructions": instructions, "duration": duration},
            })()
        )
    except Exception as bridge_err:
        print(f"[MemoryBridge] Generation log error: {bridge_err}")

    db.add(ARMLog(run_id=run.id, message=f"Generated new logic for {file_path}", level="INFO"))
    db.commit()

    return output_code


def get_reasoning_logs(db: Session):
    """
    Retrieve recent ARM logs.
    """
    logs = db.query(ARMLog).order_by(ARMLog.timestamp.desc()).limit(50).all()
    return [
        {"timestamp": log.timestamp, "message": log.message, "level": log.level}
        for log in logs
    ]


def get_config(db: Session):
    """
    Retrieve DeepSeek ARM configuration.
    """
    config = config_manager.load()
    db_config = db.query(ARMConfig).order_by(ARMConfig.updated_at.desc()).first()
    return {"runtime_config": config, "last_saved": db_config.updated_at if db_config else None}


def update_config(db: Session, parameter: str, value):
    """
    Dynamically update DeepSeek ARM configuration parameter.
    """
    config = config_manager.update(parameter, value)
    record = ARMConfig(parameter=parameter, value=str(value), updated_at=datetime.utcnow())
    db.add(record)
    db.commit()

    return {"status": "updated", "parameter": parameter, "value": value}
