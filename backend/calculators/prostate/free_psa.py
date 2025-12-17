"""
Free PSA Ratio Calculator.

Calculates percentage of free PSA relative to total PSA and provides
cancer risk assessment based on the free PSA percentage.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class FreePSACalculator(ClinicalCalculator):
    """
    Free PSA Ratio Calculator.

    Calculates:
    1. Free PSA percentage: (free_psa / total_psa) × 100
    2. Cancer risk stratification based on free PSA ratio
    3. Clinical recommendations based on Hybritech and Beckman Coulter data
    """

    @property
    def name(self) -> str:
        return "Free PSA Ratio Calculator"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.PROSTATE_CANCER

    @property
    def description(self) -> str:
        return "Calculate free PSA percentage and assess prostate cancer risk"

    @property
    def references(self) -> List[str]:
        return [
            "Catalona WJ, et al. Evaluation of percentage of free serum prostate-specific antigen to improve specificity of prostate cancer screening. JAMA. 1995;274:1214-1220",
            "Christensson A, et al. Serum prostate specific antigen complexed to alpha 1-antichymotrypsin as an indicator of prostate cancer. J Urol. 1993;150:100-105",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["total_psa", "free_psa"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Free PSA Ratio calculator inputs."""
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
                help_text="Normal: <4.0 ng/mL. Gray zone (4-10 ng/mL) is where free PSA ratio is most useful for cancer risk assessment."
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
                help_text="Free PSA is a portion of total PSA. High free/total ratio (>25%) suggests benign disease, low ratio (<10%) suggests cancer."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate free PSA inputs."""

        # Check required fields
        is_valid, msg = self._validate_required(inputs, ["total_psa", "free_psa"])
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

        # Validate that free PSA <= total PSA
        total = float(inputs["total_psa"])
        free = float(inputs["free_psa"])

        if free > total:
            return False, "Free PSA cannot exceed total PSA"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate free PSA ratio."""

        total_psa = float(inputs["total_psa"])
        free_psa = float(inputs["free_psa"])

        # Calculate percentage
        if total_psa > 0:
            free_psa_percent = (free_psa / total_psa) * 100
        else:
            free_psa_percent = 0

        # Risk stratification based on free PSA percentage
        # Based on Catalona et al. JAMA 1995
        if free_psa_percent >= 25:
            risk_category = "Low"
            cancer_probability = "~8-25%"
            clinical_significance = "Likely benign"
        elif free_psa_percent >= 20:
            risk_category = "Low-Intermediate"
            cancer_probability = "~20-35%"
            clinical_significance = "Probably benign"
        elif free_psa_percent >= 15:
            risk_category = "Intermediate"
            cancer_probability = "~30-40%"
            clinical_significance = "Unclear"
        elif free_psa_percent >= 10:
            risk_category = "Intermediate-High"
            cancer_probability = "~40-55%"
            clinical_significance = "Probably malignant"
        else:
            risk_category = "High"
            cancer_probability = "~50-75%"
            clinical_significance = "Likely malignant"

        # Context-dependent interpretation
        total_psa_context = ""
        if total_psa < 4.0:
            total_psa_context = (
                "Total PSA < 4.0 is generally considered normal; "
                "free PSA ratio less clinically relevant"
            )
        elif total_psa < 10:
            total_psa_context = (
                "Total PSA 4-10 is gray zone; free PSA ratio helps risk stratification"
            )
        else:
            total_psa_context = (
                "Total PSA > 10 suggests higher cancer risk regardless of free PSA ratio"
            )

        # Build interpretation
        interpretation_parts = [
            f"Free PSA percentage: {free_psa_percent:.1f}%",
            f"Risk category: {risk_category}",
            f"Estimated cancer probability: {cancer_probability}",
            f"Clinical significance: {clinical_significance}",
            total_psa_context,
        ]

        # Recommendations
        recommendations = []

        if free_psa_percent >= 25:
            recommendations.append("Low cancer risk; consider conservative management")
            recommendations.append("Repeat PSA measurement in 12 months")
        elif free_psa_percent >= 20:
            recommendations.append(
                "Low-intermediate risk; discuss biopsy vs. close monitoring"
            )
            recommendations.append("Consider PSA kinetics assessment")
        elif free_psa_percent >= 15:
            recommendations.append(
                "Intermediate risk; consider advanced imaging or biopsy"
            )
            recommendations.append("Evaluate PSA density and velocity")
        elif free_psa_percent >= 10:
            recommendations.append("Intermediate-high risk; biopsy consideration")
            recommendations.append("Evaluate for other risk factors")
        else:
            recommendations.append("High cancer risk; strong biopsy recommendation")
            recommendations.append(
                "Consider urgent urology referral for biopsy evaluation"
            )

        result = {
            "total_psa_ng_mL": round(total_psa, 2),
            "free_psa_ng_mL": round(free_psa, 2),
            "free_psa_percent": round(free_psa_percent, 1),
            "risk_category": risk_category,
            "cancer_probability": cancer_probability,
        }

        interpretation = ". ".join(interpretation_parts) + "."

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_category,
            recommendations=recommendations,
            references=self.references,
        )
