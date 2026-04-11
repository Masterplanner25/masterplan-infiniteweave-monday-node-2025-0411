"""Temporary: does ts1.close() behavior differ when run first vs second?"""
from __future__ import annotations
import uuid
from sqlalchemy import text


def _count_flow_runs(session_factory):
    s = session_factory()
    try:
        return s.execute(text("SELECT COUNT(*) FROM flow_runs")).scalar()
    finally:
        s.close()


def _run_scenario(db_session_factory, testing_session_factory, label=""):
    from AINDY.db.models.flow_run import FlowRun

    sf = db_session_factory()
    fr_id = str(uuid.uuid4())
    fr = FlowRun(
        id=fr_id, flow_name='t', workflow_type='t',
        state={}, current_node='start', status='running',
        trace_id=str(uuid.uuid4()),
    )
    sf.add(fr)
    sf.commit()
    sf.refresh(fr)
    c0 = _count_flow_runs(testing_session_factory)
    print(f"\n[{label}] A: after sf.commit(FlowRun): count={c0}")

    ts1 = testing_session_factory()
    ts1.execute(text("SELECT 1")).fetchone()
    ts1.close()
    c1 = _count_flow_runs(testing_session_factory)
    print(f"[{label}] B: after ts1.close(): count={c1}")

    sf.close()
    return c1 == 1  # True if FlowRun survived


def test_scenario_alone(db_session_factory, testing_session_factory):
    """Run scenario without any preceding test."""
    result = _run_scenario(db_session_factory, testing_session_factory, label="ALONE")
    print(f"\n[ALONE] FlowRun survived ts1.close(): {result}")
    # Don't assert — just observe
