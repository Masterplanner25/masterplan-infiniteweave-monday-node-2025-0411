"""
Public surface for the search domain.
Consumers: freelance
"""

from __future__ import annotations

from typing import Any

from apps.search.models import LeadGenResult, ResearchResult, SearchHistory

PUBLIC_API_VERSION = "1.0"


def extract_flow_error(result: dict) -> str:
    from apps.search.services.public_surface_service import extract_flow_error as _extract_flow_error

    return str(_extract_flow_error(result) or "")


def is_circuit_open_detail(detail: Any) -> bool:
    from apps.search.services.public_surface_service import (
        is_circuit_open_detail as _is_circuit_open_detail,
    )

    return bool(_is_circuit_open_detail(detail))


def build_ai_provider_unavailable_payload(detail: Any) -> dict[str, Any]:
    from apps.search.services.public_surface_service import (
        build_ai_provider_unavailable_payload as _build_ai_provider_unavailable_payload,
    )

    return dict(_build_ai_provider_unavailable_payload(detail) or {})

__all__ = [
    "LeadGenResult",
    "ResearchResult",
    "SearchHistory",
    "extract_flow_error",
    "is_circuit_open_detail",
    "build_ai_provider_unavailable_payload",
]
