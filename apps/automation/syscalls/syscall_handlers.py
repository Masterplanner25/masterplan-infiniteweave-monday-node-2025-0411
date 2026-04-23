"""
Syscall Handlers — Domain-specific handler implementations.

This module registers all A.I.N.D.Y. business-domain syscall handlers.
Import it during application startup (main.py lifespan) to populate
SYSCALL_REGISTRY with all domain handlers.

Domains covered
---------------
  task        sys.v1.task.*
  leadgen     sys.v1.leadgen.*
  arm         sys.v1.arm.*
  genesis     sys.v1.genesis.*
  score       sys.v1.score.*
  watcher     sys.v1.watcher.*
  goal        sys.v1.goal.*
  research    sys.v1.research.*
  agent       sys.v1.agent.*

Handler contract (same as syscall_registry.py)
-----------------------------------------------
  fn(payload: dict, context: SyscallContext) -> dict
  - May raise ValueError for bad payload
  - Opens its own SessionLocal(); never receives a DB session
  - Returns plain dict (becomes the "data" field in the response envelope)
"""
from __future__ import annotations

import logging
from typing import Any

from AINDY.kernel.syscall_registry import SyscallContext, register_syscall

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# TASK DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_task_create(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.task.create — create a task via task_services.create_task().

    Payload keys:
        task_name / name  (str) — required
        category          (str) — default "general"
        priority          (str) — default "medium"
        due_date          (str | None)
        masterplan_id     (str | None)
        parent_task_id    (str | None)
        dependency_type   (str | None)
        dependencies      (list | None)
        automation_type   (str | None)
        automation_config (dict | None)
        scheduled_time    (str | None)
        reminder_time     (str | None)
        recurrence        (str | None)
    """
    from AINDY.db.database import SessionLocal
    from apps.tasks.services.task_service import create_task

    name = payload.get("task_name") or payload.get("name")
    if not name:
        raise ValueError("sys.v1.task.create requires 'task_name' or 'name'")

    db = SessionLocal()
    try:
        task = create_task(
            db=db,
            name=name,
            category=payload.get("category"),
            priority=payload.get("priority"),
            due_date=payload.get("due_date"),
            masterplan_id=payload.get("masterplan_id"),
            parent_task_id=payload.get("parent_task_id"),
            dependency_type=payload.get("dependency_type"),
            dependencies=payload.get("dependencies"),
            automation_type=payload.get("automation_type"),
            automation_config=payload.get("automation_config"),
            scheduled_time=payload.get("scheduled_time"),
            reminder_time=payload.get("reminder_time"),
            recurrence=payload.get("recurrence"),
            user_id=context.user_id,
        )
        return {
            "task_id": str(task.id) if task.id else None,
            "task_name": task.name,
            "category": task.category,
            "priority": task.priority,
            "status": getattr(task, "status", "unknown"),
            "time_spent": getattr(task, "time_spent", 0),
            "masterplan_id": getattr(task, "masterplan_id", None),
            "parent_task_id": getattr(task, "parent_task_id", None),
            "depends_on": getattr(task, "depends_on", []) or [],
            "dependency_type": getattr(task, "dependency_type", "hard"),
            "automation_type": getattr(task, "automation_type", None),
            "automation_config": getattr(task, "automation_config", None),
        }
    finally:
        db.close()


def _handle_task_complete(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.task.complete — mark task complete via complete_task() (used by flow nodes).

    Payload keys:
        task_name / name  (str) — required
    """
    from AINDY.db.database import SessionLocal
    from apps.tasks.services.task_service import complete_task

    name = payload.get("task_name") or payload.get("name")
    if not name:
        raise ValueError("sys.v1.task.complete requires 'task_name' or 'name'")

    db = SessionLocal()
    try:
        result = complete_task(db=db, name=name, user_id=context.user_id)
        return {"task_result": result}
    finally:
        db.close()


