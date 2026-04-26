"""
Public interface for apps/analytics.

External apps must import from this module, never from
apps.analytics.services.* directly. This file is the contract boundary.
"""

from apps.analytics.services.calculations.calculation_services import (
    calculate_twr,
    save_calculation,
)
from apps.analytics.services.orchestration.infinity_loop import get_latest_adjustment
from apps.analytics.services.orchestration.infinity_orchestrator import (
    execute as run_infinity_orchestrator,
)
from apps.analytics.services.scoring.infinity_service import get_user_kpi_snapshot

__all__ = [
    "calculate_twr",
    "save_calculation",
    "get_user_kpi_snapshot",
    "run_infinity_orchestrator",
    "get_latest_adjustment",
]
