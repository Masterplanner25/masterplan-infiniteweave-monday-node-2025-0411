from datetime import datetime, timedelta
import numpy as np

# 🔥 Add a scaling constant at the top
COMPRESSION_DIVISOR = 100  # Start here, calibrate later

def project_completion(masterplan, twr_values):
    if not twr_values:
        return None

    twr_array = np.array(twr_values)

    conservative = np.percentile(twr_array, 30)
    aggressive = np.percentile(twr_array, 70)
    optimal = np.max(twr_array)

    today = datetime.utcnow()
    remaining_days = (masterplan.target_date - today).days

    def projected_eta(rate):
        if rate <= 0:
            return masterplan.target_date

        # 🔥 Normalize TWR before using it as compression factor
        effective_rate = rate / COMPRESSION_DIVISOR

        if effective_rate <= 0:
            return masterplan.target_date

        adjusted_days = remaining_days / effective_rate
        return today + timedelta(days=adjusted_days)

    return {
        "conservative_eta": projected_eta(conservative),
        "aggressive_eta": projected_eta(aggressive),
        "optimal_eta": projected_eta(optimal)
    }

def evaluate_phase(plan):
    phase_end = plan.start_date + timedelta(days=plan.duration_years * 365)
    now = datetime.utcnow()

    thresholds_met = (
        plan.total_wcu >= plan.wcu_target and
        plan.gross_revenue >= plan.revenue_target and
        plan.books_published >= plan.books_required and
        (not plan.platform_required or plan.platform_live) and
        (not plan.studio_required or plan.studio_ready) and
        plan.active_playbooks >= plan.playbooks_required
    )

    if thresholds_met:
        return 2

    if now >= phase_end:
        return 2

    return 1