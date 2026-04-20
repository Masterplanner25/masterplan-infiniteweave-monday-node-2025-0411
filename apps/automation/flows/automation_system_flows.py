import logging

from AINDY.runtime.flow_engine import FLOW_REGISTRY, register_flow
from apps.automation.flows._flow_registration import (
    register_nodes,
    register_single_node_flows,
)

logger = logging.getLogger(__name__)


# -- Node functions -----------------------------------------------------------

def automation_logs_list_node(state, context):
    try:
        from uuid import UUID
        from apps.automation.models import AutomationLog

        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        status = state.get("status")
        source_filter = state.get("source_filter")
        limit = state.get("limit", 50)
        query = db.query(AutomationLog).filter(AutomationLog.user_id == user_id)
        if status:
            query = query.filter(AutomationLog.status == status)
        if source_filter:
            query = query.filter(AutomationLog.source == source_filter)
        logs = query.order_by(AutomationLog.created_at.desc()).limit(limit).all()

        def _s(log):
            return {
                "id": log.id, "source": log.source, "task_name": log.task_name,
                "payload": log.payload, "status": log.status,
                "attempt_count": log.attempt_count, "max_attempts": log.max_attempts,
                "error_message": log.error_message, "result": log.result,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "scheduled_for": log.scheduled_for.isoformat() if log.scheduled_for else None,
            }

        return {"status": "SUCCESS", "output_patch": {"automation_logs_list_result": {"logs": [_s(log) for log in logs], "count": len(logs), "filters": {"status": status, "source": source_filter}}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def automation_log_get_node(state, context):
    try:
        from uuid import UUID
        from apps.automation.models import AutomationLog

        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        log_id = state.get("log_id")
        log = db.query(AutomationLog).filter(AutomationLog.id == log_id, AutomationLog.user_id == user_id).first()
        if not log:
            return {"status": "FAILURE", "error": "HTTP_404:Automation log not found"}

        def _s(log):
            return {
                "id": log.id, "source": log.source, "task_name": log.task_name,
                "payload": log.payload, "status": log.status,
                "attempt_count": log.attempt_count, "max_attempts": log.max_attempts,
                "error_message": log.error_message, "result": log.result,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "scheduled_for": log.scheduled_for.isoformat() if log.scheduled_for else None,
            }

        return {"status": "SUCCESS", "output_patch": {"automation_log_get_result": _s(log)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def automation_log_replay_node(state, context):
    try:
        from uuid import UUID
        from apps.automation.models import AutomationLog

        db = context.get("db")
        user_id = UUID(str(context.get("user_id")))
        log_id = state.get("log_id")
        log = db.query(AutomationLog).filter(AutomationLog.id == log_id, AutomationLog.user_id == user_id).first()
        if not log:
            return {"status": "FAILURE", "error": "HTTP_404:Automation log not found"}
        if log.status not in ("failed", "retrying"):
            return {"status": "FAILURE", "error": f"HTTP_400:Cannot replay log with status '{log.status}'. Only failed or retrying logs can be replayed."}
        from AINDY.platform_layer.scheduler_service import replay_task

        result = replay_task(log_id)
        if not result:
            return {"status": "FAILURE", "error": "HTTP_500:Replay failed - task function not registered. Check task registry."}
        return {"status": "SUCCESS", "output_patch": {"automation_log_replay_result": {"log_id": log_id, "status": "replay_scheduled", "message": "Task replay has been scheduled. Check GET /automation/logs/{id} for status updates."}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def automation_scheduler_status_node(state, context):
    try:
        from AINDY.platform_layer.scheduler_service import get_scheduler

        try:
            scheduler = get_scheduler()
            jobs = scheduler.get_jobs()
            running = scheduler.running
        except RuntimeError as exc:
            return {"status": "FAILURE", "error": f"HTTP_503:{exc}"}
        return {"status": "SUCCESS", "output_patch": {"automation_scheduler_status_result": {
            "running": running,
            "job_count": len(jobs),
            "jobs": [{"id": job.id, "name": job.name, "next_run": job.next_run_time.isoformat() if job.next_run_time else None, "trigger": str(job.trigger)} for job in jobs],
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}

def automation_task_trigger_node(state, context):
    try:
        from apps.tasks.services.task_service import get_task_by_id, queue_task_automation

        db = context.get("db")
        user_id = context.get("user_id")
        task_id = state.get("task_id")
        automation_type = state.get("automation_type")
        automation_config = state.get("automation_config")
        task = get_task_by_id(db, task_id, user_id)
        if not task:
            return {"status": "FAILURE", "error": "HTTP_404:Task not found"}
        if automation_type is not None:
            task.automation_type = automation_type
        if automation_config is not None:
            task.automation_config = automation_config
        db.commit()
        db.refresh(task)
        if not task.automation_type:
            return {"status": "FAILURE", "error": "HTTP_422:task_automation_not_configured"}
        dispatch = queue_task_automation(db=db, task=task, user_id=user_id, reason="manual_trigger")
        if not dispatch:
            return {"status": "FAILURE", "error": "HTTP_500:task_automation_dispatch_failed"}
        return {"status": "SUCCESS", "output_patch": {"automation_task_trigger_result": dispatch}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


# -- Registration -------------------------------------------------------------

def register() -> None:
    register_nodes(
        {
            "automation_logs_list_node": automation_logs_list_node,
            "automation_log_get_node": automation_log_get_node,
            "automation_log_replay_node": automation_log_replay_node,
            "automation_scheduler_status_node": automation_scheduler_status_node,
            "automation_task_trigger_node": automation_task_trigger_node,
        }
    )
    register_single_node_flows(
        {
            "automation_logs_list": "automation_logs_list_node",
            "automation_log_get": "automation_log_get_node",
            "automation_log_replay": "automation_log_replay_node",
            "automation_scheduler_status": "automation_scheduler_status_node",
            "automation_task_trigger": "automation_task_trigger_node",
        }
    )
