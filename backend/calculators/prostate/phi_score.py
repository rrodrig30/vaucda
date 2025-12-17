"""
Prostate Health Index (PHI) Score Calculator.

Calculates PHI based on total PSA, free PSA, and PSA(-2)proPSA.
PHI helps distinguish prostate cancer from benign prostate disease.
"""

import math
from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class PHICalculator(ClinicalCalculator):
    """
    Prostate Health Index (PHI) Score Calculator.

    Calculates:
    1. PHI = ([-2]proPSA / free PSA] × √(total PSA)) × 25
    2. Cancer risk stratification based on PHI value
    3. Recommendations for biopsy consideration
    """

    @property
    def name(self) -> str:
        return "Prostate Health Index (PHI)"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.PROSTATE_CANCER

    @property
    def description(self) -> str:
        return "Calculate PHI score for prostate cancer risk assessment"

    @property
    def references(self) -> List[str]:
        return [
            "Catalona WJ, et al. Evaluation of the Prostate Health Index for the detection of aggressive prostate cancer. J Urol. 2015;194:1675-1680",
            "Guazzoni G, et al. Prostate Health Index as a predictor of advanced prostate cancer in men with PSA 2-10 ng/mL and normal DRE. Prostate. 2015;75:1556-1563",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["total_psa", "free_psa", "proPSA_p2"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Prostate Health Index (PHI) calculator inputs."""
        return [
            InputMetadata(
                field_name="total_psa",
                display_name="Total PSA",
                input_type=InputType.NUMERIC,
                required=True,
                description="Total prostate-specific antigen level in serum",
                unit="ng/mL",
                min_value=0.1,
                max_value=200,
                example="6.5",
                help_text="Normal: <4 ng/mL. PHI most useful in 4-10 ng/mL gray zone. Higher total PSA increases cancer probability."
            ),
            InputMetadata(
                field_name="free_psa",
                display_name="Free PSA",
                input_type=InputType.NUMERIC,
                required=True,
                description="Free (unbound) prostate-specific antigen level",
                unit="ng/mL",
                min_value=0,
                max_value=200,
                example="1.95",
                help_text="Portion of total PSA not bound to proteins. Must be ≤ total PSA. Lower free/total ratio suggests cancer."
            ),
            InputMetadata(
                field_name="proPSA_p2",
                display_name="PSA(-2)proPSA",
                input_type=InputType.NUMERIC,
                required=True,
                description="ProPSA isoform (-2)proPSA level",
                unit="ng/mL",
                min_value=0,
                max_value=100,
                example="0.5",
                help_text="PSA precursor form that is more specific for cancer. Component of PHI calculation. Higher values increase cancer probability."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate PHI inputs."""

        # Check required fields
        is_valid, msg = self._validate_required(
            inputs, ["total_psa", "free_psa", "proPSA_p2"]
        )
        if not is_valid:
            return False, msg

        # Validate numeric ranges
        is_valid, msg = self._validate_range(
            inputs["total_psa"], min_val=0.1, max_val=200, param_name="total_psa"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["free_psa"], min_val=0, max_val=200, param_name="free_psa"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["proPSA_p2"], min_val=0, max_val=100, param_name="proPSA_p2"
        )
        if not is_valid:
            return False, msg

        # Validate that free PSA <= total PSA
        total = float(inputs["total_psa"])
        free = float(inputs["free_psa"])

        if free > total:
            return False, "Free PSA cannot exceed total PSA"

        # PHI is primarily used for PSA 4-10 range
        if total < 2 or total > 100:
            return (
                False,
                "PHI is most useful for total PSA between 4-10 ng/mL"
            )

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate PHI score."""

        total_psa = float(inputs["total_psa"])
        free_psa = float(inputs["free_psa"])
        proPSA_p2 = float(inputs["proPSA_p2"])

        # Calculate PHI
        # PHI = ([p2PSA / free PSA] * sqrt[total PSA]) * 25
        if free_psa > 0 and total_psa > 0:
            phi_ratio = (proPSA_p2 / free_psa) * math.sqrt(total_psa)
            phi_score = phi_ratio * 25
        else:
            return CalculatorResult(
                calculator_id=self.calculator_id,
                calculator_name=self.name,
                result={"error": "Cannot calculate PHI with zero values"},
                interpretation="Invalid calculation due to zero values",
                references=self.references,
            )

        # Risk stratification based on PHI
        # Lower PHI = lower cancer risk
        # Higher PHI = higher cancer risk
        if phi_score < 25:
            risk_category = "Very Low"
            cancer_probability = "~6-7%"
            recommendation = "Low cancer risk; consider repeat PSA in 12-24 months"
            risk_level = "Very Low"
        elif phi_score < 45:
            risk_category = "Low-Intermediate"
            cancer_probability = "~8-20%"
            recommendation = "Low-intermediate risk; close monitoring or shared decision-making regarding biopsy"
            risk_level = "Low-Intermediate"
        elif phi_score < 55:
            risk_category = "Intermediate"
            cancer_probability = "~25-35%"
            recommendation = "Consider biopsy or advanced imaging"
            risk_level = "Intermediate"
        else:
            risk_category = "High"
            cancer_probability = "~40-50%"
            recommendation = "High cancer risk; biopsy strongly recommended"
            risk_level = "High"

        # Additional interpretation for PSA zone
        psa_zone = ""
        if total_psa < 4:
            psa_zone = "PSA is normal; PHI less relevant in this setting"
        elif total_psa < 10:
            psa_zone = "PSA is in gray zone (4-10); PHI particularly useful here"
        else:
            psa_zone = "PSA is elevated; PHI helps assess cancer likelihood"

        # Build interpretation
        interpretation_parts = [
            f"PHI Score: {phi_score:.1f}",
            f"Risk Category: {risk_category}",
            f"Estimated cancer probability: {cancer_probability}",
            psa_zone,
            recommendation,
        ]

        # Calculate percent free PSA for reference
        percent_free_psa = (free_psa / total_psa) * 100

        result = {
            "phi_score": round(phi_score, 1),
            "risk_category": risk_category,
            "cancer_probability": cancer_probability,
            "total_psa": round(total_psa, 2),
            "free_psa": round(free_psa, 2),
            "proPSA_p2": round(proPSA_p2, 2),
            "percent_free_psa": round(percent_free_psa, 1),
        }

        recommendations = [
            recommendation,
            "PHI is most useful in PSA 4-10 ng/mL range",
            "Consider PSA kinetics and other risk factors in clinical decision-making",
        ]

        interpretation = ". ".join(interpretation_parts) + "."

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=recommendations,
            references=self.references,
        )
