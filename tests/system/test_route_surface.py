from __future__ import annotations

import os

from fastapi.routing import APIRoute


def _build_app():
    os.environ["TEST_MODE"] = "true"
    os.environ["TESTING"] = "true"

    from AINDY.main import create_app

    return create_app()


def _route_tuples():
    app = _build_app()
    api_routes = [route for route in app.routes if isinstance(route, APIRoute)]
    methods = {"GET", "POST", "PUT", "DELETE", "PATCH"}
    return {
        (method, route.path)
        for route in api_routes
        for method in route.methods
        if method in methods
    }


def test_route_count_has_not_regressed():
    routes = _route_tuples()
    count = len(routes)
    baseline = 289

    assert count >= baseline, f"Route count regressed: expected >= {baseline}, got {count}"


def test_critical_routes_exist():
    routes = _route_tuples()

    for route in {
        ("POST", "/auth/login"),
        ("POST", "/auth/register"),
        ("GET", "/health"),
        ("GET", "/ready"),
    }:
        assert route in routes
