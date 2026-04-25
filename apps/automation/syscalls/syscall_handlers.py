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

from AINDY.kernel.syscall_dispatcher import child_context, get_dispatcher
from AINDY.kernel.syscall_registry import SyscallContext, register_syscall

logger = logging.getLogger(__name__)


def _dispatch_owner_syscall(
    name: str,
    payload: dict[str, Any],
    context: SyscallContext,
    *,
    capability: str,
) -> dict[str, Any]:
    nested_context = child_context(
        context,
        capabilities=[capability],
        metadata={
            **(context.metadata or {}),
            "source": "automation",
        },
    )
    result = get_dispatcher().dispatch(name, payload, nested_context)
    if result.get("status") != "success":
        raise ValueError(result.get("error") or f"{name} failed")
    return result.get("data") or {}


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
    return _dispatch_owner_syscall(
        "sys.v1.task.create",
        payload,
        context,
        capability="task.create",
    )


def _handle_task_complete(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.task.complete — mark task complete via complete_task() (used by flow nodes).

    Payload keys:
        task_name / name  (str) — required
    """
    return _dispatch_owner_syscall(
        "sys.v1.task.complete",
        payload,
        context,
        capability="task.complete",
    )


def _handle_task_complete_full(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.task.complete_full — full task completion with orchestration (used by agent tools).

    Payload keys:
        task_name / name  (str) — required
    """
    return _dispatch_owner_syscall(
        "sys.v1.task.complete_full",
        payload,
        context,
        capability="task.complete_full",
    )


def _handle_task_start(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.task.start — start a task via task_services.start_task().

    Payload keys:
        task_name / name  (str) — required
    """
    return _dispatch_owner_syscall(
        "sys.v1.task.start",
        payload,
        context,
        capability="task.start",
    )


def _handle_task_pause(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.task.pause — pause a task via task_services.pause_task().

    Payload keys:
        task_name / name  (str) — required
    """
    return _dispatch_owner_syscall(
        "sys.v1.task.pause",
        payload,
        context,
        capability="task.pause",
    )


def _handle_task_orchestrate(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.task.orchestrate — post-completion orchestration via orchestrate_task_completion().

    Payload keys:
        task_name / name  (str) — required
    """
    return _dispatch_owner_syscall(
        "sys.v1.task.orchestrate",
        payload,
        context,
        capability="task.orchestrate",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LEADGEN DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_leadgen_search(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.leadgen.search — run B2B lead search via create_lead_results().

    Payload keys:
        query  (str) — required
    """
    if not payload.get("query"):
        raise ValueError("sys.v1.leadgen.search requires 'query'")
    return _dispatch_owner_syscall(
        "sys.v1.leadgen.search",
        payload,
        context,
        capability="leadgen.search",
    )


def _handle_leadgen_search_ai(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.leadgen.search_ai — run AI-powered lead search via run_ai_search().

    Payload keys:
        query  (str) — required
    """
    if not payload.get("query"):
        raise ValueError("sys.v1.leadgen.search_ai requires 'query'")
    return _dispatch_owner_syscall(
        "sys.v1.leadgen.search_ai",
        payload,
        context,
        capability="leadgen.search_ai",
    )


def _handle_leadgen_store(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.leadgen.store — persist leadgen results to memory bridge and search cache.

    Payload keys:
        query    (str)        — required
        results  (list[dict]) — required; serialized lead result dicts
    """
    if not context.user_id:
        return {"stored": True, "count": len(payload.get("results") or [])}
    return _dispatch_owner_syscall(
        "sys.v1.leadgen.store",
        payload,
        context,
        capability="leadgen.store",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ARM DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_arm_analyze(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.arm.analyze — run ARM code analysis via DeepSeekCodeAnalyzer.

    Payload keys:
        file_path           (str) — required
        additional_context  (str) — optional
    """
    if not payload.get("file_path"):
        raise ValueError("sys.v1.arm.analyze requires 'file_path'")
    return _dispatch_owner_syscall(
        "sys.v1.arm.analyze",
        payload,
        context,
        capability="arm.analyze",
    )


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
    if not payload.get("prompt"):
        raise ValueError("sys.v1.arm.generate requires 'prompt'")
    return _dispatch_owner_syscall(
        "sys.v1.arm.generate",
        payload,
        context,
        capability="arm.generate",
    )


def _handle_arm_store(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.arm.store — persist ARM result to Memory Bridge.

    Payload keys:
        result       (dict | str) — required; analysis or generation result
        event_type   (str)        — default "arm_analysis_complete"
        score        (int | float) — optional; for context metadata
    """
    return _dispatch_owner_syscall(
        "sys.v1.arm.store",
        payload,
        context,
        capability="arm.store",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# GENESIS DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_genesis_execute_llm(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.genesis.execute_llm — call Genesis LLM + update session state (used by flow nodes).

    Payload keys:
        session_id  (str) — required
        message     (str) — required
    """
    if not payload.get("session_id"):
        raise ValueError("sys.v1.genesis.execute_llm requires 'session_id'")
    if not payload.get("message"):
        raise ValueError("sys.v1.genesis.execute_llm requires 'message'")
    return _dispatch_owner_syscall(
        "sys.v1.genesis.execute_llm",
        payload,
        context,
        capability="genesis.execute_llm",
    )


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
    return _dispatch_owner_syscall(
        "sys.v1.score.recalculate",
        payload,
        context,
        capability="score.recalculate",
    )


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
    if not payload.get("name"):
        raise ValueError("sys.v1.goal.create requires 'name'")
    return _dispatch_owner_syscall(
        "sys.v1.goal.create",
        payload,
        context,
        capability="goal.create",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RESEARCH DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_research_query(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.research.query — web research via apps.search.services.research_engine.web_search().

    Payload keys:
        query  (str) — required
    """
    if not payload.get("query"):
        raise ValueError("sys.v1.research.query requires 'query'")
    return _dispatch_owner_syscall(
        "sys.v1.research.query",
        payload,
        context,
        capability="research.query",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT DOMAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_agent_suggest_tools(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.agent.suggest_tools — return KPI-driven tool suggestions.

    Payload keys:
        kpi_snapshot  (dict) — required; keys: focus_quality, execution_speed,
                               ai_productivity_boost, master_score
    """
    kpi_snapshot: dict = payload.get("kpi_snapshot") or {}

    if context.user_id:
        try:
            latest_result = _dispatch_owner_syscall(
                "sys.v1.analytics.get_latest_adjustment",
                {"user_id": context.user_id},
                context,
                capability="analytics.read",
            )
            latest = latest_result.get("adjustment") or {}
            persisted = (latest.get("adjustment_payload") or {}).get("suggestions")
            if isinstance(persisted, list):
                return {"suggestions": persisted[:3]}
        except Exception as exc:
            logger.warning("[sys.v1.agent.suggest_tools] persisted lookup failed: %s", exc)

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
    return _dispatch_owner_syscall(
        "sys.v1.authorship.list_authors",
        payload,
        context,
        capability="authorship.read",
    )


def _handle_rippletrace_list_pings(payload: dict, context: SyscallContext) -> dict:
    """sys.v1.rippletrace.list_recent_pings — list recent pings for a user.

    Payload keys:
        user_id  (str) — required
        limit    (int) — default 10
    """
    return _dispatch_owner_syscall(
        "sys.v1.rippletrace.list_recent_pings",
        payload,
        context,
        capability="rippletrace.read",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

def register_all_domain_handlers() -> None:
    """Register all domain syscall handlers.

    Called once at application startup. Safe to call multiple times
    (subsequent calls overwrite with the same values — idempotent).
    """
    # Tuples: (name, handler, capability, description, stable)
    # Domain-specific handlers are stable=False — they wrap application logic
    # that may change between minor releases. Only core I/O syscalls are stable.
    _registrations = [
        ("sys.v1.score.feedback",          _handle_score_feedback,        "score.feedback",        "Persist score feedback record",                          False),
        # Agent
        ("sys.v1.agent.suggest_tools",     _handle_agent_suggest_tools,   "agent.suggest_tools",   "KPI-driven tool suggestions",                            False),
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


