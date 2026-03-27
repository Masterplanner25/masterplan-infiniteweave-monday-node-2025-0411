from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import get_db
from services.auth_service import verify_api_key
from services.causal_engine import build_causal_graph, get_causal_chain
from services.content_generator import (
    generate_content,
    generate_content_for_drop,
    generate_variations,
)
from services.delta_engine import compute_deltas, emerging_drops, find_momentum_leaders
from services.influence_graph import build_influence_graph, influence_chain
from services.learning_engine import adjust_thresholds, evaluate_outcome, learning_stats
from services.narrative_engine import generate_narrative, narrative_summary
from services.playbook_engine import (
    build_playbook,
    get_playbook,
    list_playbooks,
    match_playbooks,
)
from services.prediction_engine import (
    predict_drop_point,
    prediction_summary,
    scan_drop_point_predictions,
)
from services.recommendation_engine import recommend_for_drop_point, recommendations_summary
from services.strategy_engine import build_strategies, get_strategy, list_strategies, match_strategies
from services.threadweaver import analyze_drop_point, get_dashboard_snapshot, get_top_drop_points

router = APIRouter(
    tags=["Legacy Compatibility"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("/analyze_ripple/{drop_point_id}")
def analyze_ripple(drop_point_id: str, db: Session = Depends(get_db)):
    metrics = analyze_drop_point(drop_point_id, db)
    if not metrics:
        raise HTTPException(status_code=404, detail="Drop point not found")
    return metrics


@router.get("/dashboard")
def proofboard_dashboard(db: Session = Depends(get_db)):
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


@router.get("/top_drop_points")
def top_drop_points(db: Session = Depends(get_db)):
    return {"top_drop_points": get_top_drop_points(db)}


@router.get("/ripple_deltas/{drop_point_id}")
def ripple_deltas(drop_point_id: str, db: Session = Depends(get_db)):
    return compute_deltas(drop_point_id, db)


@router.get("/emerging_drops")
def emerging_drops_view(db: Session = Depends(get_db)):
    return {"emerging_drops": emerging_drops(db)}


@router.get("/predict/{drop_point_id}")
def predict_drop_point_view(drop_point_id: str, db: Session = Depends(get_db)):
    return predict_drop_point(drop_point_id, db)


@router.get("/prediction_summary")
def prediction_summary_view(db: Session = Depends(get_db)):
    return prediction_summary(db)


@router.get("/recommend/{drop_point_id}")
def recommend_drop_point(drop_point_id: str, db: Session = Depends(get_db)):
    return recommend_for_drop_point(drop_point_id, db)


@router.get("/recommendations_summary")
def recommendations_summary_view(db: Session = Depends(get_db)):
    return recommendations_summary(db)


@router.get("/influence_graph")
def influence_graph_view(db: Session = Depends(get_db)):
    return build_influence_graph(db)


@router.get("/influence_chain/{drop_point_id}")
def influence_chain_view(drop_point_id: str, db: Session = Depends(get_db)):
    return influence_chain(drop_point_id, db)


@router.get("/causal_graph")
def causal_graph_view(db: Session = Depends(get_db)):
    return build_causal_graph(db)


@router.get("/causal_chain/{drop_point_id}")
def causal_chain_view(drop_point_id: str, db: Session = Depends(get_db)):
    return get_causal_chain(drop_point_id, db)


@router.get("/narrative/{drop_point_id}")
def narrative_view(drop_point_id: str, db: Session = Depends(get_db)):
    return generate_narrative(drop_point_id, db)


@router.get("/narrative_summary")
def narrative_summary_view(db: Session = Depends(get_db)):
    return {"stories": narrative_summary(db)}


@router.get("/strategies")
def strategies_view(db: Session = Depends(get_db)):
    build_strategies(db)
    return {"strategies": list_strategies(db)}


@router.get("/strategy/{strategy_id}")
def strategy_view(strategy_id: str, db: Session = Depends(get_db)):
    strategy = get_strategy(strategy_id, db)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy


@router.get("/strategy_match/{drop_point_id}")
def strategy_match_view(drop_point_id: str, db: Session = Depends(get_db)):
    return {"matches": match_strategies(drop_point_id, db)}


@router.post("/build_playbook/{strategy_id}")
def build_playbook_view(strategy_id: str, db: Session = Depends(get_db)):
    return build_playbook(strategy_id, db)


@router.get("/playbooks")
def playbooks_view(db: Session = Depends(get_db)):
    return {"playbooks": list_playbooks(db)}


@router.get("/playbook/{playbook_id}")
def playbook_view(playbook_id: str, db: Session = Depends(get_db)):
    playbook = get_playbook(playbook_id, db)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return playbook


@router.get("/playbook_match/{drop_point_id}")
def playbook_match_view(drop_point_id: str, db: Session = Depends(get_db)):
    return {"matches": match_playbooks(drop_point_id, db)}


@router.get("/generate_content/{playbook_id}")
def generate_content_view(playbook_id: str, db: Session = Depends(get_db)):
    return generate_content(playbook_id, db)


@router.post("/generate_content_for_drop/{drop_point_id}")
def generate_content_for_drop_view(drop_point_id: str, db: Session = Depends(get_db)):
    return generate_content_for_drop(drop_point_id, db)


@router.get("/generate_variations/{playbook_id}")
def generate_variations_view(playbook_id: str, db: Session = Depends(get_db)):
    return generate_variations(playbook_id, db)


@router.get("/learning_stats")
def learning_stats_view(db: Session = Depends(get_db)):
    return learning_stats(db)


@router.post("/evaluate/{drop_point_id}")
def evaluate_drop_point(drop_point_id: str, db: Session = Depends(get_db)):
    result = evaluate_outcome(drop_point_id, db)
    adjust_thresholds(db)
    return result
