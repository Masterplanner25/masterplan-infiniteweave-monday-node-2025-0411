"""ARM domain syscall handlers."""
from __future__ import annotations

import logging

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall

logger = logging.getLogger(__name__)


def _session_from_context(ctx: SyscallContext):
    from AINDY.db.database import SessionLocal

    external_db = ctx.metadata.get("_db")
    if external_db is not None:
        return external_db, False
    return SessionLocal(), True


def _handle_arm_analyze(payload: dict, ctx: SyscallContext) -> dict:
    from apps.arm.services.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer

    file_path = payload.get("file_path")
    if not file_path:
        raise ValueError("sys.v1.arm.analyze requires 'file_path'")

    db, owns_session = _session_from_context(ctx)
    try:
        analyzer = DeepSeekCodeAnalyzer()
        result = analyzer.run_analysis(
            file_path=file_path,
            user_id=ctx.user_id,
            db=db,
            additional_context=payload.get("additional_context", ""),
        )
        return {
            "analysis_result": result,
            "summary": result.get("summary", ""),
            "architecture_score": result.get("architecture_score"),
            "integrity_score": result.get("integrity_score"),
            "analysis_score": result.get("architecture_score", 5),
            "analysis_id": result.get("analysis_id"),
        }
    finally:
        if owns_session:
            db.close()


def _handle_arm_generate(payload: dict, ctx: SyscallContext) -> dict:
    from apps.arm.services.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer

    prompt = payload.get("prompt")
    if not prompt:
        raise ValueError("sys.v1.arm.generate requires 'prompt'")

    db, owns_session = _session_from_context(ctx)
    try:
        analyzer = DeepSeekCodeAnalyzer()
        result = analyzer.generate_code(
            prompt=prompt,
            user_id=ctx.user_id,
            db=db,
            language=payload.get("language", "python"),
            original_code=payload.get("original_code", ""),
            generation_type=payload.get("generation_type", "generate"),
            analysis_id=payload.get("analysis_id"),
            complexity=payload.get("complexity"),
            urgency=payload.get("urgency"),
        )
        return {
            "generation_result": result,
            "generated_code": result.get("generated_code", ""),
            "explanation": result.get("explanation", ""),
            "generation_id": result.get("generation_id"),
        }
    finally:
        if owns_session:
            db.close()


def _handle_arm_store(payload: dict, ctx: SyscallContext) -> dict:
    from AINDY.core.execution_signal_helper import queue_memory_capture

    result = payload.get("result", {})
    event_type = payload.get("event_type", "arm_analysis_complete")
    score = payload.get("score", 5)

    db, owns_session = _session_from_context(ctx)
    try:
        if ctx.user_id:
            queue_memory_capture(
                db=db,
                user_id=ctx.user_id,
                agent_namespace="arm",
                event_type=event_type,
                content=str(result)[:500],
                source="syscall:arm_store",
                context={"score": score},
            )
        return {"stored": True}
    except Exception as exc:
        logger.warning("[sys.v1.arm.store] non-fatal: %s", exc)
        return {"stored": False}
    finally:
        if owns_session:
            db.close()


def register_arm_syscall_handlers() -> None:
    register_syscall(
        name="sys.v1.arm.analyze",
        handler=_handle_arm_analyze,
        capability="arm.analyze",
        description="ARM code analysis.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.arm.generate",
        handler=_handle_arm_generate,
        capability="arm.generate",
        description="ARM code generation.",
        stable=False,
    )
    register_syscall(
        name="sys.v1.arm.store",
        handler=_handle_arm_store,
        capability="arm.store",
        description="Persist ARM result to memory bridge.",
        stable=False,
    )
