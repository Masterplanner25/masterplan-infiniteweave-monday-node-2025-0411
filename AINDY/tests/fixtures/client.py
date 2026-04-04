from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient


def _patch_session_aliases(monkeypatch, session_factory, engine):
    import db.database as db_database

    monkeypatch.setattr(db_database, "SessionLocal", session_factory, raising=False)
    monkeypatch.setattr(db_database, "engine", engine, raising=False)

    for module_name, module in list(sys.modules.items()):
        if not module_name:
            continue
        if not (
            module_name == "main"
            or module_name.startswith("routes.")
            or module_name.startswith("services.")
            or module_name.startswith("platform_layer.")
            or module_name.startswith("runtime.")
            or module_name.startswith("agents.")
            or module_name.startswith("memory.")
            or module_name.startswith("domain.")
            or module_name.startswith("core.")
            or module_name == "worker"
        ):
            continue
        if hasattr(module, "SessionLocal"):
            monkeypatch.setattr(module, "SessionLocal", session_factory, raising=False)
        if hasattr(module, "engine"):
            monkeypatch.setattr(module, "engine", engine, raising=False)


@pytest.fixture
def app(db_session_factory, testing_session_factory, test_engine, monkeypatch):
    from db.database import get_db
    from main import app as fastapi_app

    _patch_session_aliases(monkeypatch, testing_session_factory, test_engine)

    def _get_test_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = _get_test_db
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
