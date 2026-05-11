from AINDY.runtime.flow_engine.serialization import _json_safe
from AINDY.runtime.flow_engine.shared import Session, logger, parse_user_id


def route_event(
    event_type: str,
    payload: dict,
    db: Session,
    user_id: str = None,
) -> list[dict]:
    from AINDY.db.models.flow_run import FlowRun
    from AINDY.kernel.scheduler_engine import get_scheduler_engine

    scheduler = get_scheduler_engine()
    corr = (payload or {}).get("correlation_id") or None
    results: list[dict] = []
    matching_run_ids = scheduler.peek_matching_run_ids(event_type, correlation_id=corr)
    if not matching_run_ids:
        logger.debug(
            "[route_event] no waiting runs matched event=%s corr=%s - skipping injection",
            event_type,
            corr,
        )
        query_runs = []
    else:
        query_runs = (
            db.query(FlowRun)
            .filter(FlowRun.id.in_(matching_run_ids), FlowRun.status == "waiting")
            .all()
        )

    for run in query_runs:
        try:
            state = dict(run.state or {})
            state["event"] = payload
            run.state = _json_safe(state)
            db.flush()
            results.append({"run_id": str(run.id), "payload_injected": True})
            logger.debug(
                "[route_event] payload injected run=%s event=%s",
                run.id,
                event_type,
            )
        except Exception as exc:
            logger.warning("[route_event] payload inject failed run=%s: %s", run.id, exc)

    try:
        db.commit()
    except Exception as exc:
        logger.warning("[route_event] state commit failed event=%s: %s", event_type, exc)

    try:
        from AINDY.kernel.event_bus import publish_event

        resumed = publish_event(event_type, correlation_id=corr)
        logger.info(
            "[route_event] publish_event resumed=%d event=%s corr=%s",
            resumed,
            event_type,
            corr,
        )
    except Exception as exc:
        logger.warning("[route_event] publish_event failed event=%s: %s", event_type, exc)
    return results


def record_outcome(
    event_type: str,
    flow_name: str,
    success: bool,
    execution_time_ms: int = 0,
    user_id: str = None,
    workflow_type: str = None,
    metadata: dict = None,
    db: Session = None,
) -> None:
    if not db:
        return
    from AINDY.db.models.flow_run import EventOutcome

    try:
        outcome = EventOutcome(
            event_type=event_type,
            flow_name=flow_name,
            workflow_type=workflow_type,
            success=success,
            execution_time_ms=execution_time_ms,
            user_id=parse_user_id(user_id),
            event_metadata=metadata or {},
        )
        db.add(outcome)
        db.commit()
    except Exception as exc:
        logger.warning("record_outcome failed: %s", exc)
