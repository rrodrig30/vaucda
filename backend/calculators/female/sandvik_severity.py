"""Sandvik Severity Index Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class SandvikCalculator(ClinicalCalculator):
    """Sandvik Incontinence Severity Index."""

    @property
    def name(self) -> str:
        return "Sandvik Severity Index"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.FEMALE_UROLOGY

    @property
    def description(self) -> str:
        return "Assess stress incontinence severity"

    @property
    def references(self) -> List[str]:
        return ["Sandvik H, et al. A severity index for epidemiological surveys of female urinary incontinence. Neurourol Urodyn. 1992;11:497-505"]

    @property
    def required_inputs(self) -> List[str]:
        return ["frequency", "amount"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Sandvik Severity Index calculator inputs."""
        return [
            InputMetadata(
                field_name="frequency",
                display_name="Incontinence Frequency",
                input_type=InputType.ENUM,
                required=True,
                description="How often incontinence episodes occur",
                allowed_values=[1, 2, 3, 4],
                example="2",
                help_text="1: Less than once per month. 2: Once per month. 3: 2-3 times per month. 4: More than once per week."
            ),
            InputMetadata(
                field_name="amount",
                display_name="Amount of Leakage",
                input_type=InputType.ENUM,
                required=True,
                description="Quantity of urine loss per episode",
                allowed_values=[1, 2, 3],
                example="2",
                help_text="1: Drops only. 2: Small amount (dampens underwear). 3: Large amount (soaks clothes/furniture)."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        for param in ["frequency", "amount"]:
            try:
                score = int(inputs[param])
                if score < 1 or score > 4 if param == "frequency" else (score < 1 or score > 3):
                    return False, f"Invalid {param}"
            except (ValueError, TypeError):
                return False, f"{param} must be integer"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate Sandvik index."""
        freq = int(inputs["frequency"])
        amount = int(inputs["amount"])
        severity_index = freq * amount

        severity_map = {
            (1, 1): "Slight", (2, 1): "Slight", (1, 2): "Slight",
            (3, 1): "Moderate", (2, 2): "Moderate", (3, 2): "Moderate", (2, 3): "Moderate",
            (4, 1): "Moderate", (4, 2): "Severe", (3, 3): "Severe",
            (4, 3): "Very Severe",
        }
        severity = severity_map.get((freq, amount), "Unknown")

        result = {"severity_index": severity_index, "severity": severity}
        interpretation = f"Sandvik Index {severity_index}: {severity} incontinence."

        recommendations = ["Treatment tailored to severity", "Consider conservative measures first"]

        # Map severity to risk level
        risk_level_map = {
            "Slight": "Low",
            "Moderate": "Moderate",
            "Severe": "High",
            "Very Severe": "High",
            "Unknown": "Unknown"
        }
        risk_level = risk_level_map.get(severity, "Unknown")

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            recommendations=recommendations,
            risk_level=risk_level,
            references=self.references,
        )
