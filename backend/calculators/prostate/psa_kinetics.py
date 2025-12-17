"""
PSA Kinetics Calculator.

Calculates PSA Velocity (PSAV) and PSA Doubling Time (PSADT).
"""

import math
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class PSAKineticsCalculator(ClinicalCalculator):
    """
    PSA Kinetics Calculator.

    Calculates:
    1. PSA Velocity (PSAV) - Rate of PSA change over time
    2. PSA Doubling Time (PSADT) - Time for PSA to double
    """

    @property
    def name(self) -> str:
        return "PSA Kinetics Calculator"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.PROSTATE_CANCER

    @property
    def description(self) -> str:
        return "Calculate PSA Velocity and PSA Doubling Time for prostate cancer assessment"

    @property
    def references(self) -> List[str]:
        return [
            "D'Amico AV, et al. J Clin Oncol 2004;22:446-453",
            "Carter HB, et al. J Urol 1992;147:815-816",
            "Freedland SJ, et al. JAMA 2005;294:433-439",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["psa_values", "time_points_months"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for PSA Kinetics calculator inputs."""
        return [
            InputMetadata(
                field_name="psa_values",
                display_name="PSA Values Over Time",
                input_type=InputType.TEXT,
                required=True,
                description="Sequential PSA measurements for kinetics calculation (JSON array of numbers)",
                unit="ng/mL",
                example="[4.5, 5.2, 6.1, 7.3]",
                help_text="Minimum 2 values required. Provide as JSON array of numbers, e.g. [4.5, 5.2, 6.1]. Typically 3-5 measurements spanning 6-24 months. Used to calculate PSAV and PSADT."
            ),
            InputMetadata(
                field_name="time_points_months",
                display_name="Time Points for Each PSA Measurement",
                input_type=InputType.TEXT,
                required=True,
                description="Months at which each PSA was measured (must be in ascending order, JSON array of numbers)",
                unit="months",
                example="[0, 3, 6, 12]",
                help_text="Time points must be in chronological order. Provide as JSON array, e.g. [0, 3, 6, 12]. Typically 3-month intervals. First point is baseline (usually 0)."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate inputs for PSA kinetics calculation."""

        # Check required fields
        if "psa_values" not in inputs:
            return False, "PSA values are required"

        if "time_points_months" not in inputs:
            return False, "Time points (months) are required"

        psa_values = inputs["psa_values"]
        time_months = inputs["time_points_months"]

        # Check array types
        if not isinstance(psa_values, (list, tuple)):
            return False, "PSA values must be a list or array"

        if not isinstance(time_months, (list, tuple)):
            return False, "Time points must be a list or array"

        # Check minimum number of data points
        if len(psa_values) < 2:
            return False, "At least 2 PSA values are required"

        # Check array lengths match
        if len(psa_values) != len(time_months):
            return False, "PSA values and time points must have the same length"

        # Check PSA values are positive
        for i, psa in enumerate(psa_values):
            if not isinstance(psa, (int, float)):
                return False, f"PSA value at index {i} must be a number"
            if psa < 0:
                return False, f"PSA values must be positive (found negative value at index {i})"

        # Check time points are monotonically increasing
        for i in range(1, len(time_months)):
            if time_months[i] <= time_months[i-1]:
                return False, "Time points must be strictly increasing (chronological order)"

        # Check time interval is not zero
        time_range = time_months[-1] - time_months[0]
        if time_range == 0:
            return False, "Time interval must be greater than zero"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate PSA kinetics."""

        psa_values = inputs["psa_values"]
        time_months = inputs["time_points_months"]

        # Convert time to years for PSAV calculation
        time_years = np.array([t / 12.0 for t in time_months])
        psa_array = np.array(psa_values)

        results = {}
        interpretation_parts = []
        recommendations = []

        # Calculate PSAV using linear regression
        psav = self._calculate_psav(psa_array, time_years)
        results["psav"] = round(psav, 3)
        results["psav_unit"] = "ng/mL/year"

        # Calculate PSADT using exponential regression (if we have 3+ points)
        if len(psa_values) >= 3:
            psadt_months = self._calculate_psadt(psa_array, time_months)
            if psadt_months is not None:
                results["psadt_months"] = round(psadt_months, 1)
                results["psadt_unit"] = "months"

        # Determine risk level and interpretation
        risk_level = self._determine_risk_level(results, psav)
        interpretation = self._generate_interpretation(results, psav)
        recommendations = self._generate_recommendations(results, psav)

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=results,
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=recommendations,
            references=self.references,
        )

    def _calculate_psav(self, psa_values: np.ndarray, time_years: np.ndarray) -> float:
        """
        Calculate PSA Velocity using linear regression.

        PSAV = slope of PSA vs time (in years)
        Formula: Uses least squares regression
        """
        n = len(time_years)
        sum_x = np.sum(time_years)
        sum_y = np.sum(psa_values)
        sum_xy = np.sum(time_years * psa_values)
        sum_x2 = np.sum(time_years ** 2)

        # Calculate slope using least squares formula
        denominator = n * sum_x2 - sum_x ** 2
        if denominator == 0:
            # All time points are the same (should not happen due to validation)
            return 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denominator

        return slope

    def _calculate_psadt(self, psa_values: np.ndarray, time_months: List[float]) -> Optional[float]:
        """
        Calculate PSA Doubling Time using exponential regression.

        PSADT = ln(2) / slope
        where slope is from linear regression of ln(PSA) vs time
        """
        # Check all PSA values are positive (required for log transformation)
        if np.any(psa_values <= 0):
            return None

        # Natural log transformation of PSA values
        ln_psa = np.log(psa_values)
        time_array = np.array(time_months)

        # Linear regression on ln(PSA) vs time (in months)
        n = len(time_array)
        sum_x = np.sum(time_array)
        sum_y = np.sum(ln_psa)
        sum_xy = np.sum(time_array * ln_psa)
        sum_x2 = np.sum(time_array ** 2)

        # Calculate slope
        denominator = n * sum_x2 - sum_x ** 2
        if denominator == 0:
            return None

        slope = (n * sum_xy - sum_x * sum_y) / denominator

        # Calculate PSADT
        # For exponential growth: PSA(t) = PSA0 * e^(slope * t)
        # Doubling occurs when: 2 * PSA0 = PSA0 * e^(slope * t)
        # Therefore: 2 = e^(slope * t)
        # ln(2) = slope * t
        # t = ln(2) / slope

        if slope > 0:
            psadt_months = math.log(2) / slope
            return psadt_months
        elif slope == 0:
            # Stable PSA - infinite doubling time
            return float('inf')
        else:
            # Decreasing PSA - no doubling time
            return None

    def _determine_risk_level(self, results: Dict[str, Any], psav: float) -> str:
        """
        Determine risk level based on PSAV and PSADT.

        Risk levels:
        - very_high: PSADT <= 3 months (aggressive disease)
        - high: PSADT 3-10 months
        - intermediate: PSADT 10-15 months
        - low: PSADT > 15 months
        - very_low: Stable or decreasing PSA
        """
        # Check PSADT first (most important prognostic factor)
        if "psadt_months" in results:
            psadt = results["psadt_months"]
            if psadt <= 3:
                return "very_high"
            elif psadt < 10:
                return "high"
            elif psadt < 15:
                return "intermediate"
            else:
                return "low"

        # If no PSADT, use PSAV
        if psav > 2.0:
            return "high"
        elif psav > 0.75:
            return "intermediate"
        elif psav > 0:
            return "low"
        else:
            # Stable or decreasing
            return "very_low"

    def _generate_interpretation(self, results: Dict[str, Any], psav: float) -> str:
        """Generate clinical interpretation based on results."""
        parts = []

        # Interpret PSAV
        if psav < 0:
            parts.append(f"PSA Velocity of {psav:.2f} ng/mL/year indicates declining PSA, "
                        "suggesting effective treatment or benign process")
        elif psav == 0 or abs(psav) < 0.01:
            parts.append("PSA Velocity is approximately zero, indicating stable PSA")
        elif psav > 2.0:
            parts.append(f"PSA Velocity of {psav:.2f} ng/mL/year is concerning for "
                        "recurrence or progression and indicates increased metastatic risk")
        elif psav > 0.75:
            parts.append(f"PSA Velocity of {psav:.2f} ng/mL/year is elevated, "
                        "suggesting increased cancer risk")
        else:
            parts.append(f"PSA Velocity of {psav:.2f} ng/mL/year is within acceptable range")

        # Interpret PSADT
        if "psadt_months" in results:
            psadt = results["psadt_months"]
            if psadt <= 3:
                parts.append(f"PSA Doubling Time of {psadt:.1f} months indicates "
                           "aggressive disease with high metastatic risk")
            elif psadt < 10:
                parts.append(f"PSA Doubling Time of {psadt:.1f} months indicates "
                           "intermediate to high risk disease")
            elif psadt < 15:
                parts.append(f"PSA Doubling Time of {psadt:.1f} months indicates "
                           "lower risk disease")
            elif psadt > 100:
                parts.append("PSA Doubling Time is very long (>100 months), "
                           "suggesting indolent or stable disease")
            else:
                parts.append(f"PSA Doubling Time of {psadt:.1f} months suggests "
                           "indolent disease behavior")
        elif psav < 0:
            parts.append("PSA Doubling Time not applicable for decreasing PSA")

        return ". ".join(parts) + "."

    def _generate_recommendations(self, results: Dict[str, Any], psav: float) -> List[str]:
        """Generate clinical recommendations based on results."""
        recommendations = []

        # Recommendations based on PSADT
        if "psadt_months" in results:
            psadt = results["psadt_months"]
            if psadt <= 3:
                recommendations.append("Urgent evaluation for treatment intensification recommended")
                recommendations.append("Consider systemic imaging (bone scan, CT) to evaluate for metastases")
            elif psadt < 9:
                recommendations.append("Consider treatment modification or intensification")
                recommendations.append("Closer monitoring interval recommended (every 3 months)")
            elif psadt < 15:
                recommendations.append("Continue current management with regular monitoring")
                recommendations.append("Monitor PSA every 3-6 months")

        # Additional recommendations based on PSAV
        if psav > 2.0 and not recommendations:
            recommendations.append("Consider further evaluation for recurrence or progression")
            recommendations.append("May warrant treatment modification")
        elif psav > 0.75 and not recommendations:
            recommendations.append("Close monitoring recommended (every 3-6 months)")

        if not recommendations:
            recommendations.append("Continue routine monitoring as per standard guidelines")

        return recommendations
