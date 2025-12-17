"""
Clinical Calculator Framework for VAUCDA.

Provides base classes and registry for all 44 urologic clinical calculators
organized across 10 specialties with 100% mathematical accuracy.
"""

from calculators.base import (
    ClinicalCalculator,
    CalculatorResult,
    CalculatorInput,
    ValidationError,
)
from calculators.registry import CalculatorRegistry

__all__ = [
    "ClinicalCalculator",
    "CalculatorResult",
    "CalculatorInput",
    "ValidationError",
    "CalculatorRegistry",
]
