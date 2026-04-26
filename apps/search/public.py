"""Public interface for the search app. Other apps must only import from this file."""

from apps.search.models import LeadGenResult, ResearchResult, SearchHistory

# TODO: these route-helper exports should be refactored before stabilizing the interface.
from apps.search.routes._route_helpers import (
    _ai_provider_unavailable_response,
    _extract_flow_error,
    _is_circuit_open_detail,
)
from apps.search.services.leadgen_service import create_lead_results, run_ai_search

__all__ = [
    "LeadGenResult",
    "ResearchResult",
    "SearchHistory",
    "_ai_provider_unavailable_response",
    "_extract_flow_error",
    "_is_circuit_open_detail",
    "create_lead_results",
    "run_ai_search",
]
