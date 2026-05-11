"""
aindy.exceptions — structured exceptions for the A.I.N.D.Y. SDK.

Every HTTP error from the server is mapped to a typed exception so callers
can write clean, specific error handling instead of inspecting status codes.
"""
from __future__ import annotations


class AINDYError(Exception):
    """Base class for all SDK errors.

    Attributes:
        message:     Human-readable error description.
        status_code: HTTP status code from the server (None for network errors).
        response:    Raw server response dict (None for network errors).
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response or {}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status={self.status_code!r}, message={self.message!r})"


class AuthenticationError(AINDYError):
    """Raised when the API key is missing, invalid, or expired (HTTP 401)."""


class PermissionDeniedError(AINDYError):
    """Raised when the caller lacks a required capability (HTTP 403).

    Typical cause: the Platform API key's scope does not include the
    capability required by the target syscall.
    """


class NotFoundError(AINDYError):
    """Raised when the requested resource does not exist (HTTP 404)."""


class ValidationError(AINDYError):
    """Raised when the server rejects the request shape (HTTP 422).

    Typical cause: missing required field, wrong type, or schema violation
    in the syscall input payload.
    """


class ResourceLimitError(AINDYError):
    """Raised when a resource quota is exceeded (HTTP 429).

    Typical cause: syscall_count or cpu_time_ms exceeded for the execution unit.
    """


class ServerError(AINDYError):
    """Raised on unexpected server errors (HTTP 5xx)."""


class NetworkError(AINDYError):
    """Raised when the request could not reach the server at all.

    Wraps connection-refused, timeout, and DNS-failure scenarios.
    """

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


# ── HTTP status → exception mapping ──────────────────────────────────────────

def _raise_for_status(status_code: int, body: dict, url: str) -> None:
    """Raise the appropriate AINDYError for a non-2xx HTTP response.

    Args:
        status_code: HTTP status code.
        body:        Parsed JSON response body.
        url:         Request URL (for context in error messages).
    """
    # Extract the most useful error string from the response body.
    detail = body.get("detail") or body.get("error") or body.get("message") or str(body)
    if isinstance(detail, dict):
        detail = detail.get("error") or detail.get("message") or str(detail)
    msg = f"[HTTP {status_code}] {detail} — {url}"

    if status_code == 401:
        raise AuthenticationError(msg, status_code=status_code, response=body)
    if status_code == 403:
        raise PermissionDeniedError(msg, status_code=status_code, response=body)
    if status_code == 404:
        raise NotFoundError(msg, status_code=status_code, response=body)
    if status_code == 422:
        raise ValidationError(msg, status_code=status_code, response=body)
    if status_code == 429:
        raise ResourceLimitError(msg, status_code=status_code, response=body)
    if status_code >= 500:
        raise ServerError(msg, status_code=status_code, response=body)
    raise AINDYError(msg, status_code=status_code, response=body)
