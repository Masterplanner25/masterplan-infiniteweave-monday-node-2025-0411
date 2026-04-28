from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient

from AINDY.core.execution_guard import require_execution_context
from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.middleware import enforce_execution_contract


def _build_guarded_app(use_pipeline: bool) -> FastAPI:
    app = FastAPI()
    router = APIRouter(dependencies=[Depends(require_execution_context)])

    @router.get("/business")
    def business_route(request: Request):
        if not use_pipeline:
            return {"status": "raw"}
        return execute_with_pipeline_sync(
            request=request,
            route_name="test.business",
            handler=lambda ctx: {"status": "ok"},
        )

    app.include_router(router)
    app.middleware("http")(enforce_execution_contract)
    return app


def test_execution_guard_raises_for_non_pipeline_route():
    client = TestClient(_build_guarded_app(use_pipeline=False))
    try:
        client.get("/business")
        assert False, "Expected execution contract violation"
    except RuntimeError as exc:
        assert "ExecutionContract violation" in str(exc)


def test_execution_guard_allows_pipeline_route():
    client = TestClient(_build_guarded_app(use_pipeline=True))
    response = client.get("/business")

    assert response.status_code == 200
    body = response.json()
    assert str(body["status"]).lower() == "success"
