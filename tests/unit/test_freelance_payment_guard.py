from __future__ import annotations

import pytest


def test_execute_stripe_action_raises_not_implemented():
    from apps.automation.services.automation_execution_service import _execute_stripe_action

    with pytest.raises(NotImplementedError) as exc_info:
        _execute_stripe_action({}, {})

    assert "Stripe payment delivery is not yet implemented" in str(exc_info.value)
