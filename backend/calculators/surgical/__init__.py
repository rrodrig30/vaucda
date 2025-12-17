"""Surgical Risk Assessment Calculators."""

from calculators.surgical.rcri import RCRICalculator
from calculators.surgical.nsqip import NSQIPCalculator
from calculators.surgical.cfs import CFSCalculator
from calculators.surgical.cci import CCICalculator
from calculators.surgical.life_expectancy_ssa import SSALifeExpectancyCalculator

# Deprecated - unreliable for ages outside 65/75/85
# from calculators.surgical.life_expectancy import LifeExpectancyCalculator

__all__ = [
    "RCRICalculator",
    "NSQIPCalculator",
    "CFSCalculator",
    "CCICalculator",
    "SSALifeExpectancyCalculator",  # Replaced LifeExpectancyCalculator
]
