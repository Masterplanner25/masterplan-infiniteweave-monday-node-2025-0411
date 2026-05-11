from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


@dataclass
class DomainHealthStatus:
    domain: str
    healthy: bool
    last_checked: datetime
    error: str | None = None


class DomainHealthRegistry:
    """Registry for per-domain health check functions."""

    def __init__(self) -> None:
        self._checks: dict[str, Callable[[], bool]] = {}

    def register(self, domain: str, check_fn: Callable[[], bool]) -> None:
        self._checks[str(domain).strip()] = check_fn

    def check_one(self, domain: str) -> DomainHealthStatus:
        normalized = str(domain).strip()
        now = datetime.now(timezone.utc)
        check_fn = self._checks.get(normalized)
        if check_fn is None:
            return DomainHealthStatus(
                domain=normalized,
                healthy=False,
                last_checked=now,
                error="domain check not registered",
            )
        try:
            healthy = bool(check_fn())
            return DomainHealthStatus(
                domain=normalized,
                healthy=healthy,
                last_checked=now,
                error=None if healthy else "health check returned false",
            )
        except Exception as exc:
            return DomainHealthStatus(
                domain=normalized,
                healthy=False,
                last_checked=now,
                error=str(exc),
            )

    def check_all(self) -> dict[str, DomainHealthStatus]:
        return {
            domain: self.check_one(domain)
            for domain in sorted(self._checks)
        }


domain_health_registry = DomainHealthRegistry()
