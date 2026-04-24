from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def test_execute_stripe_action_raises_on_missing_key():
    from apps.automation.services.automation_execution_service import _execute_stripe_action

    with pytest.raises(ValueError) as exc_info:
        _execute_stripe_action({"automation_config": {}}, {})

    assert "stripe_secret_key not configured" in str(exc_info.value)


def test_execute_stripe_action_raises_on_zero_amount():
    from apps.automation.services.automation_execution_service import _execute_stripe_action

    with pytest.raises(ValueError) as exc_info:
        _execute_stripe_action({}, {"stripe_secret_key": "sk_test_fake", "amount": 0})

    assert "amount must be > 0" in str(exc_info.value)


def test_execute_stripe_action_calls_stripe_api():
    from apps.automation.services import automation_execution_service as svc

    call_log: list[str] = []

    def fake_urlopen(req, timeout=None):
        path = req.full_url
        call_log.append(path)
        resp = MagicMock()
        if "/v1/products" in path:
            resp.read.return_value = json.dumps({"id": "prod_test"}).encode()
        elif "/v1/prices" in path:
            resp.read.return_value = json.dumps({"id": "price_test"}).encode()
        elif "/v1/payment_links" in path:
            resp.read.return_value = json.dumps(
                {
                    "id": "plink_test",
                    "url": "https://buy.stripe.com/test",
                }
            ).encode()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    with patch.object(svc.urllib_request, "urlopen", side_effect=fake_urlopen):
        with patch.object(svc.urllib_request, "Request", wraps=svc.urllib_request.Request):
            result = svc._execute_stripe_action(
                {"task_name": "test_service"},
                {"stripe_secret_key": "sk_test_fake", "amount": 5000, "currency": "usd"},
            )

    assert result["automation_type"] == "stripe"
    assert result["status"] == "completed"
    assert result["payment_link_url"] == "https://buy.stripe.com/test"
    assert result["amount_cents"] == 5000
    assert any("/v1/products" in c for c in call_log)
    assert any("/v1/prices" in c for c in call_log)
    assert any("/v1/payment_links" in c for c in call_log)


def test_delivery_type_payment_accepted_at_order_creation():
    from apps.freelance.services.freelance_service import _SUPPORTED_DELIVERY_TYPES

    assert "payment" in _SUPPORTED_DELIVERY_TYPES
