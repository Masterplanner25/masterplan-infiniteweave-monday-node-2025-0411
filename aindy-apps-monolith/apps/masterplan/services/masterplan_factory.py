import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID
from AINDY.core.execution_signal_helper import queue_memory_capture
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from apps.masterplan.models import GenesisSessionDB, MasterPlan
from apps.masterplan.services.posture import determine_posture  # adjust import if needed
from AINDY.core.observability_events import emit_observability_event


logger = logging.getLogger(__name__)


def create_masterplan_from_genesis(session_id: int, draft: dict, db: Session, user_id: str = None):

    session = (
        db.query(GenesisSessionDB)
        .filter(GenesisSessionDB.id == session_id)
        .with_for_update()
        .first()
    )

    if not session:
        raise Exception("Genesis session not found")

    if session.status == "locked":
        raise Exception("Session already locked")

    if not session.synthesis_ready:
        raise ValueError("Session is not synthesis-ready — run /genesis/synthesize first")

    # Load draft from session if available; fall back to caller-supplied draft
    draft_to_use = session.draft_json or draft

    # Version label scoped per-user to avoid global numbering pollution
    if user_id:
        user_uuid = UUID(str(user_id))
        user_plans = db.query(MasterPlan).filter(MasterPlan.user_id == user_uuid).order_by(MasterPlan.id).all()
    else:
        user_plans = db.query(MasterPlan).order_by(MasterPlan.id).all()

    if not user_plans:
        version_label = "V1"
        is_origin = True
        parent_id = None
    else:
        version_label = f"V{len(user_plans) + 1}"
        is_origin = False
        parent_id = user_plans[-1].id

    # Timeline
    horizon = draft_to_use.get("time_horizon_years", 5)
    # MasterPlan.start_date/target_date are legacy naive DateTime columns; SQLAlchemy may strip tzinfo here.
    start_date = datetime.now(timezone.utc)
    target_date = start_date + timedelta(days=int(horizon * 365))

    # Posture
    posture = determine_posture(draft_to_use)

    try:
        masterplan = MasterPlan(
            version_label=version_label,
            is_origin=is_origin,
            is_active=False,
            user_id=UUID(str(user_id)) if user_id else None,
            status="locked",
            structure_json=draft_to_use,
            posture=posture,
            locked_at=start_date,
            start_date=start_date,
            duration_years=horizon,
            target_date=target_date,
            parent_id=parent_id,
            linked_genesis_session_id=session.id
        )

        db.add(masterplan)

        # Freeze Genesis
        session.status = "locked"
        session.locked_at = start_date

        db.commit()
        db.refresh(masterplan)
    except IntegrityError:
        db.rollback()
        raise ValueError(
            f"A masterplan already exists for genesis session {session_id}"
        )
    except Exception:
        db.rollback()
        raise

    # Capture lock event to memory (fire-and-forget)
    if user_id:
        try:
            vision = ""
            if isinstance(draft_to_use, dict):
                vision = str(draft_to_use.get("vision_statement") or draft_to_use.get("vision_summary") or "")
            queue_memory_capture(
                db=db,
                user_id=user_id,
                agent_namespace="genesis",
                event_type="masterplan_locked",
                content=(
                    f"Masterplan locked: {masterplan.version_label} "
                    f"(posture: {masterplan.posture}, session: {session_id}). "
                    f"Vision: {vision[:200]}"
                ),
                source="genesis_lock",
                tags=["genesis", "masterplan", "decision"],
                node_type="decision",
                force=True,
            )
        except Exception:
            emit_observability_event(
                logger,
                event="masterplan_lock_memory_capture_failed",
                session_id=session_id,
                user_id=user_id,
                masterplan_id=getattr(masterplan, "id", None),
            )
            raise

    # Observe for identity inference (non-blocking)
    if user_id:
        try:
            from apps.identity.public import observe_identity_event

            observe_identity_event(
                user_id=user_id,
                db=db,
                event_type="masterplan_locked",
                context={"posture": masterplan.posture},
            )
        except Exception:
            emit_observability_event(
                logger,
                event="masterplan_identity_observation_failed",
                session_id=session_id,
                user_id=user_id,
                masterplan_id=getattr(masterplan, "id", None),
            )
            raise

    return masterplan


