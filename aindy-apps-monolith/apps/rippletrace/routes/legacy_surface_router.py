"""
LEGACY SURFACE — Rippletrace compatibility routes.

These routes are maintained for existing callers. No new routes should
be added here. Migrate callers to /apps/rippletrace/*.

To check what callers exist: grep the client codebase and any external
integrations for the paths listed in docs/platform/interfaces/API_CONTRACTS.md
under "Legacy Compatibility Surface (Rippletrace)".

Removal plan: when no callers are verified against these paths, remove
this file and deregister from bootstrap.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from AINDY.core.execution_gate import to_envelope
from AINDY.core.execution_helper import execute_with_pipeline
from AINDY.db.database import get_db
from AINDY.platform_layer.rate_limiter import limiter
from AINDY.services.auth_service import verify_api_key

router = APIRouter(
    tags=["Legacy Compatibility"],
    dependencies=[Depends(verify_api_key)],
)

_LEGACY_API_KEY_USER_ID = "__api_key__"


def add_deprecation_headers(response: Response):
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = ""
    response.headers["Link"] = '</apps/rippletrace/>; rel="successor-version"'


def _with_execution_envelope(payload):
    envelope = to_envelope(
        eu_id=None,
        trace_id=None,
        status="SUCCESS",
        output=None,
        error=None,
        duration_ms=None,
        attempt_count=1,
    )
    if hasattr(payload, "status_code") and hasattr(payload, "body"):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        result = dict(data) if isinstance(data, dict) else dict(payload)
        result.setdefault("execution_envelope", envelope)
        return result
    return {"data": payload, "execution_envelope": envelope}


async def _run_legacy(request: Request, route_name: str, handler, *, input_payload=None):
    # Legacy surface is API-key-only. Existing callers do not authenticate as a user,
    # so we stamp a sentinel user_id for execution-pipeline observability.
    return await execute_with_pipeline(
        request=request,
        route_name=route_name,
        handler=handler,
        user_id=_LEGACY_API_KEY_USER_ID,
        input_payload=input_payload,
    )


def analyze_drop_point(drop_point_id: str, db: Session):
    from apps.rippletrace.services.threadweaver import analyze_drop_point as _impl

    return _impl(drop_point_id, db)


def get_dashboard_snapshot(db: Session):
    from apps.rippletrace.services.threadweaver import get_dashboard_snapshot as _impl

    return _impl(db)


def find_momentum_leaders(db: Session):
    from apps.rippletrace.services.delta_engine import find_momentum_leaders as _impl

    return _impl(db)


def scan_drop_point_predictions(db: Session, limit: int = 20):
    from apps.rippletrace.services.prediction_engine import scan_drop_point_predictions as _impl

    return _impl(db, limit=limit)


def recommendations_summary(db: Session, limit: int = 20):
    from apps.rippletrace.services.recommendation_engine import recommendations_summary as _impl

    return _impl(db, limit=limit)


def get_top_drop_points(db: Session):
    from apps.rippletrace.services.threadweaver import get_top_drop_points as _impl

    return _impl(db)


def compute_deltas(drop_point_id: str, db: Session):
    from apps.rippletrace.services.delta_engine import compute_deltas as _impl

    return _impl(drop_point_id, db)


def emerging_drops(db: Session):
    from apps.rippletrace.services.delta_engine import emerging_drops as _impl

    return _impl(db)


def predict_drop_point(drop_point_id: str, db: Session):
    from apps.rippletrace.services.prediction_engine import predict_drop_point as _impl

    return _impl(drop_point_id, db)


def prediction_summary(db: Session):
    from apps.rippletrace.services.prediction_engine import prediction_summary as _impl

    return _impl(db)


def recommend_for_drop_point(drop_point_id: str, db: Session):
    from apps.rippletrace.services.recommendation_engine import recommend_for_drop_point as _impl

    return _impl(drop_point_id, db)


def build_influence_graph(db: Session):
    from apps.rippletrace.services.influence_graph import build_influence_graph as _impl

    return _impl(db)


def influence_chain(drop_point_id: str, db: Session):
    from apps.rippletrace.services.influence_graph import influence_chain as _impl

    return _impl(drop_point_id, db)


def build_causal_graph(db: Session):
    from apps.rippletrace.services.causal_engine import build_causal_graph as _impl

    return _impl(db)


def get_causal_chain(drop_point_id: str, db: Session):
    from apps.rippletrace.services.causal_engine import get_causal_chain as _impl

    return _impl(drop_point_id, db)


def generate_narrative(drop_point_id: str, db: Session):
    from apps.rippletrace.services.narrative_engine import generate_narrative as _impl

    return _impl(drop_point_id, db)


def narrative_summary(db: Session):
    from apps.rippletrace.services.narrative_engine import narrative_summary as _impl

    return _impl(db)


def build_strategies(db: Session):
    from apps.rippletrace.services.strategy_engine import build_strategies as _impl

    return _impl(db)


def list_strategies(db: Session):
    from apps.rippletrace.services.strategy_engine import list_strategies as _impl

    return _impl(db)


def get_strategy(strategy_id: str, db: Session):
    from apps.rippletrace.services.strategy_engine import get_strategy as _impl

    return _impl(strategy_id, db)


def match_strategies(drop_point_id: str, db: Session):
    from apps.rippletrace.services.strategy_engine import match_strategies as _impl

    return _impl(drop_point_id, db)


def build_playbook(strategy_id: str, db: Session):
    from apps.rippletrace.services.playbook_engine import build_playbook as _impl

    return _impl(strategy_id, db)


def list_playbooks(db: Session):
    from apps.rippletrace.services.playbook_engine import list_playbooks as _impl

    return _impl(db)


def get_playbook(playbook_id: str, db: Session):
    from apps.rippletrace.services.playbook_engine import get_playbook as _impl

    return _impl(playbook_id, db)


def match_playbooks(drop_point_id: str, db: Session):
    from apps.rippletrace.services.playbook_engine import match_playbooks as _impl

    return _impl(drop_point_id, db)


def generate_content(playbook_id: str, db: Session):
    from apps.rippletrace.services.content_generator import generate_content as _impl

    return _impl(playbook_id, db)


def generate_content_for_drop(drop_point_id: str, db: Session):
    from apps.rippletrace.services.content_generator import generate_content_for_drop as _impl

    return _impl(drop_point_id, db)


def generate_variations(playbook_id: str, db: Session):
    from apps.rippletrace.services.content_generator import generate_variations as _impl

    return _impl(playbook_id, db)


def learning_stats(db: Session):
    from apps.rippletrace.services.learning_engine import learning_stats as _impl

    return _impl(db)


def evaluate_outcome(drop_point_id: str, db: Session):
    from apps.rippletrace.services.learning_engine import evaluate_outcome as _impl

    return _impl(drop_point_id, db)


def adjust_thresholds(db: Session):
    from apps.rippletrace.services.learning_engine import adjust_thresholds as _impl

    return _impl(db)


@router.get("/analyze_ripple/{drop_point_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def analyze_ripple(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def handler(ctx):
        metrics = analyze_drop_point(drop_point_id, db)
        if not metrics:
            raise HTTPException(status_code=404, detail="Drop point not found")
        return metrics

    return await _run_legacy(request, "rippletrace.legacy.analyze_ripple", handler)


@router.get("/dashboard", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def proofboard_dashboard(request: Request, db: Session = Depends(get_db)):
    def handler(ctx):
        snapshot = get_dashboard_snapshot(db)
        leaders = find_momentum_leaders(db)
        predictions = scan_drop_point_predictions(db, limit=20)

        snapshot.update(
            {
                "fastest_accelerating_drop": leaders.get("fastest_accelerating"),
                "biggest_spike_drop": leaders.get("biggest_spike"),
                "predicted_spike_candidates": [
                    p for p in predictions if p["prediction"] == "likely_to_spike"
                ],
                "declining_drops": [
                    p for p in predictions if p["prediction"] == "declining"
                ],
                "recommendations_summary": recommendations_summary(db, limit=10),
            }
        )
        return snapshot

    return await _run_legacy(request, "rippletrace.legacy.dashboard", handler)


async def _wrap_legacy(request: Request, route_name: str, fn):
    def handler(ctx):
        return fn()

    return await _run_legacy(request, route_name, handler)


@router.get("/top_drop_points", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def top_drop_points(request: Request, db: Session = Depends(get_db)):
    def fn():
        return {"top_drop_points": get_top_drop_points(db)}

    return await _wrap_legacy(request, "rippletrace.legacy.top_drop_points", fn)


@router.get("/ripple_deltas/{drop_point_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def ripple_deltas(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def fn():
        return compute_deltas(drop_point_id, db)

    return await _wrap_legacy(request, "rippletrace.legacy.ripple_deltas", fn)


@router.get("/emerging_drops", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def emerging_drops_view(request: Request, db: Session = Depends(get_db)):
    def fn():
        return {"emerging_drops": emerging_drops(db)}

    return await _wrap_legacy(request, "rippletrace.legacy.emerging_drops", fn)


@router.get("/predict/{drop_point_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def predict_drop_point_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def fn():
        return predict_drop_point(drop_point_id, db)

    return await _wrap_legacy(request, "rippletrace.legacy.predict", fn)


@router.get("/prediction_summary", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def prediction_summary_view(request: Request, db: Session = Depends(get_db)):
    def fn():
        return prediction_summary(db)

    return await _wrap_legacy(request, "rippletrace.legacy.prediction_summary", fn)


@router.get("/recommend/{drop_point_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def recommend_drop_point(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def fn():
        return recommend_for_drop_point(drop_point_id, db)

    return await _wrap_legacy(request, "rippletrace.legacy.recommend", fn)


@router.get("/recommendations_summary", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def recommendations_summary_view(request: Request, db: Session = Depends(get_db)):
    def fn():
        return recommendations_summary(db)

    return await _wrap_legacy(request, "rippletrace.legacy.recommendations_summary", fn)


# NOTE: This route has no equivalent in rippletrace_router.py and is called by
# client code. Do not deprecate until a migration path exists.
@router.get("/influence_graph")
@limiter.limit("60/minute")
async def influence_graph_view(request: Request, db: Session = Depends(get_db)):
    def fn():
        return build_influence_graph(db)

    return await _wrap_legacy(request, "rippletrace.legacy.influence_graph", fn)


@router.get("/influence_chain/{drop_point_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def influence_chain_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def fn():
        return influence_chain(drop_point_id, db)

    return await _wrap_legacy(request, "rippletrace.legacy.influence_chain", fn)


@router.get("/causal_graph", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def causal_graph_view(request: Request, db: Session = Depends(get_db)):
    def fn():
        return build_causal_graph(db)

    return await _wrap_legacy(request, "rippletrace.legacy.causal_graph", fn)


@router.get("/causal_chain/{drop_point_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def causal_chain_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def fn():
        return get_causal_chain(drop_point_id, db)

    return await _wrap_legacy(request, "rippletrace.legacy.causal_chain", fn)


@router.get("/narrative/{drop_point_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def narrative_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def fn():
        return generate_narrative(drop_point_id, db)

    return await _wrap_legacy(request, "rippletrace.legacy.narrative", fn)


@router.get("/narrative_summary", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def narrative_summary_view(request: Request, db: Session = Depends(get_db)):
    def fn():
        return {"stories": narrative_summary(db)}

    return await _wrap_legacy(request, "rippletrace.legacy.narrative_summary", fn)


@router.get("/strategies", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def strategies_view(request: Request, db: Session = Depends(get_db)):
    def fn():
        build_strategies(db)
        return {"strategies": list_strategies(db)}

    return await _wrap_legacy(request, "rippletrace.legacy.strategies", fn)


@router.get("/strategy/{strategy_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def strategy_view(request: Request, strategy_id: str, db: Session = Depends(get_db)):
    def fn():
        strategy = get_strategy(strategy_id, db)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return strategy

    return await _wrap_legacy(request, "rippletrace.legacy.strategy", fn)


@router.get("/strategy_match/{drop_point_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def strategy_match_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def fn():
        return {"matches": match_strategies(drop_point_id, db)}

    return await _wrap_legacy(request, "rippletrace.legacy.strategy_match", fn)


@router.post("/build_playbook/{strategy_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("30/minute")
async def build_playbook_view(request: Request, strategy_id: str, db: Session = Depends(get_db)):
    def fn():
        return build_playbook(strategy_id, db)

    return _with_execution_envelope(
        await _wrap_legacy(request, "rippletrace.legacy.build_playbook", fn)
    )


@router.get("/playbooks", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def playbooks_view(request: Request, db: Session = Depends(get_db)):
    def fn():
        return {"playbooks": list_playbooks(db)}

    return await _wrap_legacy(request, "rippletrace.legacy.playbooks", fn)


@router.get("/playbook/{playbook_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def playbook_view(request: Request, playbook_id: str, db: Session = Depends(get_db)):
    def fn():
        playbook = get_playbook(playbook_id, db)
        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")
        return playbook

    return await _wrap_legacy(request, "rippletrace.legacy.playbook", fn)


@router.get("/playbook_match/{drop_point_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def playbook_match_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def fn():
        return {"matches": match_playbooks(drop_point_id, db)}

    return await _wrap_legacy(request, "rippletrace.legacy.playbook_match", fn)


@router.get("/generate_content/{playbook_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def generate_content_view(request: Request, playbook_id: str, db: Session = Depends(get_db)):
    def fn():
        return generate_content(playbook_id, db)

    return await _wrap_legacy(request, "rippletrace.legacy.generate_content", fn)


@router.post("/generate_content_for_drop/{drop_point_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("30/minute")
async def generate_content_for_drop_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def fn():
        return generate_content_for_drop(drop_point_id, db)

    return _with_execution_envelope(
        await _wrap_legacy(request, "rippletrace.legacy.generate_content_for_drop", fn)
    )


@router.get("/generate_variations/{playbook_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def generate_variations_view(request: Request, playbook_id: str, db: Session = Depends(get_db)):
    def fn():
        return generate_variations(playbook_id, db)

    return await _wrap_legacy(request, "rippletrace.legacy.generate_variations", fn)


@router.get("/learning_stats", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("60/minute")
async def learning_stats_view(request: Request, db: Session = Depends(get_db)):
    def fn():
        return learning_stats(db)

    return await _wrap_legacy(request, "rippletrace.legacy.learning_stats", fn)


@router.post("/evaluate/{drop_point_id}", dependencies=[Depends(add_deprecation_headers)])
@limiter.limit("30/minute")
async def evaluate_drop_point(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def fn():
        result = evaluate_outcome(drop_point_id, db)
        adjust_thresholds(db)
        return result

    return _with_execution_envelope(
        await _wrap_legacy(request, "rippletrace.legacy.evaluate", fn)
    )
