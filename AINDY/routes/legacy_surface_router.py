from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from AINDY.core.execution_helper import execute_with_pipeline_sync
from AINDY.db.database import get_db
from AINDY.services.auth_service import verify_api_key

from AINDY.analytics.causal_engine import build_causal_graph, get_causal_chain
from AINDY.domain.content_generator import (
    generate_content,
    generate_content_for_drop,
    generate_variations,
)
from AINDY.analytics.delta_engine import compute_deltas, emerging_drops, find_momentum_leaders
from AINDY.analytics.influence_graph import build_influence_graph, influence_chain
from AINDY.analytics.learning_engine import adjust_thresholds, evaluate_outcome, learning_stats
from AINDY.analytics.narrative_engine import generate_narrative, narrative_summary
from AINDY.analytics.playbook_engine import (
    build_playbook,
    get_playbook,
    list_playbooks,
    match_playbooks,
)
from AINDY.analytics.prediction_engine import (
    predict_drop_point,
    prediction_summary,
    scan_drop_point_predictions,
)
from AINDY.analytics.recommendation_engine import (
    recommend_for_drop_point,
    recommendations_summary,
)
from AINDY.domain.strategy_engine import (
    build_strategies,
    get_strategy,
    list_strategies,
    match_strategies,
)
from AINDY.utils.threadweaver import (
    analyze_drop_point,
    get_dashboard_snapshot,
    get_top_drop_points,
)

router = APIRouter(
    tags=["Legacy Compatibility"],
    dependencies=[Depends(verify_api_key)],
)


# ------------------------------
# ANALYZE
# ------------------------------
@router.get("/analyze_ripple/{drop_point_id}")
def analyze_ripple(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def handler(ctx):
        metrics = analyze_drop_point(drop_point_id, db)
        if not metrics:
            raise HTTPException(status_code=404, detail="Drop point not found")
        return metrics

    return execute_with_pipeline_sync(request, "analyze_ripple", handler)


# ------------------------------
# DASHBOARD
# ------------------------------
@router.get("/dashboard")
def proofboard_dashboard(request: Request, db: Session = Depends(get_db)):
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

    return execute_with_pipeline_sync(request, "dashboard", handler)


# ------------------------------
# SIMPLE PASS-THROUGH ENDPOINTS
# ------------------------------

def wrap(request, name, fn):
    def handler(ctx):
        return fn()
    return execute_with_pipeline_sync(request, name, handler)


@router.get("/top_drop_points")
def top_drop_points(request: Request, db: Session = Depends(get_db)):
    return wrap(request, "top_drop_points", lambda: {"top_drop_points": get_top_drop_points(db)})


@router.get("/ripple_deltas/{drop_point_id}")
def ripple_deltas(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    return wrap(request, "ripple_deltas", lambda: compute_deltas(drop_point_id, db))


@router.get("/emerging_drops")
def emerging_drops_view(request: Request, db: Session = Depends(get_db)):
    return wrap(request, "emerging_drops", lambda: {"emerging_drops": emerging_drops(db)})


@router.get("/predict/{drop_point_id}")
def predict_drop_point_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    return wrap(request, "predict", lambda: predict_drop_point(drop_point_id, db))


@router.get("/prediction_summary")
def prediction_summary_view(request: Request, db: Session = Depends(get_db)):
    return wrap(request, "prediction_summary", lambda: prediction_summary(db))


@router.get("/recommend/{drop_point_id}")
def recommend_drop_point(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    return wrap(request, "recommend", lambda: recommend_for_drop_point(drop_point_id, db))


@router.get("/recommendations_summary")
def recommendations_summary_view(request: Request, db: Session = Depends(get_db)):
    return wrap(request, "recommendations_summary", lambda: recommendations_summary(db))


@router.get("/influence_graph")
def influence_graph_view(request: Request, db: Session = Depends(get_db)):
    return wrap(request, "influence_graph", lambda: build_influence_graph(db))


@router.get("/influence_chain/{drop_point_id}")
def influence_chain_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    return wrap(request, "influence_chain", lambda: influence_chain(drop_point_id, db))


@router.get("/causal_graph")
def causal_graph_view(request: Request, db: Session = Depends(get_db)):
    return wrap(request, "causal_graph", lambda: build_causal_graph(db))


@router.get("/causal_chain/{drop_point_id}")
def causal_chain_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    return wrap(request, "causal_chain", lambda: get_causal_chain(drop_point_id, db))


@router.get("/narrative/{drop_point_id}")
def narrative_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    return wrap(request, "narrative", lambda: generate_narrative(drop_point_id, db))


@router.get("/narrative_summary")
def narrative_summary_view(request: Request, db: Session = Depends(get_db)):
    return wrap(request, "narrative_summary", lambda: {"stories": narrative_summary(db)})


@router.get("/strategies")
def strategies_view(request: Request, db: Session = Depends(get_db)):
    def fn():
        build_strategies(db)
        return {"strategies": list_strategies(db)}
    return wrap(request, "strategies", fn)


@router.get("/strategy/{strategy_id}")
def strategy_view(request: Request, strategy_id: str, db: Session = Depends(get_db)):
    def fn():
        strategy = get_strategy(strategy_id, db)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        return strategy
    return wrap(request, "strategy", fn)


@router.get("/strategy_match/{drop_point_id}")
def strategy_match_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    return wrap(request, "strategy_match", lambda: {"matches": match_strategies(drop_point_id, db)})


@router.post("/build_playbook/{strategy_id}")
def build_playbook_view(request: Request, strategy_id: str, db: Session = Depends(get_db)):
    return wrap(request, "build_playbook", lambda: build_playbook(strategy_id, db))


@router.get("/playbooks")
def playbooks_view(request: Request, db: Session = Depends(get_db)):
    return wrap(request, "playbooks", lambda: {"playbooks": list_playbooks(db)})


@router.get("/playbook/{playbook_id}")
def playbook_view(request: Request, playbook_id: str, db: Session = Depends(get_db)):
    def fn():
        playbook = get_playbook(playbook_id, db)
        if not playbook:
            raise HTTPException(status_code=404, detail="Playbook not found")
        return playbook
    return wrap(request, "playbook", fn)


@router.get("/playbook_match/{drop_point_id}")
def playbook_match_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    return wrap(request, "playbook_match", lambda: {"matches": match_playbooks(drop_point_id, db)})


@router.get("/generate_content/{playbook_id}")
def generate_content_view(request: Request, playbook_id: str, db: Session = Depends(get_db)):
    return wrap(request, "generate_content", lambda: generate_content(playbook_id, db))


@router.post("/generate_content_for_drop/{drop_point_id}")
def generate_content_for_drop_view(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    return wrap(request, "generate_content_for_drop", lambda: generate_content_for_drop(drop_point_id, db))


@router.get("/generate_variations/{playbook_id}")
def generate_variations_view(request: Request, playbook_id: str, db: Session = Depends(get_db)):
    return wrap(request, "generate_variations", lambda: generate_variations(playbook_id, db))


@router.get("/learning_stats")
def learning_stats_view(request: Request, db: Session = Depends(get_db)):
    return wrap(request, "learning_stats", lambda: learning_stats(db))


@router.post("/evaluate/{drop_point_id}")
def evaluate_drop_point(request: Request, drop_point_id: str, db: Session = Depends(get_db)):
    def fn():
        result = evaluate_outcome(drop_point_id, db)
        adjust_thresholds(db)
        return result
    return wrap(request, "evaluate", fn)

