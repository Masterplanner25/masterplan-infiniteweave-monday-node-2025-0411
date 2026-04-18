from __future__ import annotations


class MasterplanEventTypes:
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
