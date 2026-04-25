from __future__ import annotations


def test_platform_adapters_importable():
    """Response adapters must be importable from the platform layer."""
    from AINDY.platform_layer.response_adapters import (
        legacy_envelope_adapter,
        memory_completion_adapter,
        memory_execute_adapter,
        raw_canonical_adapter,
        raw_json_adapter,
    )

    assert callable(raw_json_adapter)
    assert callable(legacy_envelope_adapter)
    assert callable(raw_canonical_adapter)
    assert callable(memory_execute_adapter)
    assert callable(memory_completion_adapter)


def test_shim_still_works():
    """Backward-compat shim must still export all adapter names."""
    import apps._adapters as shim

    assert hasattr(shim, "raw_json_adapter")
    assert hasattr(shim, "legacy_envelope_adapter")
    assert hasattr(shim, "raw_canonical_adapter")
    assert hasattr(shim, "memory_execute_adapter")
    assert hasattr(shim, "memory_completion_adapter")


def test_adapter_returns_json_response():
    """raw_json_adapter must return a JSONResponse."""
    from fastapi.responses import JSONResponse

    from AINDY.platform_layer.response_adapters import raw_json_adapter

    result = raw_json_adapter(
        route_name="test",
        canonical={"data": {"key": "value"}, "status": "success", "trace_id": "abc"},
        status_code=200,
        trace_headers={},
    )
    assert isinstance(result, JSONResponse)
