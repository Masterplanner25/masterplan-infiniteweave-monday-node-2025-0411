# enhanced_calculations.py
"""
Enhanced calculation functions with error handling and input validation.
Extends the existing calculations.py with better error handling.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, validator
import numpy as np
from error_handlers import safe_calculation, CalculationError

class CalculationInput(BaseModel):
    """Base input model for all calculations"""
    values: List[float]
    metadata: Dict[str, Any] = {}

class TWRInput(CalculationInput):
    """Input model for Time-Weighted Return calculation"""
    periods: List[float]
    
    @validator('periods')
    def validate_periods_length(cls, v, values):
        if 'values' in values and len(v) != len(values['values']):
            raise ValueError('Periods length must match values length')
        return v

class EnhancedCalculations:
    """
    Enhanced calculation services with comprehensive error handling
    and input validation
    """
    
    @staticmethod
    @safe_calculation("twr")
    def calculate_twr(data: TWRInput) -> float:
        """
        Enhanced TWR calculation with proper error handling
        """
        try:
            if len(data.values) != len(data.periods):
                raise ValueError("Values and periods must have same length")
            
            if any(p <= 0 for p in data.periods):
                raise ValueError("All periods must be positive")
            
            # Original TWR calculation logic
            product = 1.0
            for value, period in zip(data.values, data.periods):
                product *= (1 + value) ** period
            return product - 1.0
            
        except Exception as e:
            raise CalculationError(
                message="TWR calculation failed",
                calculation_type="twr",
                original_error=e
            )
    
    @staticmethod
    @safe_calculation("virality")
    def calculate_virality_coefficient(shares: int, views: int, 
                                     conversions: int = 0) -> float:
        """
        Enhanced virality calculation with validation
        """
        try:
            if shares < 0 or views < 0 or conversions < 0:
                raise ValueError("All inputs must be non-negative")
            
            if views == 0:
                return 0.0
            
            virality = (shares / views) * 100
            if conversions > 0:
                virality *= (conversions / shares) if shares > 0 else 0
            
            return round(virality, 2)
            
        except Exception as e:
            raise CalculationError(
                message="Virality calculation failed",
                calculation_type="virality",
                original_error=e
            )
    
    @staticmethod
    @safe_calculation("revenue_scaling")
    def calculate_revenue_scaling(current_revenue: float, growth_rate: float, 
                                periods: int) -> Dict[str, float]:
        """
        Enhanced revenue scaling calculation with comprehensive output
        """
        try:
            if current_revenue < 0:
                raise ValueError("Current revenue cannot be negative")
            if periods <= 0:
                raise ValueError("Periods must be positive")
            
            projected_revenue = current_revenue * ((1 + growth_rate) ** periods)
            total_growth = projected_revenue - current_revenue
            growth_per_period = total_growth / periods
            
            return {
                "projected_revenue": round(projected_revenue, 2),
                "total_growth": round(total_growth, 2),
                "growth_per_period": round(growth_per_period, 2),
                "growth_rate": growth_rate
            }
            
        except Exception as e:
            raise CalculationError(
                message="Revenue scaling calculation failed",
                calculation_type="revenue_scaling",
                original_error=e
            )