"""International Consultation on Incontinence Questionnaire (ICIQ) Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator, CalculatorCategory, CalculatorResult,
    InputMetadata, InputType,
)


class ICIQCalculator(ClinicalCalculator):
    """ICIQ-UI Short Form for urinary incontinence severity."""

    @property
    def name(self) -> str:
        return "ICIQ-UI Short Form"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_VOIDING

    @property
    def description(self) -> str:
        return "Assess urinary incontinence severity and impact on quality of life"

    @property
    def references(self) -> List[str]:
        return [
            "Avery K, et al. ICIQ: a brief and robust measure for evaluating the symptoms and impact of urinary incontinence. Neurourol Urodyn. 2004;23(4):322-330"
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["frequency", "amount", "impact"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get input schema for ICIQ Incontinence Questionnaire."""
        return [
            InputMetadata("frequency", "Leakage Frequency", InputType.NUMERIC, True, "How often incontinence occurs (0-5)", unit="points", min_value=0, max_value=5, example="2", help_text="0=Never, 1=About once/week or less, 2=2-3 times/week, 3=About once/day, 4=Several times/day, 5=All the time"),
            InputMetadata("amount", "Amount of Leakage", InputType.NUMERIC, True, "Quantity per episode (0-6)", unit="points", min_value=0, max_value=6, example="2", help_text="0=None, 2=Small amount, 4=Moderate amount, 6=Large amount"),
            InputMetadata("impact", "Impact on Quality of Life", InputType.NUMERIC, True, "Severity impact score", unit="points", min_value=0, max_value=10, example="5", help_text="0 = no impact, 10 = severe impact on daily life. Guides treatment intensity."),
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if "frequency" not in inputs or not (0 <= inputs["frequency"] <= 5):
            return False, "Frequency must be 0-5"
        if "amount" not in inputs or not (0 <= inputs["amount"] <= 6):
            return False, "Amount must be 0-6"
        if "impact" not in inputs or not (0 <= inputs["impact"] <= 10):
            return False, "Impact must be 0-10"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        frequency = inputs["frequency"]
        amount = inputs["amount"]
        impact = inputs["impact"]

        total_score = frequency + amount + impact

        if total_score == 0:
            severity = "No incontinence"
        elif total_score <= 5:
            severity = "Slight"
        elif total_score <= 12:
            severity = "Moderate"
        elif total_score <= 18:
            severity = "Severe"
        else:
            severity = "Very severe"

        interpretation = f"ICIQ-UI Score: {total_score}/21. Severity: {severity}"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={"total_score": total_score, "severity": severity},
            interpretation=interpretation,
            risk_level=severity,
            references=self.references
        )
