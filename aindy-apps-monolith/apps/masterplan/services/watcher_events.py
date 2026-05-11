from __future__ import annotations

from typing import Any

from apps.masterplan.services.eta_service import recalculate_all_etas


def handle_watcher_session_ended(event: dict[str, Any]) -> int:
    """React to watcher session completion by recalculating MasterPlan ETAs."""
    db = event.get("db")
    return recalculate_all_etas(db=db)


def register_masterplan_event_handlers() -> None:
    from AINDY.platform_layer.event_service import register_event_handler

    register_event_handler("watcher.session_ended", handle_watcher_session_ended)
