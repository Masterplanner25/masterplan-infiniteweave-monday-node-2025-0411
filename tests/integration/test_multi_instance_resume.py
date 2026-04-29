"""
Integration test: flow started on Instance A is resumed by Instance B.

Uses fakeredis with shared state to simulate two independent SchedulerEngine
instances connected to the same Redis backend.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

try:
    import fakeredis

    HAS_FAKEREDIS = True
except ImportError:
    HAS_FAKEREDIS = False


pytestmark = [
    pytest.mark.multi_instance,
    pytest.mark.skipif(not HAS_FAKEREDIS, reason="fakeredis not installed"),
]


@pytest.fixture
def shared_redis():
    """Single fakeredis server shared by both SchedulerEngine instances."""
    server = fakeredis.FakeServer()
    return fakeredis.FakeRedis(server=server, decode_responses=True)


def _make_engine():
    from AINDY.kernel.scheduler_engine import SchedulerEngine

    engine = SchedulerEngine()
    engine.mark_rehydration_complete()
    return engine


class TestMultiInstanceResume:
    def test_instance_b_resumes_flow_started_on_instance_a(
        self,
        shared_redis,
        db_session,
        db_session_factory,
    ):
        """
        Scenario:
        1. Instance A: register_wait("run-123", "order.completed", ...)
        2. Instance A dies (simulated by not using it further)
        3. Instance B receives notify_event("order.completed")
        4. Assert: Instance B enqueues resume for run-123
        5. Assert: resume callback calls ExecutionUnitService.resume_execution_unit("eu-abc")
        """
        from AINDY.db.models.waiting_flow_run import WaitingFlowRun
        from AINDY.db.models.flow_run import FlowRun
        from AINDY.kernel.redis_wait_registry import RedisWaitRegistry
        from AINDY.kernel.resume_spec import RESUME_HANDLER_EU, ResumeSpec

        instance_a = _make_engine()
        eu_id = "eu-abc"
        run_id = "run-123"
        tenant_id = "tenant-test"

        spec = ResumeSpec(
            handler=RESUME_HANDLER_EU,
            eu_id=eu_id,
            tenant_id=tenant_id,
            run_id=run_id,
            eu_type="task",
        )
        registry = RedisWaitRegistry(shared_redis)
        registry.register(run_id, spec)

        db_session.add(
            FlowRun(
                id=run_id,
                flow_name="test.flow",
                workflow_type="test_flow",
                state={},
                current_node="wait_node",
                status="waiting",
                waiting_for="order.completed",
                trace_id=None,
            )
        )
        db_session.add(
            WaitingFlowRun(
                run_id=run_id,
                event_type="order.completed",
                correlation_id=None,
                eu_id=eu_id,
                priority="normal",
                instance_id="instance-a",
            )
        )
        db_session.commit()

        instance_b = _make_engine()
        resume_called: list[str] = []

        with patch("AINDY.kernel.event_bus.get_redis_client", return_value=shared_redis), patch(
            "AINDY.db.SessionLocal",
            db_session_factory,
        ), patch(
            "AINDY.core.execution_unit_service.ExecutionUnitService.resume_execution_unit",
            side_effect=lambda eu_id_arg: resume_called.append(eu_id_arg),
        ):
            count = instance_b.notify_event("order.completed", broadcast=False)

            assert count == 1
            item = instance_b.dequeue_next()
            assert item is not None
            assert item.execution_unit_id == eu_id
            assert item.run_id == run_id

            item.run_callback()

        assert resume_called == [eu_id]
        assert registry.get_spec(run_id) is None

        # Instance A is intentionally unused after registration; this keeps the
        # test faithful to the "origin instance died" scenario.
        assert instance_a.waiting_for(run_id) is None

    def test_only_one_instance_claims_concurrent_resume(
        self,
        shared_redis,
        db_session,
        db_session_factory,
    ):
        """
        When two instances call notify_event for the same run_id,
        exactly one enqueues the resume and the other finds the key already deleted.
        """
        from AINDY.db.models.waiting_flow_run import WaitingFlowRun
        from AINDY.db.models.flow_run import FlowRun
        from AINDY.kernel.redis_wait_registry import RedisWaitRegistry
        from AINDY.kernel.resume_spec import RESUME_HANDLER_EU, ResumeSpec

        run_id = "run-race"
        eu_id = "eu-race"
        tenant_id = "tenant-race"

        RedisWaitRegistry(shared_redis).register(
            run_id,
            ResumeSpec(
                handler=RESUME_HANDLER_EU,
                eu_id=eu_id,
                tenant_id=tenant_id,
                run_id=run_id,
                eu_type="flow",
            ),
        )
        db_session.add(
            FlowRun(
                id=run_id,
                flow_name="test.flow",
                workflow_type="test_flow",
                state={},
                current_node="wait_node",
                status="waiting",
                waiting_for="payment.received",
                trace_id=None,
            )
        )
        db_session.add(
            WaitingFlowRun(
                run_id=run_id,
                event_type="payment.received",
                correlation_id=None,
                eu_id=eu_id,
                priority="normal",
                instance_id="instance-a",
            )
        )
        db_session.commit()

        instance_b1 = _make_engine()
        instance_b2 = _make_engine()

        with patch("AINDY.kernel.event_bus.get_redis_client", return_value=shared_redis), patch(
            "AINDY.db.SessionLocal",
            db_session_factory,
        ), patch(
            "AINDY.core.execution_unit_service.ExecutionUnitService.resume_execution_unit",
        ):
            first = instance_b1.notify_event("payment.received", broadcast=False)
            second = instance_b2.notify_event("payment.received", broadcast=False)

        total_items = (
            instance_b1.queue_depth()["normal"] +
            instance_b2.queue_depth()["normal"]
        )
        assert first + second == 1
        assert total_items == 1

    def test_no_redis_falls_back_to_local_only(self):
        """When Redis is unavailable, cross-instance path is silently skipped."""
        engine = _make_engine()

        with patch("AINDY.kernel.event_bus.get_redis_client", return_value=None):
            count = engine.notify_event("any.event", broadcast=False)

        assert count == 0
        assert engine.queue_depth() == {"high": 0, "normal": 0, "low": 0}
