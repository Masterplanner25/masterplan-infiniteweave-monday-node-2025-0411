from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import MasterPlan
from db.models.metrics_models import CanonicalMetricDB
from schemas.analytics import LinkedInRawInput
from services.analytics.linkedin_adapter import linkedin_adapter
from sqlalchemy import func

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/linkedin/manual")
def ingest_linkedin_manual(data: LinkedInRawInput, db: Session = Depends(get_db)):

    plan = db.query(MasterPlan).filter_by(id=data.masterplan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="MasterPlan not found")

    canonical = linkedin_adapter(data)

    existing = db.query(CanonicalMetricDB).filter_by(
        masterplan_id=canonical["masterplan_id"],
        platform=canonical["platform"],
        scope_type=canonical["scope_type"],
        scope_id=canonical["scope_id"],
        period_type=canonical["period_type"],
        period_start=canonical["period_start"]
    ).first()

    if existing:
        for key, value in canonical.items():
            setattr(existing, key, value)
        db_record = existing
    else:
        db_record = CanonicalMetricDB(**canonical)
        db.add(db_record)

    db.commit()
    db.refresh(db_record)

    return db_record

@router.get("/masterplan/{masterplan_id}")
def get_masterplan_analytics(
    masterplan_id: int,
    period_type: str | None = None,
    platform: str | None = None,
    scope_type: str | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(CanonicalMetricDB).filter(
        CanonicalMetricDB.masterplan_id == masterplan_id
    )

    if period_type:
        query = query.filter(CanonicalMetricDB.period_type == period_type)

    if platform:
        query = query.filter(CanonicalMetricDB.platform == platform)

    if scope_type:
        query = query.filter(CanonicalMetricDB.scope_type == scope_type)

    results = query.order_by(CanonicalMetricDB.period_start.desc()).all()

    return results

@router.get("/masterplan/{masterplan_id}/summary")
def get_masterplan_summary(
    masterplan_id: int,
    group_by: str | None = None,
    db: Session = Depends(get_db)
):

    query = db.query(CanonicalMetricDB).filter(
        CanonicalMetricDB.masterplan_id == masterplan_id
    )

    records = query.order_by(
        CanonicalMetricDB.period_start.asc()
    ).all()

    if not records:
        return {"message": "No telemetry records found."}

    # ---- GROUPED SUMMARY ----
    if group_by == "period":

        grouped = {}

        for r in records:
            key = (r.period_type, r.period_start)

            if key not in grouped:
                grouped[key] = {
                    "period_type": r.period_type,
                    "period_start": r.period_start,
                    "period_end": r.period_end,
                    "totals": {
                        "passive_visibility": 0,
                        "active_discovery": 0,
                        "unique_reach": 0,
                        "interaction_volume": 0,
                        "deep_attention_units": 0,
                        "intent_signals": 0,
                        "conversion_events": 0,
                        "growth_velocity": 0,
                    }
                }

            g = grouped[key]["totals"]

            g["passive_visibility"] += r.passive_visibility or 0
            g["active_discovery"] += r.active_discovery or 0
            g["unique_reach"] += r.unique_reach or 0
            g["interaction_volume"] += r.interaction_volume or 0
            g["deep_attention_units"] += r.deep_attention_units or 0
            g["intent_signals"] += r.intent_signals or 0
            g["conversion_events"] += r.conversion_events or 0
            g["growth_velocity"] += r.growth_velocity or 0

        # ---- Recalculate weighted rates per period ----
        output = []

        for (ptype, pstart), data in grouped.items():

            totals = data["totals"]

            visibility = totals["passive_visibility"] or 1
            reach = totals["unique_reach"] or 1
            intent = totals["intent_signals"] or 1

            rates = {
                "interaction_rate": totals["interaction_volume"] / visibility,
                "attention_rate": totals["deep_attention_units"] / visibility,
                "intent_rate": totals["intent_signals"] / reach,
                "conversion_rate": totals["conversion_events"] / intent,
                "discovery_ratio": totals["active_discovery"] / visibility,
                "growth_rate": totals["growth_velocity"] / reach,
            }

            output.append({
                "period_type": ptype,
                "period_start": data["period_start"],
                "period_end": data["period_end"],
                "totals": totals,
                "rates": rates
            })

        return {
            "masterplan_id": masterplan_id,
            "grouped": output
        }

    # ---- GLOBAL SUMMARY (existing behavior) ----
    totals = {
        "passive_visibility": sum(r.passive_visibility or 0 for r in records),
        "active_discovery": sum(r.active_discovery or 0 for r in records),
        "unique_reach": sum(r.unique_reach or 0 for r in records),
        "interaction_volume": sum(r.interaction_volume or 0 for r in records),
        "deep_attention_units": sum(r.deep_attention_units or 0 for r in records),
        "intent_signals": sum(r.intent_signals or 0 for r in records),
        "conversion_events": sum(r.conversion_events or 0 for r in records),
        "growth_velocity": sum(r.growth_velocity or 0 for r in records),
    }

    visibility = totals["passive_visibility"] or 1
    reach = totals["unique_reach"] or 1
    intent = totals["intent_signals"] or 1

    rates = {
        "interaction_rate": totals["interaction_volume"] / visibility,
        "attention_rate": totals["deep_attention_units"] / visibility,
        "intent_rate": totals["intent_signals"] / reach,
        "conversion_rate": totals["conversion_events"] / intent,
        "discovery_ratio": totals["active_discovery"] / visibility,
        "growth_rate": totals["growth_velocity"] / reach,
    }

    return {
        "masterplan_id": masterplan_id,
        "record_count": len(records),
        "totals": totals,
        "rates": rates
    }


