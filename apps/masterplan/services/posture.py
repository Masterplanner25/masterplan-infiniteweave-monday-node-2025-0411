"""
services/posture.py
Strategic posture determination for MasterPlan creation.

Postures: Stable | Accelerated | Aggressive | Reduced

Logic:
  ambition_score and time_horizon_years drive posture classification.
  Both come from the synthesis draft dict.
"""


def determine_posture(draft: dict) -> str:
    """
    Determine strategic posture from a synthesis draft.

    Returns one of: Stable | Accelerated | Aggressive | Reduced
    """
    horizon = float(draft.get("time_horizon_years", 5))
    ambition = float(draft.get("ambition_score", 0.5))

    # Aggressive: short horizon + high ambition
    if horizon <= 2 and ambition >= 0.7:
        return "Aggressive"

    # Accelerated: moderate-to-short horizon + moderate-high ambition
    if horizon <= 4 and ambition >= 0.6:
        return "Accelerated"

    # Reduced: long horizon + low ambition (conservative/maintenance mode)
    if horizon >= 7 and ambition <= 0.3:
        return "Reduced"

    # Default: Stable (long-term, balanced)
    return "Stable"


def posture_description(posture: str) -> str:
    """Return a one-line description for a given posture label."""
    descriptions = {
        "Stable": "Long-term, balanced execution with steady compounding.",
        "Accelerated": "Faster-than-baseline pace with focused intensity.",
        "Aggressive": "Maximum velocity — compressed timeline, high risk tolerance.",
        "Reduced": "Conservative mode — preserve existing assets, minimal new bets.",
    }
    return descriptions.get(posture, "Unknown posture.")

