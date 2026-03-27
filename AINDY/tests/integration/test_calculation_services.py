"""
test_calculation_services.py
────────────────────────────
Diagnostic tests for services/calculation_services.py.
Tests cover every public function, edge cases, and the C++/Python kernel flag.

Failing tests document known bugs; they are intentional.
"""
import pytest
from unittest.mock import MagicMock, patch


# ── Import the module under test ──────────────────────────────────────────────
from services import calculation_services
from schemas.analytics_inputs import (
    TaskInput,
    EngagementInput,
    AIEfficiencyInput,
    ImpactInput,
    EfficiencyInput,
    RevenueScalingInput,
    ExecutionSpeedInput,
    AttentionValueInput,
    EngagementRateInput,
    BusinessGrowthInput,
    MonetizationEfficiencyInput,
    AIProductivityBoostInput,
    LostPotentialInput,
    DecisionEfficiencyInput,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_task(time_spent=2.0, task_complexity=3, skill_level=4,
              ai_utilization=3, task_difficulty=2):
    return TaskInput(
        task_name="Test Task",
        time_spent=time_spent,
        task_complexity=task_complexity,
        skill_level=skill_level,
        ai_utilization=ai_utilization,
        task_difficulty=task_difficulty,
    )


# ── LHI / TWR ─────────────────────────────────────────────────────────────────

class TestTWR:
    def test_lhi_formula(self):
        """LHI = time_spent × task_complexity × skill_level; verify indirectly via TWR numerator."""
        task = make_task(time_spent=1.0, task_complexity=2, skill_level=3, ai_utilization=1, task_difficulty=1)
        # LHI = 1.0 * 2 * 3 = 6.0
        # TWR = (6.0 * 1 * 1.0) / 1 = 6.0
        result = calculation_services.calculate_twr(task)
        assert result == pytest.approx(6.0, rel=1e-6)

    def test_twr_formula_values(self):
        """TWR = (LHI × ai_utilization × time_spent) / task_difficulty."""
        task = make_task(time_spent=2.0, task_complexity=3, skill_level=4, ai_utilization=3, task_difficulty=2)
        # LHI = 2.0 * 3 * 4 = 24.0
        # TWR = (24.0 * 3 * 2.0) / 2 = 144.0 / 2 = 72.0
        result = calculation_services.calculate_twr(task)
        assert result == pytest.approx(72.0, rel=1e-6)

    def test_twr_zero_difficulty_raises(self):
        """
        BUG FIXED: task_difficulty=0 now raises ValueError (service guard) or
        pydantic.ValidationError (schema-level validator) instead of ZeroDivisionError.
        See TECH_DEBT.md §9.
        """
        from pydantic import ValidationError
        with pytest.raises((ValueError, ValidationError)):
            task = make_task(task_difficulty=0)
            calculation_services.calculate_twr(task)


# ── Engagement Score ───────────────────────────────────────────────────────────

class TestEngagementScore:
    def test_engagement_score_formula(self, sample_engagement_input):
        """Engagement = weighted_dot([likes,shares,comments,clicks,top] , [2,3,1.5,1,0.5]) / total_views."""
        data = sample_engagement_input
        # 100*2 + 50*3 + 30*1.5 + 200*1 + 45*0.5 = 200+150+45+200+22.5 = 617.5
        # 617.5 / 1000 = 0.6175 → rounds to 0.62
        result = calculation_services.calculate_engagement_score(data)
        assert result == pytest.approx(0.62, abs=0.01)

    def test_engagement_zero_views_returns_zero(self):
        """total_views=0 must NOT raise ZeroDivisionError; should return 0."""
        data = EngagementInput(
            likes=100, shares=50, comments=30, clicks=200,
            time_on_page=45.0, total_views=0
        )
        # The code checks `if data.total_views == 0: return 0` — this should work
        result = calculation_services.calculate_engagement_score(data)
        assert result == 0


# ── C++ Kernel flag ────────────────────────────────────────────────────────────

class TestCPPKernel:
    def test_cpp_kernel_flag_exists(self):
        """_USE_CPP_KERNEL flag must be present in the module."""
        assert hasattr(calculation_services, "_USE_CPP_KERNEL"), (
            "_USE_CPP_KERNEL flag missing from calculation_services"
        )

    def test_cpp_kernel_flag_is_bool(self):
        """_USE_CPP_KERNEL must be a boolean."""
        assert isinstance(calculation_services._USE_CPP_KERNEL, bool)

    def test_cpp_python_parity(self):
        """
        When C++ kernel IS available, results must match Python fallback within 1e-9.
        When NOT available, Python fallback is used — test that it is deterministic.
        """
        import math
        values = [2.0, 3.0, 1.5, 1.0, 0.5]
        weights = [100.0, 50.0, 30.0, 200.0, 45.0]

        # Python fallback
        python_result = sum(v * w for v, w in zip(values, weights))

        if calculation_services._USE_CPP_KERNEL:
            cpp_result = calculation_services._cpp_weighted_dot(values, weights)
            assert abs(cpp_result - python_result) < 1e-9, (
                f"C++ kernel result {cpp_result} differs from Python {python_result} by more than 1e-9"
            )
        else:
            # fallback is used — ensure deterministic
            result1 = calculation_services._cpp_weighted_dot(values, weights)
            result2 = calculation_services._cpp_weighted_dot(values, weights)
            assert result1 == result2


# ── Other calculation functions ────────────────────────────────────────────────

class TestOtherCalculations:
    def test_calculate_effort(self):
        task = make_task(time_spent=4.0, task_complexity=3, skill_level=2, ai_utilization=1)
        result = calculation_services.calculate_effort(task)
        # (4.0 * 3) / (2 + 1 + 1) = 12/4 = 3.0
        assert result == pytest.approx(3.0, rel=1e-6)

    def test_calculate_productivity(self):
        task = make_task(time_spent=3.0, skill_level=4, ai_utilization=2)
        result = calculation_services.calculate_productivity(task)
        # (2 * 4) / (3.0 + 1) = 8 / 4 = 2.0
        assert result == pytest.approx(2.0, rel=1e-6)

    def test_calculate_virality(self):
        result = calculation_services.calculate_virality(
            share_rate=0.5, engagement_rate=0.3, conversion_rate=0.1, time_factor=2.0
        )
        # (0.5 * 0.3 * 0.1) / (2.0 + 1) = 0.015 / 3 = 0.005
        assert result == pytest.approx(0.005, rel=1e-6)

    def test_calculate_ai_efficiency_zero_tasks(self):
        data = AIEfficiencyInput(ai_contributions=10, human_contributions=5, total_tasks=0)
        assert calculation_services.calculate_ai_efficiency(data) == 0

    def test_calculate_ai_efficiency(self):
        data = AIEfficiencyInput(ai_contributions=10, human_contributions=5, total_tasks=10)
        result = calculation_services.calculate_ai_efficiency(data)
        # (10 / (5+1)) * (10 / 10) = (10/6) * 1 ≈ 1.67
        assert result == pytest.approx(round((10/6)*1, 2), abs=0.01)

    def test_calculate_impact_score_zero_reach(self):
        data = ImpactInput(reach=0, engagement=100, conversion=5)
        assert calculation_services.calculate_impact_score(data) == 0

    def test_income_efficiency(self):
        data = EfficiencyInput(focused_effort=8.0, ai_utilization=3.0, time=4.0, capital=2.0)
        result = calculation_services.income_efficiency(data)
        # (8.0 * 3.0) / (4.0 + 2.0) = 24/6 = 4.0
        assert result == pytest.approx(4.0, rel=1e-6)

    def test_revenue_scaling(self):
        data = RevenueScalingInput(
            ai_leverage=5.0, content_distribution=3.0,
            time=2.0, audience_engagement=0.5
        )
        result = calculation_services.revenue_scaling(data)
        # ((5+3)/2) * 0.5 = 4.0 * 0.5 = 2.0
        assert result == pytest.approx(2.0, rel=1e-6)

    def test_execution_speed(self):
        data = ExecutionSpeedInput(ai_automations=10.0, systemized_workflows=5.0, decision_lag=3.0)
        result = calculation_services.execution_speed(data)
        # (10+5)/3 = 5.0
        assert result == pytest.approx(5.0, rel=1e-6)

    def test_attention_value(self):
        data = AttentionValueInput(content_output=20.0, platform_presence=4.0, time=5.0)
        result = calculation_services.attention_value(data)
        # (20*4)/5 = 16.0
        assert result == pytest.approx(16.0, rel=1e-6)

    def test_engagement_rate(self):
        data = EngagementRateInput(total_interactions=50.0, total_views=500.0)
        result = calculation_services.engagement_rate(data)
        assert result == pytest.approx(0.1, rel=1e-6)

    def test_business_growth(self):
        data = BusinessGrowthInput(revenue=10000.0, expenses=6000.0, scaling_friction=2.0)
        result = calculation_services.business_growth(data)
        # (10000-6000)/2 = 2000.0
        assert result == pytest.approx(2000.0, rel=1e-6)

    def test_monetization_efficiency(self):
        data = MonetizationEfficiencyInput(total_revenue=5000.0, audience_size=1000.0)
        result = calculation_services.monetization_efficiency(data)
        assert result == pytest.approx(5.0, rel=1e-6)

    def test_ai_productivity_boost(self):
        data = AIProductivityBoostInput(tasks_with_ai=100.0, tasks_without_ai=60.0, time_saved=4.0)
        result = calculation_services.ai_productivity_boost(data)
        # (100-60)/4 = 10.0
        assert result == pytest.approx(10.0, rel=1e-6)

    def test_lost_potential(self):
        data = LostPotentialInput(missed_opportunities=5.0, time_delayed=3.0, gains_from_action=2.0)
        result = calculation_services.lost_potential(data)
        # (5*3) - 2 = 13.0
        assert result == pytest.approx(13.0, rel=1e-6)

    def test_decision_efficiency(self):
        data = DecisionEfficiencyInput(
            automated_decisions=50.0, manual_decisions=10.0, processing_time=5.0
        )
        result = calculation_services.decision_efficiency(data)
        # 50 / (10 + 5) = 50/15 ≈ 3.333...
        assert result == pytest.approx(50/15, rel=1e-6)


# ── DB save ────────────────────────────────────────────────────────────────────

class TestSaveCalculation:
    def test_save_calculation_calls_db_add_and_commit(self):
        """save_calculation() must call db.add() and db.commit()."""
        mock_db = MagicMock()

        # The CalculationResult instance returned by refresh needs an id
        saved_obj = MagicMock()
        saved_obj.id = 42
        mock_db.refresh.side_effect = lambda obj: None

        result = calculation_services.save_calculation(mock_db, "TestMetric", 3.14)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_save_calculation_returns_none_on_exception(self):
        """save_calculation() catches DB errors and returns None rather than raising."""
        mock_db = MagicMock()
        mock_db.add.side_effect = Exception("DB connection lost")

        result = calculation_services.save_calculation(mock_db, "BrokenMetric", 1.0)

        # Should not raise — returns None on failure
        assert result is None
        mock_db.rollback.assert_called_once()
