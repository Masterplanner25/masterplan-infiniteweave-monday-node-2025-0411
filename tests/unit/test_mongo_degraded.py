from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

from AINDY.db.mongo_setup import MongoUnavailableError
from AINDY.exception_handlers import mongo_unavailable_exception_handler


def test_require_mongo_client_raises_when_client_missing():
    with patch("AINDY.db.mongo_setup.get_mongo_client", return_value=None):
        from AINDY.db.mongo_setup import require_mongo_client

        with pytest.raises(MongoUnavailableError) as exc_info:
            require_mongo_client("automation_execution_service")

    assert exc_info.value.detail == "MongoDB is not available: automation_execution_service"


def test_require_mongo_client_returns_client_when_available():
    client = MagicMock()
    with patch("AINDY.db.mongo_setup.get_mongo_client", return_value=client):
        from AINDY.db.mongo_setup import require_mongo_client

        result = require_mongo_client("task_service")

    assert result is client


@pytest.mark.asyncio
async def test_mongo_unavailable_exception_handler_returns_structured_503():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
            "scheme": "http",
        }
    )

    response = await mongo_unavailable_exception_handler(
        request,
        MongoUnavailableError("automation_execution_service"),
    )

    assert response.status_code == 503
    assert response.body
    assert b'"error":"mongo_unavailable"' in response.body
    assert b"MongoDB is not available: automation_execution_service" in response.body
