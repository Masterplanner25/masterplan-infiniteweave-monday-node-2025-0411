from __future__ import annotations

import uuid


def test_emit_system_event_persists_to_test_db(db_session, test_user):
    from db.models.system_event import SystemEvent
    from services.system_event_service import emit_system_event

    trace_id = str(uuid.uuid4())
    emit_system_event(
        db=db_session,
        event_type="execution.started",
        user_id=test_user.id,
        trace_id=trace_id,
        payload={"status": "started"},
        required=True,
    )

    rows = db_session.query(SystemEvent).all()
    assert len(rows) == 1
    assert rows[0].type == "execution.started"
    assert rows[0].trace_id == trace_id
