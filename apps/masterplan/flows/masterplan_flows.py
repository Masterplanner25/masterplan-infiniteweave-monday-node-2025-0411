from AINDY.runtime.flow_helpers import register_nodes, register_single_node_flows


def goals_list_node(state, context):
    try:
        from apps.masterplan.services.goal_service import get_active_goals

        db = context.get("db")
        user_id = context.get("user_id")
        return {"status": "SUCCESS", "output_patch": {"goals_list_result": get_active_goals(db, user_id)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def goals_state_node(state, context):
    try:
        from apps.masterplan.services.goal_service import detect_goal_drift, get_goal_states

        db = context.get("db")
        user_id = context.get("user_id")
        result = {
            "goals": get_goal_states(db, user_id),
            "drift": detect_goal_drift(db, user_id),
        }
        return {"status": "SUCCESS", "output_patch": {"goals_state_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def genesis_session_create_node(state, context):
    try:
        import uuid
        from apps.masterplan.models import GenesisSessionDB

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session = GenesisSessionDB(
            user_id=user_id,
            synthesis_ready=False,
            summarized_state={
                "vision_summary": None, "time_horizon": None, "mechanism_summary": None,
                "assets_summary": None, "inferred_domains": [], "inferred_phases": [], "confidence": 0.0,
            },
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return {"status": "SUCCESS", "output_patch": {"genesis_session_create_result": {"session_id": session.id}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def genesis_session_get_node(state, context):
    try:
        import uuid
        from apps.masterplan.models import GenesisSessionDB

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session_id = state.get("session_id")
        session = db.query(GenesisSessionDB).filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == user_id,
        ).first()
        if not session:
            return {"status": "FAILURE", "error": "HTTP_404:GenesisSession not found"}
        result = {
            "session_id": session.id,
            "status": session.status,
            "synthesis_ready": session.synthesis_ready,
            "summarized_state": session.summarized_state,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
        return {"status": "SUCCESS", "output_patch": {"genesis_session_get_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def genesis_draft_get_node(state, context):
    try:
        import uuid
        from apps.masterplan.models import GenesisSessionDB

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session_id = state.get("session_id")
        session = db.query(GenesisSessionDB).filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == user_id,
        ).first()
        if not session:
            return {"status": "FAILURE", "error": "HTTP_404:GenesisSession not found"}
        if not session.draft_json:
            return {"status": "FAILURE", "error": "HTTP_404:No draft available yet - run /genesis/synthesize first"}
        result = {
            "session_id": session.id,
            "draft": session.draft_json,
            "synthesis_ready": session.synthesis_ready,
        }
        return {"status": "SUCCESS", "output_patch": {"genesis_draft_get_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def genesis_synthesize_node(state, context):
    try:
        import uuid
        from apps.masterplan.models import GenesisSessionDB
        from apps.masterplan.services.genesis_ai import call_genesis_synthesis_llm

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session_id = state.get("session_id")
        session = db.query(GenesisSessionDB).filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == user_id,
        ).first()
        if not session:
            return {"status": "FAILURE", "error": "HTTP_404:GenesisSession not found"}
        if not session.synthesis_ready:
            return {"status": "FAILURE", "error": "HTTP_422:Session is not ready for synthesis yet"}
        current_state = session.summarized_state or {}
        draft = call_genesis_synthesis_llm(current_state, user_id=str(user_id), db=db)
        session.draft_json = draft
        db.commit()
        return {"status": "SUCCESS", "output_patch": {"genesis_synthesize_result": {"draft": draft}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def genesis_audit_node(state, context):
    try:
        import uuid
        from apps.masterplan.models import GenesisSessionDB
        from apps.masterplan.services.genesis_ai import validate_draft_integrity

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session_id = state.get("session_id")
        session = db.query(GenesisSessionDB).filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == user_id,
        ).first()
        if not session:
            return {"status": "FAILURE", "error": "HTTP_404:GenesisSession not found"}
        if not session.draft_json:
            return {"status": "FAILURE", "error": "HTTP_422:No draft available - run /genesis/synthesize first"}
        return {"status": "SUCCESS", "output_patch": {"genesis_audit_result": validate_draft_integrity(session.draft_json)}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def genesis_lock_node(state, context):
    try:
        import uuid
        from AINDY.core.execution_signal_helper import queue_memory_capture
        from apps.masterplan.models import GenesisSessionDB
        from apps.masterplan.services.masterplan_factory import create_masterplan_from_genesis

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        session_id = state.get("session_id")
        draft = state.get("draft")
        session = db.query(GenesisSessionDB).filter(
            GenesisSessionDB.id == session_id,
            GenesisSessionDB.user_id == user_id,
        ).first()
        if not session:
            return {"status": "FAILURE", "error": "HTTP_404:GenesisSession not found"}
        try:
            masterplan = create_masterplan_from_genesis(
                session_id=session_id, draft=draft, db=db, user_id=str(user_id)
            )
        except Exception as e:
            return {"status": "FAILURE", "error": f"HTTP_400:Failed to create masterplan: {e}"}
        try:
            vision = str(draft.get("vision_statement") or draft.get("vision_summary") or "") if isinstance(draft, dict) else ""
            queue_memory_capture(
                db=db, user_id=str(user_id), agent_namespace="genesis",
                event_type="masterplan_locked",
                content=f"Masterplan locked: {masterplan.version_label} (posture: {masterplan.posture}, session: {session_id}). Vision: {vision[:200]}",
                source="genesis_lock", tags=["genesis", "masterplan", "decision"],
                node_type="decision", force=True,
            )
        except Exception:
            pass
        return {"status": "SUCCESS", "output_patch": {"genesis_lock_result": {
            "masterplan_id": masterplan.id,
            "version": masterplan.version_label,
            "posture": masterplan.posture,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def genesis_activate_node(state, context):
    try:
        import uuid
        from datetime import datetime, timezone
        from AINDY.core.execution_signal_helper import queue_memory_capture
        from apps.masterplan.models import MasterPlan

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        plan_id = state.get("plan_id")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        db.query(MasterPlan).filter(MasterPlan.user_id == user_id).update({"is_active": False})
        plan.is_active = True
        plan.status = "active"
        plan.activated_at = datetime.now(timezone.utc)
        db.commit()
        try:
            queue_memory_capture(
                db=db, user_id=str(user_id), agent_namespace="genesis",
                event_type="masterplan_activated",
                content=f"Masterplan activated: {plan.version_label} (id: {plan_id})",
                source="genesis_activate", tags=["genesis", "masterplan", "activation"],
                node_type="decision", force=True,
            )
        except Exception:
            pass
        return {"status": "SUCCESS", "output_patch": {"genesis_activate_result": {"activation_status": "activated"}}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def masterplan_lock_from_genesis_node(state, context):
    try:
        from apps.masterplan.services.masterplan_factory import create_masterplan_from_genesis
        from apps.masterplan.services.masterplan_execution_service import sync_masterplan_tasks
        from apps.masterplan.services.posture import posture_description

        db = context.get("db")
        user_id = str(context.get("user_id"))
        session_id = state.get("session_id")
        draft = state.get("draft", {})
        if not session_id:
            return {"status": "FAILURE", "error": "HTTP_400:session_id is required"}
        try:
            masterplan = create_masterplan_from_genesis(session_id=session_id, draft=draft, db=db, user_id=user_id)
        except ValueError as e:
            return {"status": "FAILURE", "error": f"HTTP_422:Masterplan validation failed: {e}"}
        except Exception as e:
            return {"status": "FAILURE", "error": f"HTTP_400:Failed to create masterplan: {e}"}
        task_sync = sync_masterplan_tasks(db=db, masterplan=masterplan, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"masterplan_lock_from_genesis_result": {
            "masterplan_id": masterplan.id,
            "version": masterplan.version_label,
            "posture_description": posture_description(masterplan.posture),
            "posture": masterplan.posture,
            "status": masterplan.status,
            "task_sync": task_sync,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def masterplan_lock_node(state, context):
    try:
        from datetime import datetime, timezone
        from apps.masterplan.models import MasterPlan
        from apps.masterplan.services.masterplan_execution_service import sync_masterplan_tasks

        db = context.get("db")
        user_id = str(context.get("user_id"))
        plan_id = state.get("plan_id")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        if plan.status == "locked":
            return {"status": "FAILURE", "error": "HTTP_400:Plan is already locked"}
        plan.status = "locked"
        plan.locked_at = datetime.now(timezone.utc)
        db.commit()
        task_sync = sync_masterplan_tasks(db=db, masterplan=plan, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"masterplan_lock_result": {
            "plan_id": plan.id, "status": plan.status, "task_sync": task_sync,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def masterplan_list_node(state, context):
    try:
        from apps.masterplan.models import MasterPlan

        db = context.get("db")
        user_id = str(context.get("user_id"))
        plans = db.query(MasterPlan).filter(MasterPlan.user_id == user_id).order_by(MasterPlan.id.desc()).all()
        return {"status": "SUCCESS", "output_patch": {"masterplan_list_result": {
            "plans": [
                {
                    "id": p.id, "version_label": p.version_label, "posture": p.posture,
                    "status": p.status, "is_active": p.is_active,
                    "created_at": p.created_at, "locked_at": p.locked_at, "activated_at": p.activated_at,
                }
                for p in plans
            ]
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def masterplan_get_node(state, context):
    try:
        from apps.masterplan.models import MasterPlan
        from apps.masterplan.services.masterplan_execution_service import get_masterplan_execution_status

        db = context.get("db")
        user_id = str(context.get("user_id"))
        plan_id = state.get("plan_id")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        execution_status = get_masterplan_execution_status(db=db, masterplan_id=plan.id, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"masterplan_get_result": {
            "id": plan.id, "version_label": plan.version_label, "posture": plan.posture,
            "status": plan.status, "is_active": plan.is_active, "structure_json": plan.structure_json,
            "created_at": plan.created_at, "locked_at": plan.locked_at, "activated_at": plan.activated_at,
            "linked_genesis_session_id": plan.linked_genesis_session_id,
            "execution_status": execution_status,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def masterplan_anchor_node(state, context):
    try:
        from datetime import datetime
        from apps.masterplan.models import MasterPlan

        db = context.get("db")
        user_id = str(context.get("user_id"))
        plan_id = state.get("plan_id")
        anchor_date = state.get("anchor_date")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        if anchor_date is not None:
            try:
                plan.anchor_date = datetime.fromisoformat(anchor_date)
            except ValueError:
                return {"status": "FAILURE", "error": "HTTP_422:anchor_date must be ISO format"}
        if state.get("goal_value") is not None:
            plan.goal_value = state["goal_value"]
        if state.get("goal_unit") is not None:
            plan.goal_unit = state["goal_unit"]
        if state.get("goal_description") is not None:
            plan.goal_description = state["goal_description"]
        db.commit()
        return {"status": "SUCCESS", "output_patch": {"masterplan_anchor_result": {
            "plan_id": plan.id,
            "anchor_date": plan.anchor_date.isoformat() if plan.anchor_date else None,
            "goal_value": plan.goal_value,
            "goal_unit": plan.goal_unit,
            "goal_description": plan.goal_description,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def masterplan_projection_node(state, context):
    try:
        from apps.masterplan.models import MasterPlan
        from apps.masterplan.services.eta_service import calculate_eta

        db = context.get("db")
        user_id = str(context.get("user_id"))
        plan_id = state.get("plan_id")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        try:
            result = calculate_eta(db=db, masterplan_id=plan_id, user_id=user_id)
        except Exception as exc:
            return {"status": "FAILURE", "error": f"HTTP_500:eta_calculation_failed: {exc}"}
        return {"status": "SUCCESS", "output_patch": {"masterplan_projection_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def masterplan_activate_node(state, context):
    try:
        from datetime import datetime, timezone
        from apps.masterplan.models import MasterPlan
        from apps.masterplan.services.masterplan_execution_service import get_masterplan_execution_status, sync_masterplan_tasks

        db = context.get("db")
        user_id = str(context.get("user_id"))
        plan_id = state.get("plan_id")
        plan = db.query(MasterPlan).filter(MasterPlan.id == plan_id, MasterPlan.user_id == user_id).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:Plan not found"}
        db.query(MasterPlan).filter(MasterPlan.user_id == user_id).update({"is_active": False})
        plan.is_active = True
        plan.status = "active"
        plan.activated_at = datetime.now(timezone.utc)
        db.commit()
        task_sync = sync_masterplan_tasks(db=db, masterplan=plan, user_id=user_id)
        execution_status = get_masterplan_execution_status(db=db, masterplan_id=plan.id, user_id=user_id)
        return {"status": "SUCCESS", "output_patch": {"masterplan_activate_result": {
            "status": "activated", "plan_id": plan.id,
            "task_sync": task_sync, "execution_status": execution_status,
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def register() -> None:
    register_nodes(
        {
            "goals_list_node": goals_list_node,
            "goals_state_node": goals_state_node,
            "genesis_session_create_node": genesis_session_create_node,
            "genesis_session_get_node": genesis_session_get_node,
            "genesis_draft_get_node": genesis_draft_get_node,
            "genesis_synthesize_node": genesis_synthesize_node,
            "genesis_audit_node": genesis_audit_node,
            "genesis_lock_node": genesis_lock_node,
            "genesis_activate_node": genesis_activate_node,
            "masterplan_lock_from_genesis_node": masterplan_lock_from_genesis_node,
            "masterplan_lock_node": masterplan_lock_node,
            "masterplan_list_node": masterplan_list_node,
            "masterplan_get_node": masterplan_get_node,
            "masterplan_anchor_node": masterplan_anchor_node,
            "masterplan_projection_node": masterplan_projection_node,
            "masterplan_activate_node": masterplan_activate_node,
        }
    )
    register_single_node_flows(
        {
            "goals_list": "goals_list_node",
            "goals_state": "goals_state_node",
            "genesis_session_create": "genesis_session_create_node",
            "genesis_session_get": "genesis_session_get_node",
            "genesis_draft_get": "genesis_draft_get_node",
            "genesis_synthesize": "genesis_synthesize_node",
            "genesis_audit": "genesis_audit_node",
            "genesis_lock": "genesis_lock_node",
            "genesis_activate": "genesis_activate_node",
            "masterplan_lock_from_genesis": "masterplan_lock_from_genesis_node",
            "masterplan_lock": "masterplan_lock_node",
            "masterplan_list": "masterplan_list_node",
            "masterplan_get": "masterplan_get_node",
            "masterplan_anchor": "masterplan_anchor_node",
            "masterplan_projection": "masterplan_projection_node",
            "masterplan_activate": "masterplan_activate_node",
        }
    )
