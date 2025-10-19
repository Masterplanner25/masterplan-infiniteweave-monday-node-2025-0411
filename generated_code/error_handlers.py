# error_handlers.py
"""
Enhanced error handling and input validation for calculation services.
Addresses missing error handling identified in analysis.
"""
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, validator
from typing import Any, Dict, List, Optional
import logging
import traceback

logger = logging.getLogger(__name__)

class CalculationError(Exception):
    """Custom exception for calculation-related errors"""
    def __init__(self, message: str, calculation_type: str = None, original_error: Exception = None):
        self.message = message
        self.calculation_type = calculation_type
        self.original_error = original_error
        super().__init__(self.message)

class ValidationError(Exception):
    """Custom exception for input validation errors"""
    pass

def validate_calculation_input(input_data: BaseModel, calculation_type: str) -> None:
    """
    Enhanced input validation for calculation services
    """
    errors = []
    
    # Common validations across all calculation types
    if hasattr(input_data, 'values') and input_data.values:
        if not all(isinstance(v, (int, float)) for v in input_data.values):
            errors.append("All values must be numeric")
        
        if len(input_data.values) < 2:
            errors.append("At least 2 values required for calculation")
    
    # Type-specific validations
    if calculation_type == "twr":
        if hasattr(input_data, 'periods') and input_data.periods:
            if any(p <= 0 for p in input_data.periods):
                errors.append("All periods must be positive")
    
    elif calculation_type == "virality":
        if hasattr(input_data, 'shares') and input_data.shares < 0:
            errors.append("Shares cannot be negative")
        if hasattr(input_data, 'views') and input_data.views < 0:
            errors.append("Views cannot be negative")
    
    elif calculation_type in ["revenue_scaling", "business_growth"]:
        if hasattr(input_data, 'revenue') and input_data.revenue < 0:
            errors.append("Revenue cannot be negative")
        if hasattr(input_data, 'customers') and input_data.customers < 0:
            errors.append("Customer count cannot be negative")
    
    if errors:
        raise ValidationError(f"Input validation failed for {calculation_type}: {', '.join(errors)}")

async def calculation_error_handler(request: Request, exc: CalculationError) -> JSONResponse:
    """Global error handler for calculation errors"""
    logger.error(f"Calculation error in {exc.calculation_type}: {exc.message}")
    
    if exc.original_error:
        logger.error(f"Original error: {traceback.format_exception(type(exc.original_error), exc.original_error, exc.original_error.__traceback__)}")
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "CalculationError",
            "calculation_type": exc.calculation_type,
            "message": exc.message,
            "detail": str(exc.original_error) if exc.original_error else None
        }
    )

async def validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Global error handler for validation errors"""
    return JSONResponse(
        status_code=400,
        content={
            "error": "ValidationError",
            "message": str(exc)
        }
    )

def safe_calculation(calculation_type: str):
    """
    Decorator for calculation functions that adds error handling and validation
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                # Extract input data from args or kwargs
                input_data = None
                for arg in args:
                    if isinstance(arg, BaseModel):
                        input_data = arg
                        break
                
                if not input_data:
                    for key, value in kwargs.items():
                        if isinstance(value, BaseModel):
                            input_data = value
                            break
                
                # Validate input if we found a BaseModel
                if input_data:
                    validate_calculation_input(input_data, calculation_type)
                
                # Execute calculation
                result = func(*args, **kwargs)
                return result
                
            except ValidationError:
                raise  # Re-raise validation errors
            except Exception as e:
                raise CalculationError(
                    message=f"Calculation failed for {calculation_type}",
                    calculation_type=calculation_type,
                    original_error=e
                )
        return wrapper
    return decorator