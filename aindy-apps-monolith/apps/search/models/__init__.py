"""Search app models."""

from apps.search.models.leadgen_model import LeadGenResult
from apps.search.models.research_results import ResearchResult
from apps.search.models.search_history import SearchHistory

__all__ = [
    "LeadGenResult",
    "ResearchResult",
    "SearchHistory",
]


def register_models() -> None:
    return None
