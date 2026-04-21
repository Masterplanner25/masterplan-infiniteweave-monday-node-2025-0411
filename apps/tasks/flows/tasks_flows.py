from apps.automation.flows._flow_registration import register_nodes, register_single_node_flows


def tasks_list_node(state, context):
    try:
        import uuid
        from apps.tasks.models import Task

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        tasks = db.query(Task).filter(Task.user_id == user_id).all()
        data = [
            {
                "task_id": t.id,
                "task_name": t.name,
                "category": t.category,
                "priority": t.priority,
                "status": getattr(t, "status", "unknown"),
                "time_spent": t.time_spent,
                "masterplan_id": getattr(t, "masterplan_id", None),
                "parent_task_id": getattr(t, "parent_task_id", None),
                "depends_on": getattr(t, "depends_on", []) or [],
                "dependency_type": getattr(t, "dependency_type", "hard"),
                "automation_type": getattr(t, "automation_type", None),
                "automation_config": getattr(t, "automation_config", None),
            }
            for t in tasks
        ]
        return {"status": "SUCCESS", "output_patch": {"tasks_list_result": data}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def tasks_recurrence_check_node(state, context):
    try:
        import threading
        from apps.tasks.services.task_service import handle_recurrence

        t = threading.Thread(target=handle_recurrence, daemon=True)
        t.start()
        return {"status": "SUCCESS", "output_patch": {"tasks_recurrence_check_result": {
            "message": "Recurrence job started in background."
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def register() -> None:
    register_nodes(
        {
            "tasks_list_node": tasks_list_node,
            "tasks_recurrence_check_node": tasks_recurrence_check_node,
        }
    )
    register_single_node_flows(
        {
            "tasks_list": "tasks_list_node",
            "tasks_recurrence_check": "tasks_recurrence_check_node",
        }
    )
