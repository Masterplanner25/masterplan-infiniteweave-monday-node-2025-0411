from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from AINDY.kernel.resume_spec import (
    RESUME_HANDLER_EU,
    ResumeSpec,
    build_callback_from_spec,
    spec_from_json,
    spec_to_json,
)


def test_spec_round_trips_through_json():
    spec = ResumeSpec(
        handler=RESUME_HANDLER_EU,
        eu_id="eu-123",
        tenant_id="tenant-1",
        run_id="run-123",
        eu_type="flow",
    )

    round_tripped = spec_from_json(spec_to_json(spec))

    assert round_tripped == spec


def test_build_callback_from_spec_calls_resume():
    spec = ResumeSpec(
        handler=RESUME_HANDLER_EU,
        eu_id="eu-456",
        tenant_id="tenant-2",
        run_id="run-456",
        eu_type="flow",
    )
    mock_session = MagicMock()
    mock_session.__enter__.return_value = mock_session
    mock_session.__exit__.return_value = False
    service_instance = MagicMock()

    with patch("AINDY.db.SessionLocal", return_value=mock_session), patch(
        "AINDY.core.execution_unit_service.ExecutionUnitService",
        return_value=service_instance,
    ):
        callback = build_callback_from_spec(spec)
        callback()

    service_instance.resume_execution_unit.assert_called_once_with("eu-456")


def test_build_callback_raises_for_unknown_handler():
    spec = ResumeSpec(
        handler="unknown.handler",
        eu_id="eu-789",
        tenant_id="tenant-3",
        run_id="run-789",
        eu_type=None,
    )

    with pytest.raises(ValueError, match="Unknown resume handler"):
        build_callback_from_spec(spec)
