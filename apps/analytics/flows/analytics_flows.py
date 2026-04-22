import logging

from AINDY.platform_layer.registry import get_symbol
from apps.automation.flows._flow_registration import register_nodes, register_single_node_flows

logger = logging.getLogger(__name__)


def score_get_node(state, context):
    try:
        import uuid
        from apps.analytics.models import UserScore, KPI_WEIGHTS

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))

        score = db.query(UserScore).filter(UserScore.user_id == user_id).first()
        if not score:
            from apps.analytics.services.infinity_orchestrator import execute as execute_infinity_orchestrator

            result = execute_infinity_orchestrator(user_id=user_id, db=db, trigger_event="manual")
            if result:
                return {"status": "SUCCESS", "output_patch": {"score_get_result": result["score"]}}
            return {"status": "SUCCESS", "output_patch": {"score_get_result": {
                "user_id": str(user_id), "master_score": 0.0, "kpis": {}, "message": "No score yet.",
            }}}

        from apps.analytics.services.infinity_loop import get_latest_adjustment, serialize_adjustment

        latest = get_latest_adjustment(user_id=str(user_id), db=db)
        serialized = serialize_adjustment(latest)
        latest_payload = None
        memory_visibility = {"memory_context_count": 0, "memory_signal_count": 0}
        if serialized:
            adj_payload = (serialized.get("adjustment_payload") or {})
            loop_context = adj_payload.get("loop_context") or {}
            memory_signals = list(loop_context.get("memory_signals") or [])
            memory_visibility = {
                "memory_context_count": len(loop_context.get("memory") or []),
                "memory_signal_count": len(memory_signals),
            }
            latest_payload = {
                "decision_type": serialized["decision_type"],
                "applied_at": serialized["applied_at"],
                "adjustment_payload": serialized["adjustment_payload"],
            }

        result = {
            "user_id": str(user_id),
            "master_score": score.master_score,
            "kpis": {
                "execution_speed": score.execution_speed_score,
                "decision_efficiency": score.decision_efficiency_score,
                "ai_productivity_boost": score.ai_productivity_boost_score,
                "focus_quality": score.focus_quality_score,
                "masterplan_progress": score.masterplan_progress_score,
            },
            "weights": KPI_WEIGHTS,
            "metadata": {
                "confidence": score.confidence,
                "data_points_used": score.data_points_used,
                "trigger_event": score.trigger_event,
                "calculated_at": score.calculated_at.isoformat() if score.calculated_at else None,
                "memory_context_count": memory_visibility["memory_context_count"],
                "memory_signal_count": memory_visibility["memory_signal_count"],
            },
            "latest_adjustment": latest_payload,
        }
        return {"status": "SUCCESS", "output_patch": {"score_get_result": result}}
    except Exception as e:
        logger.error("score_get_node error: %s", e)
        return {"status": "FAILURE", "error": str(e)}


