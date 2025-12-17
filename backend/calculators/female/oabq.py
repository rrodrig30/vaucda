"""OAB-q Overactive Bladder Questionnaire Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class OABQCalculator(ClinicalCalculator):
    """OAB-q symptom bother and quality of life assessment."""

    @property
    def name(self) -> str:
        return "OAB-q Short Form"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.FEMALE_UROLOGY

    @property
    def description(self) -> str:
        return "Assess overactive bladder symptom bother and quality of life"

    @property
    def references(self) -> List[str]:
        return ["Coyne KS, et al. The development of the overactive bladder questionnaire. Neurourol Urodyn. 2006;25:472-480"]

    @property
    def required_inputs(self) -> List[str]:
        return ["symptom_bother_score", "qol_score"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for OAB-q Short Form calculator inputs."""
        return [
            InputMetadata(
                field_name="symptom_bother_score",
                display_name="Symptom Bother Score",
                input_type=InputType.NUMERIC,
                required=True,
                description="Score reflecting how bothersome OAB symptoms are",
                unit="score",
                min_value=0,
                max_value=100,
                example="65",
                help_text="0-100 scale. Higher score indicates greater symptom bother. Typical scores range from 20-80."
            ),
            InputMetadata(
                field_name="qol_score",
                display_name="Quality of Life Score",
                input_type=InputType.NUMERIC,
                required=True,
                description="OAB impact on health-related quality of life",
                unit="score",
                min_value=0,
                max_value=100,
                example="45",
                help_text="0-100 scale where higher scores indicate better quality of life. Used to assess treatment benefit."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = self.required_inputs
        for field in required:
            if field not in inputs:
                return False, f"{field} is required"

        for param in self.required_inputs:
            is_valid, msg = self._validate_range(inputs[param], min_val=0, max_val=100, param_name=param)
            if not is_valid:
                return False, msg
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate OAB-q scores."""
        symptom = round(float(inputs["symptom_bother_score"]), 1)
        qol = round(float(inputs["qol_score"]), 1)

        result = {"symptom_bother": symptom, "qol_score": qol}

        interpretation = f"OAB symptom bother: {symptom}/100. HRQL: {qol}/100 (higher = better quality of life)."

        recommendations = ["Address modifiable risk factors", "Consider pharmacological therapy if symptoms bothersome"]

        if symptom >= 60:
            severity = "High"
        elif symptom >= 30:
            severity = "Moderate"
        else:
            severity = "Low"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            recommendations=recommendations,
            risk_level=severity,
            references=self.references,
        )
