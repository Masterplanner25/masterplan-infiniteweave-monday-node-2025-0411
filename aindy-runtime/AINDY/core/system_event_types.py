from __future__ import annotations


class SystemEventTypes:
    STARTUP_RECOVERY_FAILED = "startup.recovery.failed"
    STARTUP_RECOVERY_COMPLETED = "startup.recovery.completed"

    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_WAITING = "execution.waiting"
    EXECUTION_STEP_COMPLETED = "execution.step.completed"
    ANALYTICS_SCORE_UPDATED = "analytics.score.updated"
    MASTERPLAN_GOAL_STATE_CHANGED = "masterplan.goal_state.changed"

    FLOW_NODE_STARTED = "flow.node.started"
    FLOW_WAITING = "flow.waiting"
    WAIT_TIMEOUT = "WAIT_TIMEOUT"
    FLOW_NODE_COMPLETED = "flow.node.completed"
    FLOW_NODE_FAILED = "flow.node.failed"

    ASYNC_JOB_STARTED = "async_job.started"
    ASYNC_JOB_COMPLETED = "async_job.completed"
    ASYNC_JOB_FAILED = "async_job.failed"

    AGENT_STEP = "agent.step"
    AGENT_STEP_COMPLETED = "agent.step.completed"
    AGENT_STEP_FAILED = "agent.step.failed"

    MEMORY_WRITE = "memory.write"
    MEMORY_WRITE_FAILED = "error.memory_write"
    EMBEDDING_STARTED = "embedding.started"
    EMBEDDING_COMPLETED = "embedding.completed"
    EMBEDDING_FAILED = "embedding.failed"
    AUTONOMY_DECISION = "autonomy.decision"

    FEEDBACK_RETRY_DETECTED = "feedback.retry_detected"
    FEEDBACK_LATENCY_SPIKE = "feedback.latency_spike"
    FEEDBACK_ABANDONMENT_DETECTED = "feedback.abandonment_detected"
    FEEDBACK_REPEATED_FAILURE = "feedback.repeated_failure"

    NODUS_EXECUTE_STARTED = "nodus.execute.started"
    NODUS_EXECUTE_COMPLETED = "nodus.execute.completed"
    NODUS_EXECUTE_FAILED = "nodus.execute.failed"

    NODUS_EVENT_EMITTED = "nodus.event.emitted"
    NODUS_EVENT_WAIT_REQUESTED = "nodus.event.wait_requested"
    NODUS_EVENT_WAIT_RESUMED = "nodus.event.wait_resumed"

    NODUS_TRACE_STEP = "nodus.trace.step"
    NODUS_TRACE_COMPLETE = "nodus.trace.complete"

    SYSCALL_EXECUTED = "syscall.executed"