def score_history_node(state, context):
    try:
        import uuid
        from apps.analytics.models import ScoreHistory

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        limit = state.get("limit", 30)
        history = (
            db.query(ScoreHistory)
            .filter(ScoreHistory.user_id == user_id)
            .order_by(ScoreHistory.calculated_at.desc())
            .limit(limit)
            .all()
        )
        result = {
            "user_id": str(user_id),
            "history": [
                {
                    "master_score": h.master_score,
                    "calculated_at": h.calculated_at.isoformat() if h.calculated_at else None,
                }
                for h in history
            ],
        }
        return {"status": "SUCCESS", "output_patch": {"score_history_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def score_feedback_list_node(state, context):
    try:
        import uuid
        from apps.automation.models import UserFeedback

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        limit = state.get("limit", 50)
        history = (
            db.query(UserFeedback)
            .filter(UserFeedback.user_id == user_id)
            .order_by(UserFeedback.created_at.desc())
            .limit(limit)
            .all()
        )
        return {"status": "SUCCESS", "output_patch": {"score_feedback_list_result": {
            "user_id": str(user_id),
            "count": len(history),
        }}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def analytics_linkedin_ingest_node(state, context):
    try:
        import uuid
        from apps.analytics.models import CanonicalMetricDB
        from apps.analytics.schemas.analytics import LinkedInRawInput
        from apps.social.services.linkedin_adapter import linkedin_adapter

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        data_dict = state.get("data", {})
        masterplan_id = data_dict.get("masterplan_id")
        MasterPlan = get_symbol("MasterPlan")
        if MasterPlan is None:
            return {"status": "FAILURE", "error": "HTTP_503:MasterPlan model unavailable"}

        plan = db.query(MasterPlan).filter(
            MasterPlan.id == masterplan_id,
            MasterPlan.user_id == user_id,
        ).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:MasterPlan not found"}

        data = LinkedInRawInput(**data_dict)
        canonical = linkedin_adapter(data)
        canonical["user_id"] = user_id

        existing = db.query(CanonicalMetricDB).filter_by(
            masterplan_id=canonical["masterplan_id"],
            platform=canonical["platform"],
            scope_type=canonical["scope_type"],
            scope_id=canonical["scope_id"],
            period_type=canonical["period_type"],
            period_start=canonical["period_start"],
        ).first()

        if existing:
            for key, value in canonical.items():
                setattr(existing, key, value)
            db_record = existing
        else:
            db_record = CanonicalMetricDB(**canonical)
            db.add(db_record)

        db.commit()
        db.refresh(db_record)
        return {"status": "SUCCESS", "output_patch": {"analytics_linkedin_ingest_result": db_record}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def analytics_masterplan_get_node(state, context):
    try:
        import uuid
        from apps.analytics.models import CanonicalMetricDB

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        masterplan_id = state.get("masterplan_id")
        period_type = state.get("period_type")
        platform = state.get("platform")
        scope_type = state.get("scope_type")
        MasterPlan = get_symbol("MasterPlan")
        if MasterPlan is None:
            return {"status": "FAILURE", "error": "HTTP_503:MasterPlan model unavailable"}

        plan = db.query(MasterPlan).filter(
            MasterPlan.id == masterplan_id,
            MasterPlan.user_id == user_id,
        ).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:MasterPlan not found"}

        query = db.query(CanonicalMetricDB).filter(CanonicalMetricDB.masterplan_id == masterplan_id)
        if period_type:
            query = query.filter(CanonicalMetricDB.period_type == period_type)
        if platform:
            query = query.filter(CanonicalMetricDB.platform == platform)
        if scope_type:
            query = query.filter(CanonicalMetricDB.scope_type == scope_type)

        return {"status": "SUCCESS", "output_patch": {
            "analytics_masterplan_get_result": query.order_by(CanonicalMetricDB.period_start.desc()).all()
        }}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def analytics_masterplan_summary_node(state, context):
    try:
        import uuid
        from apps.analytics.models import CanonicalMetricDB

        db = context.get("db")
        user_id = uuid.UUID(str(context.get("user_id")))
        masterplan_id = state.get("masterplan_id")
        group_by = state.get("group_by")
        MasterPlan = get_symbol("MasterPlan")
        if MasterPlan is None:
            return {"status": "FAILURE", "error": "HTTP_503:MasterPlan model unavailable"}

        plan = db.query(MasterPlan).filter(
            MasterPlan.id == masterplan_id,
            MasterPlan.user_id == user_id,
        ).first()
        if not plan:
            return {"status": "FAILURE", "error": "HTTP_404:MasterPlan not found"}

        records = (
            db.query(CanonicalMetricDB)
            .filter(CanonicalMetricDB.masterplan_id == masterplan_id)
            .order_by(CanonicalMetricDB.period_start.asc())
            .all()
        )
        if not records:
            return {"status": "SUCCESS", "output_patch": {"analytics_masterplan_summary_result": {"message": "No telemetry records found."}}}

        if group_by == "period":
            grouped = {}
            for r in records:
                key = (r.period_type, r.period_start)
                if key not in grouped:
                    grouped[key] = {"period_type": r.period_type, "period_start": r.period_start, "period_end": r.period_end,
                                    "totals": {k: 0 for k in ["passive_visibility", "active_discovery", "unique_reach",
                                                               "interaction_volume", "deep_attention_units", "intent_signals",
                                                               "conversion_events", "growth_velocity"]}}
                g = grouped[key]["totals"]
                for k in g:
                    g[k] += getattr(r, k) or 0
            output = []
            for (ptype, _pstart), data in grouped.items():
                t = data["totals"]
                vis = t["passive_visibility"] or 1
                reach = t["unique_reach"] or 1
                intent = t["intent_signals"] or 1
                output.append({
                    "period_type": ptype,
                    "period_start": data["period_start"],
                    "period_end": data["period_end"],
                    "totals": t,
                    "rates": {
                        "interaction_rate": t["interaction_volume"] / vis,
                        "attention_rate": t["deep_attention_units"] / vis,
                        "intent_rate": t["intent_signals"] / reach,
                        "conversion_rate": t["conversion_events"] / intent,
                        "discovery_ratio": t["active_discovery"] / vis,
                        "growth_rate": t["growth_velocity"] / reach,
                    },
                })
            result = {"masterplan_id": masterplan_id, "grouped": output}
        else:
            totals = {k: sum(getattr(r, k) or 0 for r in records)
                      for k in ["passive_visibility", "active_discovery", "unique_reach",
                                 "interaction_volume", "deep_attention_units", "intent_signals",
                                 "conversion_events", "growth_velocity"]}
            vis = totals["passive_visibility"] or 1
            reach = totals["unique_reach"] or 1
            intent = totals["intent_signals"] or 1
            result = {
                "masterplan_id": masterplan_id,
                "record_count": len(records),
                "totals": totals,
                "rates": {
                    "interaction_rate": totals["interaction_volume"] / vis,
                    "attention_rate": totals["deep_attention_units"] / vis,
                    "intent_rate": totals["intent_signals"] / reach,
                    "conversion_rate": totals["conversion_events"] / intent,
                    "discovery_ratio": totals["active_discovery"] / vis,
                    "growth_rate": totals["growth_velocity"] / reach,
                },
            }
        return {"status": "SUCCESS", "output_patch": {"analytics_masterplan_summary_result": result}}
    except Exception as e:
        return {"status": "FAILURE", "error": str(e)}


def register() -> None:
    register_nodes(
        {
            "score_get_node": score_get_node,
            "score_history_node": score_history_node,
            "score_feedback_list_node": score_feedback_list_node,
            "analytics_linkedin_ingest_node": analytics_linkedin_ingest_node,
            "analytics_masterplan_get_node": analytics_masterplan_get_node,
            "analytics_masterplan_summary_node": analytics_masterplan_summary_node,
        }
    )
    register_single_node_flows(
        {
            "score_get": "score_get_node",
            "score_history": "score_history_node",
            "score_feedback_list": "score_feedback_list_node",
            "analytics_linkedin_ingest": "analytics_linkedin_ingest_node",
            "analytics_masterplan_get": "analytics_masterplan_get_node",
            "analytics_masterplan_summary": "analytics_masterplan_summary_node",
        }
    )
