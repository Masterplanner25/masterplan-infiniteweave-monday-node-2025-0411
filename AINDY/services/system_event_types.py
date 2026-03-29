from __future__ import annotations


class SystemEventTypes:
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"

    FLOW_NODE_STARTED = "flow.node.started"
    FLOW_WAITING = "flow.waiting"
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

    FREELANCE_DELIVERY_STARTED = "freelance.delivery.started"
    FREELANCE_DELIVERY_COMPLETED = "freelance.delivery.completed"
    FREELANCE_DELIVERY_FAILED = "freelance.delivery.failed"
