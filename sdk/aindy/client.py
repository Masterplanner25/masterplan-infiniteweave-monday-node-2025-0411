"""
aindy.client — AINDYClient, the root HTTP client for the SDK.

All API sub-modules (memory, flow, events, execution, syscalls) are composed
onto this object so callers need only one import and one initialisation call.

Usage::

    from aindy import AINDYClient

    client = AINDYClient(
        base_url="http://localhost:8000",
        api_key="aindy_your_platform_key",
    )

    # All sub-APIs are available immediately
    result = client.memory.read("/memory/shawn/tasks/*")
    client.flow.run("analyze_tasks", {"nodes": result["data"]["nodes"]})
"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from aindy.exceptions import NetworkError, _raise_for_status

__all__ = ["AINDYClient"]

_DEFAULT_TIMEOUT = 30  # seconds


class AINDYClient:
    """Root SDK client. Compose all sub-APIs and handle HTTP transport.

    Args:
        base_url: Base URL of the A.I.N.D.Y. server, e.g. ``"http://localhost:8000"``.
        api_key:  Platform API key (``aindy_...``) **or** a JWT bearer token.
                  Platform keys are preferred for SDK use — create one with
                  ``POST /platform/keys``.
        timeout:  Per-request timeout in seconds (default 30).

    Sub-APIs (available after construction):
        - ``client.syscalls``  — raw syscall dispatch
        - ``client.memory``    — memory.read / memory.write / memory.search
        - ``client.flow``      — flow.run
        - ``client.events``    — event.emit
        - ``client.execution`` — execution.get
        - ``client.nodus``     — run_script / upload_script
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

        # Compose sub-APIs lazily to keep this constructor fast and testable.
        from aindy.syscalls import Syscalls
        from aindy.memory import MemoryAPI
        from aindy.flow import FlowAPI
        from aindy.events import EventAPI
        from aindy.execution import ExecutionAPI
        from aindy.nodus import NodusAPI

        self.syscalls = Syscalls(self)
        self.memory = MemoryAPI(self.syscalls)
        self.flow = FlowAPI(self.syscalls)
        self.events = EventAPI(self.syscalls)
        self.execution = ExecutionAPI(self.syscalls)
        self.nodus = NodusAPI(self)

    # ── HTTP transport ────────────────────────────────────────────────────────

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated HTTP request and return the parsed JSON body.

        Args:
            method:  HTTP method: ``"GET"``, ``"POST"``, ``"DELETE"``.
            path:    Path relative to ``base_url``, e.g. ``"/platform/syscall"``.
            payload: JSON-serialisable request body (for POST/PUT).
            params:  Query string parameters.

        Returns:
            Parsed JSON response body as a dict.

        Raises:
            AuthenticationError:  401 — invalid or missing API key.
            PermissionDeniedError: 403 — insufficient capability scope.
            NotFoundError:        404 — resource not found.
            ValidationError:      422 — malformed request payload.
            ResourceLimitError:   429 — quota exceeded.
            ServerError:          5xx — unexpected server error.
            NetworkError:         Connection refused, timeout, or DNS failure.
        """
        url = self._build_url(path, params)
        headers = self._auth_headers()

        body_bytes: bytes | None = None
        if payload is not None:
            body_bytes = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = Request(url, data=body_bytes, headers=headers, method=method.upper())

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            try:
                body = json.loads(exc.read())
            except Exception:
                body = {"error": str(exc)}
            _raise_for_status(exc.code, body, url)
        except URLError as exc:
            raise NetworkError(
                f"Could not reach {self.base_url}: {exc.reason}",
                cause=exc,
            ) from exc

    # ── Convenience wrappers ─────────────────────────────────────────────────

    def get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        """GET request."""
        return self.request("GET", path, params=params)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST request."""
        return self.request("POST", path, payload=payload)

    def delete(self, path: str) -> dict[str, Any]:
        """DELETE request."""
        return self.request("DELETE", path)

    # ── Private ──────────────────────────────────────────────────────────────

    def _build_url(self, path: str, params: dict[str, str] | None) -> str:
        url = self.base_url + path
        if params:
            from urllib.parse import urlencode
            url += "?" + urlencode({k: v for k, v in params.items() if v is not None})
        return url

    def _auth_headers(self) -> dict[str, str]:
        # Support both Platform API keys (aindy_...) and JWT bearer tokens.
        if self.api_key.startswith("aindy_"):
            return {"X-Platform-Key": self.api_key}
        return {"Authorization": f"Bearer {self.api_key}"}
