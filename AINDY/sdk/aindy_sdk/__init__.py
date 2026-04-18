"""
aindy — A.I.N.D.Y. Developer SDK (v1)

The SDK exposes the full A.I.N.D.Y. platform surface — memory, flows, events,
syscalls, and Nodus script execution — through a single client object.

Quick start::

    from AINDY.sdk.aindy_sdk import AINDYClient

    client = AINDYClient(
        base_url="http://localhost:8000",
        api_key="aindy_your_platform_key",
    )

    # Read memory nodes
    result = client.memory.read("/memory/shawn/entities/**")
    nodes = result["data"]["nodes"]

    # Run a flow
    analysis = client.flow.run("analyze_entities", {"nodes": nodes})

    # Write back an insight
    client.memory.write(
        "/memory/shawn/insights/outcome",
        analysis["data"]["summary"],
        tags=["auto-generated", "sprint"],
    )

    # Emit an event
    client.events.emit("sprint.analyzed", {"node_count": len(nodes)})

    # Run a Nodus script inline
    result = client.nodus.run_script(
        'set_state("hello", "world")',
        input={},
    )
"""
from AINDY.sdk.aindy_sdk.client import AINDYClient
from AINDY.sdk.aindy_sdk.exceptions import (
    AINDYError,
    AuthenticationError,
    NetworkError,
    NotFoundError,
    PermissionDeniedError,
    ResourceLimitError,
    ServerError,
    ValidationError,
)

__all__ = [
    "AINDYClient",
    # Exceptions
    "AINDYError",
    "AuthenticationError",
    "NetworkError",
    "NotFoundError",
    "PermissionDeniedError",
    "ResourceLimitError",
    "ServerError",
    "ValidationError",
]

__version__ = "1.0.0"
