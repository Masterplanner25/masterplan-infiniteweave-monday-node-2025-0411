from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pymongo.errors import PyMongoError


def test_optional_mongo_degrades_gracefully_when_url_missing(monkeypatch):
    from AINDY.db import mongo_setup

    monkeypatch.setattr(mongo_setup, "_client", None)
    monkeypatch.setattr(mongo_setup.settings, "SKIP_MONGO_PING", False)
    monkeypatch.setattr(mongo_setup.settings, "MONGO_URL", "")

    assert mongo_setup.ensure_mongo_ready(required=False) is None


def test_required_mongo_fails_fast_when_url_missing(monkeypatch):
    from AINDY.db import mongo_setup

    monkeypatch.setattr(mongo_setup, "_client", None)
    monkeypatch.setattr(mongo_setup.settings, "SKIP_MONGO_PING", False)
    monkeypatch.setattr(mongo_setup.settings, "MONGO_URL", "")

    with pytest.raises(RuntimeError, match="MONGO_URL"):
        mongo_setup.ensure_mongo_ready(required=True)


def test_required_mongo_fails_fast_when_ping_fails(monkeypatch):
    from AINDY.db import mongo_setup

    mongo_ctor = MagicMock()
    mongo_client = MagicMock()
    mongo_client.admin.command.side_effect = PyMongoError("ping failed")
    mongo_ctor.return_value = mongo_client

    monkeypatch.setattr(mongo_setup, "_client", None)
    monkeypatch.setattr(mongo_setup.settings, "SKIP_MONGO_PING", False)
    monkeypatch.setattr(mongo_setup.settings, "MONGO_URL", "mongodb://localhost:27017")
    monkeypatch.setattr(mongo_setup, "MongoClient", mongo_ctor)

    with pytest.raises(RuntimeError, match="Mongo connection failed"):
        mongo_setup.ensure_mongo_ready(required=True)


def test_close_mongo_client_is_idempotent(monkeypatch):
    from AINDY.db import mongo_setup

    mongo_ctor = MagicMock()
    mongo_client = MagicMock()
    mongo_client.admin.command.return_value = {"ok": 1}
    mongo_ctor.return_value = mongo_client

    monkeypatch.setattr(mongo_setup, "_client", None)
    monkeypatch.setattr(mongo_setup.settings, "SKIP_MONGO_PING", False)
    monkeypatch.setattr(mongo_setup.settings, "MONGO_URL", "mongodb://localhost:27017")
    monkeypatch.setattr(mongo_setup, "MongoClient", mongo_ctor)

    assert mongo_setup.ensure_mongo_ready(required=False) is mongo_client

    mongo_setup.close_mongo_client()
    mongo_client.close.assert_called_once()
    assert mongo_setup._client is None

    mongo_setup.close_mongo_client()
    mongo_client.close.assert_called_once()
    assert mongo_setup._client is None