def _handle_task_complete_full(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.task.complete_full — full task completion with orchestration (used by agent tools).

    Payload keys:
        task_name / name  (str) — required
    """
    from AINDY.db.database import SessionLocal
    from apps.tasks.services.task_service import execute_task_completion

    name = payload.get("task_name") or payload.get("name")
    if not name:
        raise ValueError("sys.v1.task.complete_full requires 'task_name' or 'name'")

    db = SessionLocal()
    try:
        result = execute_task_completion(db=db, name=name, user_id=context.user_id)
        return result if isinstance(result, dict) else {"result": result}
    finally:
        db.close()


def _handle_task_start(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.task.start — start a task via task_services.start_task().

    Payload keys:
        task_name / name  (str) — required
    """
    from AINDY.db.database import SessionLocal
    from apps.tasks.services.task_service import start_task

    name = payload.get("task_name") or payload.get("name")
    if not name:
        raise ValueError("sys.v1.task.start requires 'task_name' or 'name'")

    db = SessionLocal()
    try:
        message = start_task(db, name, user_id=context.user_id)
        return {"task_start_result": {"message": message}}
    finally:
        db.close()


def _handle_task_pause(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.task.pause — pause a task via task_services.pause_task().

    Payload keys:
        task_name / name  (str) — required
    """
    from AINDY.db.database import SessionLocal
    from apps.tasks.services.task_service import pause_task

    name = payload.get("task_name") or payload.get("name")
    if not name:
        raise ValueError("sys.v1.task.pause requires 'task_name' or 'name'")

    db = SessionLocal()
    try:
        message = pause_task(db, name, user_id=context.user_id)
        return {"task_pause_result": {"message": message}}
    finally:
        db.close()


def _handle_task_orchestrate(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.task.orchestrate — post-completion orchestration via orchestrate_task_completion().

    Payload keys:
        task_name / name  (str) — required
    """
    from AINDY.db.database import SessionLocal
    from apps.tasks.services.task_service import orchestrate_task_completion

    name = payload.get("task_name") or payload.get("name")
    if not name:
        raise ValueError("sys.v1.task.orchestrate requires 'task_name' or 'name'")

    db = SessionLocal()
    try:
        orchestration = orchestrate_task_completion(db=db, name=name, user_id=context.user_id)
        return {"task_orchestration": orchestration}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# LEADGEN DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_leadgen_search(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.leadgen.search — run B2B lead search via create_lead_results().

    Payload keys:
        query  (str) — required
    """
    from AINDY.db.database import SessionLocal
    from apps.search.services.leadgen_service import create_lead_results

    query = payload.get("query", "")
    if not query:
        raise ValueError("sys.v1.leadgen.search requires 'query'")

    db = SessionLocal()
    try:
        raw = create_lead_results(db, query, user_id=context.user_id)
        serialized = [
            {
                "company": r.company,
                "url": r.url,
                "fit_score": r.fit_score,
                "intent_score": r.intent_score,
                "data_quality_score": r.data_quality_score,
                "overall_score": r.overall_score,
                "reasoning": r.reasoning,
                "search_score": search_score,
                "created_at": (
                    r.created_at.isoformat()
                    if hasattr(r.created_at, "isoformat")
                    else str(r.created_at or "")
                ),
            }
            for r, search_score in raw
        ]
        return {"search_results": serialized, "count": len(serialized)}
    finally:
        db.close()


def _handle_leadgen_search_ai(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.leadgen.search_ai — run AI-powered lead search via run_ai_search().

    Payload keys:
        query  (str) — required
    """
    from AINDY.db.database import SessionLocal
    from apps.search.services.leadgen_service import run_ai_search

    query = payload.get("query", "")
    if not query:
        raise ValueError("sys.v1.leadgen.search_ai requires 'query'")

    db = SessionLocal()
    try:
        leads = run_ai_search(query=query, user_id=context.user_id, db=db)
        return {"leads": leads, "count": len(leads)}
    finally:
        db.close()


def _handle_leadgen_store(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.leadgen.store — persist leadgen results to memory bridge and search cache.

    Payload keys:
        query    (str)        — required
        results  (list[dict]) — required; serialized lead result dicts
    """
    from AINDY.core.execution_signal_helper import queue_memory_capture
    from AINDY.db.database import SessionLocal

    query: str = payload.get("query", "")
    results: list = payload.get("results") or []

    db = SessionLocal()
    try:
        if context.user_id and results:
            queue_memory_capture(
                db=db,
                user_id=context.user_id,
                agent_namespace="leadgen",
                event_type="leadgen_search",
                content=f"LeadGen '{query[:80]}': {len(results)} results",
                source="flow_engine:leadgen",
                tags=["leadgen", "search", "outcome"],
            )

        if context.user_id and query and results:
            try:
                from apps.search.services.search_service import persist_search_result
                persist_search_result(
                    db=db,
                    user_id=context.user_id,
                    query=query,
                    result={"query": query, "count": len(results), "results": results},
                    search_type="leadgen",
                )
            except Exception as cache_exc:
                logger.warning("[sys.v1.leadgen.store] cache persist failed (non-fatal): %s", cache_exc)

        return {"stored": True, "count": len(results)}
    except Exception:
        raise
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# ARM DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_arm_analyze(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.arm.analyze — run ARM code analysis via DeepSeekCodeAnalyzer.

    Payload keys:
        file_path           (str) — required
        additional_context  (str) — optional
    """
    from AINDY.db.database import SessionLocal
    from apps.arm.services.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer

    file_path = payload.get("file_path")
    if not file_path:
        raise ValueError("sys.v1.arm.analyze requires 'file_path'")

    db = SessionLocal()
    try:
        analyzer = DeepSeekCodeAnalyzer()
        result = analyzer.run_analysis(
            file_path=file_path,
            user_id=context.user_id,
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
        db.close()


def _handle_arm_generate(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.arm.generate — run ARM code generation via DeepSeekCodeAnalyzer.

    Payload keys:
        prompt          (str) — required
        language        (str) — default "python"
        original_code   (str) — optional
        generation_type (str) — optional
        analysis_id     (str) — optional
        complexity      (str) — optional
        urgency         (str) — optional
    """
    from AINDY.db.database import SessionLocal
    from apps.arm.services.deepseek.deepseek_code_analyzer import DeepSeekCodeAnalyzer

    prompt = payload.get("prompt")
    if not prompt:
        raise ValueError("sys.v1.arm.generate requires 'prompt'")

    db = SessionLocal()
    try:
        analyzer = DeepSeekCodeAnalyzer()
        result = analyzer.generate_code(
            prompt=prompt,
            user_id=context.user_id,
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
        db.close()


def _handle_arm_store(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.arm.store — persist ARM result to Memory Bridge.

    Payload keys:
        result       (dict | str) — required; analysis or generation result
        event_type   (str)        — default "arm_analysis_complete"
        score        (int | float) — optional; for context metadata
    """
    from AINDY.core.execution_signal_helper import queue_memory_capture
    from AINDY.db.database import SessionLocal

    result = payload.get("result", {})
    event_type = payload.get("event_type", "arm_analysis_complete")
    score = payload.get("score", 5)

    db = SessionLocal()
    try:
        if context.user_id:
            queue_memory_capture(
                db=db,
                user_id=context.user_id,
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
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# GENESIS DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_genesis_execute_llm(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.genesis.execute_llm — call Genesis LLM + update session state (used by flow nodes).

    Payload keys:
        session_id  (str) — required
        message     (str) — required
    """
    import uuid

    from AINDY.db.database import SessionLocal
    from apps.masterplan.models import GenesisSessionDB
    from apps.masterplan.services.genesis_ai import call_genesis_llm

    session_id = payload.get("session_id")
    message = payload.get("message")
    if not session_id:
        raise ValueError("sys.v1.genesis.execute_llm requires 'session_id'")
    if not message:
        raise ValueError("sys.v1.genesis.execute_llm requires 'message'")

    db = SessionLocal()
    try:
        user_id = uuid.UUID(str(context.user_id))
        session = (
            db.query(GenesisSessionDB)
            .filter(
                GenesisSessionDB.id == session_id,
                GenesisSessionDB.user_id == user_id,
            )
            .first()
        )
        if not session:
            raise ValueError("GenesisSession not found")

        current_state = session.summarized_state or {}
        llm_output = call_genesis_llm(
            message=message,
            current_state=current_state,
            user_id=str(user_id),
            db=db,
        )

        state_update = llm_output.get("state_update", {})
        for key, value in state_update.items():
            if key in current_state and value is not None:
                current_state[key] = value

        if "confidence" in current_state:
            current_state["confidence"] = max(0.0, min(current_state["confidence"], 1.0))

        session.summarized_state = current_state
        if llm_output.get("synthesis_ready", False) and not session.synthesis_ready:
            session.synthesis_ready = True
        db.commit()

        return {
            "genesis_response": {
                "reply": llm_output.get("reply", ""),
                "synthesis_ready": session.synthesis_ready,
            }
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _handle_genesis_message(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.genesis.message — run full genesis_message flow via execute_intent (used by agent tools).

    Payload keys:
        session_id  (str) — required
        message     (str) — required
    """
    from AINDY.db.database import SessionLocal
    from AINDY.runtime.flow_engine import execute_intent

    session_id = payload.get("session_id")
    message = payload.get("message")
    if not message:
        raise ValueError("sys.v1.genesis.message requires 'message'")
    if not session_id:
        raise ValueError("sys.v1.genesis.message requires 'session_id'")

    db = SessionLocal()
    try:
        result = execute_intent(
            intent_data={
                "workflow_type": "genesis_message",
                "session_id": session_id,
                "message": message,
            },
            db=db,
            user_id=context.user_id,
        )
        return result if isinstance(result, dict) else {"result": result}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# SCORE DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_score_recalculate(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.score.recalculate — recalculate Infinity Score via orchestrator.

    Payload keys:
        trigger_event  (str) — default "manual"
    """
    from AINDY.db.database import SessionLocal
    from apps.analytics.services.infinity_orchestrator import execute as execute_infinity_orchestrator

    trigger = payload.get("trigger_event", "manual")

    db = SessionLocal()
    try:
        result = execute_infinity_orchestrator(
            user_id=context.user_id,
            db=db,
            trigger_event=trigger,
        )
        if not result:
            raise ValueError("score calculation returned empty result")
        score_data = result.get("score") or result
        return {"score_recalculate_result": score_data}
    finally:
        db.close()


def _handle_score_feedback(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.score.feedback — persist a UserFeedback record.

    Payload keys:
        source_type        (str)   — required
        source_id          (str)   — optional
        feedback_value     (float) — optional
        feedback_text      (str)   — optional
        loop_adjustment_id (str)   — optional
    """
    from datetime import datetime, timezone
    from uuid import UUID

    from AINDY.db.database import SessionLocal
    from AINDY.platform_layer.user_ids import require_user_id
    from apps.automation.models import LoopAdjustment, UserFeedback

    db = SessionLocal()
    try:
        user_id = require_user_id(context.user_id)
        feedback = UserFeedback(
            user_id=user_id,
            source_type=payload.get("source_type"),
            source_id=payload.get("source_id"),
            feedback_value=payload.get("feedback_value"),
            feedback_text=payload.get("feedback_text"),
            loop_adjustment_id=payload.get("loop_adjustment_id"),
        )
        db.add(feedback)
        loop_adjustment_id = payload.get("loop_adjustment_id")
        if loop_adjustment_id:
            adjustment = (
                db.query(LoopAdjustment)
                .filter(
                    LoopAdjustment.id == UUID(str(loop_adjustment_id)),
                    LoopAdjustment.user_id == user_id,
                )
                .first()
            )
            if adjustment is not None and adjustment.evaluated_at is None:
                adjustment.evaluated_at = datetime.now(timezone.utc)
                db.add(adjustment)
        db.commit()
        db.refresh(feedback)
        return {"score_feedback_result": {"id": str(feedback.id)}}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# WATCHER DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_watcher_ingest(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.watcher.ingest — persist a batch of WatcherSignals.

    Payload keys:
        signals  (list[dict]) — required; each dict is one signal record
    """
    from datetime import datetime, timezone
    from uuid import UUID

    from AINDY.db.database import SessionLocal
    from AINDY.db.models.watcher_signal import WatcherSignal
    from AINDY.platform_layer.watcher_contract import (
        get_valid_activity_types,
        get_valid_signal_types,
        parse_signal_timestamp,
    )

    signals: list = payload.get("signals") or []
    if not isinstance(signals, list) or not signals:
        raise ValueError("sys.v1.watcher.ingest requires non-empty 'signals' list")

    db = SessionLocal()
    try:
        persisted = 0
        session_ended_count = 0
        batch_user_id = None

        for idx, sig in enumerate(signals):
            signal_type = sig.get("signal_type")
            activity_type = sig.get("activity_type")
            if signal_type not in get_valid_signal_types():
                raise ValueError(f"Signal [{idx}]: unknown signal_type {signal_type!r}")
            if activity_type not in get_valid_activity_types():
                raise ValueError(f"Signal [{idx}]: unknown activity_type {activity_type!r}")

            ts = parse_signal_timestamp(sig.get("timestamp"))
            meta = sig.get("metadata") or {}
            signal_user_id = sig.get("user_id")
            if signal_user_id and not batch_user_id:
                batch_user_id = signal_user_id

            row = WatcherSignal(
                signal_type=signal_type,
                session_id=sig.get("session_id"),
                user_id=UUID(str(signal_user_id)) if signal_user_id else None,
                app_name=sig.get("app_name"),
                window_title=sig.get("window_title") or None,
                activity_type=activity_type,
                signal_timestamp=ts,
                received_at=datetime.now(timezone.utc),
                duration_seconds=meta.get("duration_seconds"),
                focus_score=meta.get("focus_score"),
                signal_metadata=meta if meta else None,
            )
            db.add(row)
            if signal_type == "session_ended":
                session_ended_count += 1
            persisted += 1

        db.commit()
        return {
            "watcher_ingest_result": {
                "accepted": persisted,
                "session_ended_count": session_ended_count,
            },
            "watcher_batch_user_id": batch_user_id,
            "watcher_session_ended_count": session_ended_count,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_goal_create(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.goal.create — create a goal via goal_service.create_goal().

    Payload keys:
        name            (str)   — required
        description     (str)   — optional
        goal_type       (str)   — default "strategic"
        priority        (float) — default 0.5
        status          (str)   — default "active"
        success_metric  (dict)  — optional
    """
    from AINDY.db.database import SessionLocal
    from apps.masterplan.services.goal_service import create_goal

    name = payload.get("name")
    if not name:
        raise ValueError("sys.v1.goal.create requires 'name'")

    db = SessionLocal()
    try:
        goal = create_goal(
            db,
            user_id=context.user_id,
            name=name,
            description=payload.get("description"),
            goal_type=payload.get("goal_type", "strategic"),
            priority=payload.get("priority", 0.5),
            status=payload.get("status", "active"),
            success_metric=payload.get("success_metric", {}),
        )
        return {"goal_create_result": goal}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# RESEARCH DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_research_query(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.research.query — web research via apps.search.services.research_engine.web_search().

    Payload keys:
        query  (str) — required
    """
    from apps.search.services.research_engine import web_search

    query = payload.get("query", "")
    if not query:
        raise ValueError("sys.v1.research.query requires 'query'")

    raw = web_search(query)
    return {"raw_result": raw[:2000] if raw else ""}


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_agent_suggest_tools(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.agent.suggest_tools — return KPI-driven tool suggestions.

    Payload keys:
        kpi_snapshot  (dict) — required; keys: focus_quality, execution_speed,
                               ai_productivity_boost, master_score
    """
    from AINDY.db.database import SessionLocal

    kpi_snapshot: dict = payload.get("kpi_snapshot") or {}

    # Try persisted suggestions first
    db = SessionLocal()
    try:
        if context.user_id:
            try:
                from apps.analytics.services.infinity_loop import get_latest_adjustment
                latest = get_latest_adjustment(user_id=context.user_id, db=db)
                if latest and latest.adjustment_payload:
                    persisted = latest.adjustment_payload.get("suggestions")
                    if isinstance(persisted, list):
                        return {"suggestions": persisted[:3]}
            except Exception as exc:
                logger.warning("[sys.v1.agent.suggest_tools] persisted lookup failed: %s", exc)
    finally:
        db.close()

    if not kpi_snapshot:
        return {"suggestions": []}

    try:
        suggestions: list[dict[str, Any]] = []
        focus = kpi_snapshot.get("focus_quality", 50.0)
        speed = kpi_snapshot.get("execution_speed", 50.0)
        ai_boost = kpi_snapshot.get("ai_productivity_boost", 50.0)
        master = kpi_snapshot.get("master_score", 50.0)

        if focus < 40:
            suggestions.append({
                "tool": "memory.recall",
                "reason": f"Focus quality is low ({focus:.0f}/100) — recall past context before starting new work",
                "suggested_goal": "Recall recent memories and notes to regain context on current priorities",
            })

        if speed < 40:
            suggestions.append({
                "tool": "task.create",
                "reason": f"Execution speed is low ({speed:.0f}/100) — create a concrete next action to rebuild momentum",
                "suggested_goal": "Create a focused task for the most important thing I need to do today",
            })
        elif speed < 55:
            suggestions.append({
                "tool": "task.create",
                "reason": f"Execution pace is below average ({speed:.0f}/100) — a new task could help",
                "suggested_goal": "Create a small, completable task to get back on track",
            })

        if ai_boost < 40 and len(suggestions) < 3:
            suggestions.append({
                "tool": "arm.analyze",
                "reason": f"ARM usage is low ({ai_boost:.0f}/100) — analyzing code could boost quality scores",
                "suggested_goal": "Analyze the current codebase for architecture and integrity improvements",
            })

        if master >= 70 and len(suggestions) < 3:
            suggestions.append({
                "tool": "genesis.message",
                "reason": f"Strong overall performance ({master:.0f}/100) — review strategic direction with Genesis",
                "suggested_goal": "Review my current MasterPlan progress and refine next priorities with Genesis",
            })

        return {"suggestions": suggestions[:3]}
    except Exception as exc:
        logger.warning("[sys.v1.agent.suggest_tools] failed: %s", exc)
        return {"suggestions": []}


# ── MAS Memory Handlers ───────────────────────────────────────────────────────
# Thin wrappers that delegate to syscall_registry handlers.
# Registered via register_all_domain_handlers() so they override the base
# registry entries with domain-handler versions (idempotent).

def _mas_memory_list(payload: dict, context) -> dict:
    """sys.v1.memory.list — list MAS nodes at a path prefix."""
    from AINDY.platform_layer.memory_runtime import list_memory_nodes

    return list_memory_nodes(payload, context)


def _mas_memory_tree(payload: dict, context) -> dict:
    """sys.v1.memory.tree — hierarchical tree of nodes under a path."""
    from AINDY.platform_layer.memory_runtime import get_memory_tree

    return get_memory_tree(payload, context)


def _mas_memory_trace(payload: dict, context) -> dict:
    """sys.v1.memory.trace — causal trace from node at path."""
    from AINDY.platform_layer.memory_runtime import trace_memory_chain

    return trace_memory_chain(payload, context)


def _handle_authorship_list(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.authorship.list_authors — list recent authors for a user.

    Payload keys:
        user_id  (str) — required
        limit    (int) — default 10
    """
    import uuid

    from AINDY.db.database import SessionLocal
    from apps.authorship.models import AuthorDB

    user_id = payload.get("user_id") or context.user_id
    limit = int(payload.get("limit") or 10)

    external_db = context.metadata.get("_db") or context.metadata.get("db")
    owns_session = external_db is None
    db = external_db if external_db is not None else SessionLocal()
    try:
        authors = (
            db.query(AuthorDB)
            .filter(AuthorDB.user_id == uuid.UUID(str(user_id)))
            .order_by(AuthorDB.joined_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "authors": [
                {
                    "id": a.id,
                    "name": a.name,
                    "platform": a.platform,
                    "last_seen": a.last_seen.isoformat() if a.last_seen else None,
                    "notes": a.notes,
                }
                for a in authors
            ]
        }
    finally:
        if owns_session:
            db.close()


def _handle_rippletrace_list_pings(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.rippletrace.list_recent_pings — list recent pings for a user.

    Payload keys:
        user_id  (str) — required
        limit    (int) — default 10
    """
    import uuid

    from AINDY.db.database import SessionLocal
    from apps.rippletrace.models import PingDB

    user_id = payload.get("user_id") or context.user_id
    limit = int(payload.get("limit") or 10)

    external_db = context.metadata.get("_db") or context.metadata.get("db")
    owns_session = external_db is None
    db = external_db if external_db is not None else SessionLocal()
    try:
        ripples = (
            db.query(PingDB)
            .filter(PingDB.user_id == uuid.UUID(str(user_id)))
            .order_by(PingDB.date_detected.desc())
            .limit(limit)
            .all()
        )
        return {
            "pings": [
                {
                    "ping_type": r.ping_type,
                    "source_platform": r.source_platform,
                    "summary": r.connection_summary,
                    "date_detected": r.date_detected.isoformat() if r.date_detected else None,
                }
                for r in ripples
            ]
        }
    finally:
        if owns_session:
            db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

def register_all_domain_handlers() -> None:
    """Register all domain syscall handlers.

    Called once at application startup. Safe to call multiple times
    (subsequent calls overwrite with the same values — idempotent).
    """
    from apps.tasks.syscalls.syscall_handlers import register_task_syscall_handlers

    register_task_syscall_handlers()

    # Tuples: (name, handler, capability, description, stable)
    # Domain-specific handlers are stable=False — they wrap application logic
    # that may change between minor releases. Only core I/O syscalls are stable.
    _registrations = [
        # LeadGen
        ("sys.v1.leadgen.search",          _handle_leadgen_search,        "leadgen.search",        "B2B lead search via create_lead_results",                False),
        ("sys.v1.leadgen.search_ai",       _handle_leadgen_search_ai,     "leadgen.search_ai",     "AI-powered B2B lead search",                            False),
        ("sys.v1.leadgen.store",           _handle_leadgen_store,         "leadgen.store",         "Persist leadgen results to memory bridge",               False),
        # ARM
        ("sys.v1.arm.analyze",             _handle_arm_analyze,           "arm.analyze",           "ARM code analysis",                                      False),
        ("sys.v1.arm.generate",            _handle_arm_generate,          "arm.generate",          "ARM code generation",                                    False),
        ("sys.v1.arm.store",               _handle_arm_store,             "arm.store",             "Persist ARM result to memory bridge",                    False),
        # Genesis
        ("sys.v1.genesis.execute_llm",     _handle_genesis_execute_llm,   "genesis.execute_llm",   "Call Genesis LLM and update session (flow nodes)",      False),
        ("sys.v1.genesis.message",         _handle_genesis_message,       "genesis.message",       "Full genesis message flow (agent tools)",                False),
        # Score
        ("sys.v1.score.recalculate",       _handle_score_recalculate,     "score.recalculate",     "Recalculate Infinity Score",                             False),
        ("sys.v1.score.feedback",          _handle_score_feedback,        "score.feedback",        "Persist score feedback record",                          False),
        # Goal
        ("sys.v1.goal.create",             _handle_goal_create,           "goal.create",           "Create a goal",                                          False),
        # Research
        ("sys.v1.research.query",          _handle_research_query,        "research.query",        "Web research query",                                     False),
        # Agent
        ("sys.v1.agent.suggest_tools",     _handle_agent_suggest_tools,   "agent.suggest_tools",   "KPI-driven tool suggestions",                            False),
        # Authorship / RippleTrace reads
        ("sys.v1.authorship.list_authors", _handle_authorship_list,       "authorship.read",       "List recent authors for a user",                        False),
        ("sys.v1.rippletrace.list_recent_pings", _handle_rippletrace_list_pings, "rippletrace.read", "List recent pings for a user",                        False),
        # Memory Address Space (path-based — experimental extensions)
        ("sys.v1.memory.list",             _mas_memory_list,              "memory.list",           "List MAS nodes at path prefix",                          False),
        ("sys.v1.memory.tree",             _mas_memory_tree,              "memory.tree",           "Hierarchical tree of nodes under path",                  False),
        ("sys.v1.memory.trace",            _mas_memory_trace,             "memory.trace",          "Causal trace from node at path",                         False),
    ]

    for name, handler, capability, description, stable in _registrations:
        register_syscall(name, handler, capability, description, stable=stable)

    logger.info(
        "[syscall_handlers] registered %d domain handlers", len(_registrations)
    )


