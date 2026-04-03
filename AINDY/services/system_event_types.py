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

    NODUS_EXECUTE_STARTED = "nodus.execute.started"
    NODUS_EXECUTE_COMPLETED = "nodus.execute.completed"
    NODUS_EXECUTE_FAILED = "nodus.execute.failed"

    NODUS_EVENT_EMITTED = "nodus.event.emitted"
    NODUS_EVENT_WAIT_REQUESTED = "nodus.event.wait_requested"
    NODUS_EVENT_WAIT_RESUMED = "nodus.event.wait_resumed"

    NODUS_TRACE_STEP = "nodus.trace.step"
    NODUS_TRACE_COMPLETE = "nodus.trace.complete"

    SYSCALL_EXECUTED = "syscall.executed"

    GENESIS_MESSAGE_STARTED = "genesis.message.started"
    GENESIS_MESSAGE_COMPLETED = "genesis.message.completed"
    GENESIS_MESSAGE_FAILED = "genesis.message.failed"

    GENESIS_SYNTHESIZE_STARTED = "genesis.synthesize.started"
    GENESIS_SYNTHESIZED = "genesis.synthesize.completed"
    GENESIS_SYNTHESIZE_FAILED = "genesis.synthesize.failed"

    GENESIS_LOCK_STARTED = "genesis.lock.started"
    GENESIS_LOCKED = "genesis.lock.completed"
    GENESIS_LOCK_FAILED = "genesis.lock.failed"

    GENESIS_ACTIVATE_STARTED = "genesis.activate.started"
    GENESIS_ACTIVATED = "genesis.activate.completed"
    GENESIS_ACTIVATE_FAILED = "genesis.activate.failed"

    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_PAUSED = "task.paused"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
