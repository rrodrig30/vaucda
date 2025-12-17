"""Stress UI Severity Assessment Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class StressUISeverityCalculator(ClinicalCalculator):
    """Stamey incontinence grading for stress UI."""

    @property
    def name(self) -> str:
        return "Stress UI Severity Assessment"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.FEMALE_UROLOGY

    @property
    def description(self) -> str:
        return "Grade severity of stress urinary incontinence"

    @property
    def references(self) -> List[str]:
        return ["Stamey TA. Endoscopic suspension of the vesical neck for urinary incontinence. Ann Surg. 1973;176:535-546"]

    @property
    def required_inputs(self) -> List[str]:
        return ["stamey_grade"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Stress UI Severity Assessment calculator inputs."""
        return [
            InputMetadata(
                field_name="stamey_grade",
                display_name="Stamey Grade",
                input_type=InputType.ENUM,
                required=True,
                description="Severity grading for stress urinary incontinence",
                allowed_values=[0, 1, 2, 3],
                example="1",
                help_text="Grade 0: No incontinence. Grade 1: With straining/exertion (cough, sneeze, lifting). Grade 2: With walking/standing/mild exertion. Grade 3: Total incontinence at rest."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        try:
            grade = int(inputs["stamey_grade"])
            if grade < 0 or grade > 3:
                return False, "Grade must be 0-3"
        except (ValueError, TypeError):
            return False, "Grade must be integer"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate stress UI severity."""
        grade = int(inputs["stamey_grade"])

        descriptions = {
            0: "No incontinence",
            1: "Incontinence with coughing, sneezing, or heavy lifting",
            2: "Incontinence with walking, standing, or mild exertion",
            3: "Total incontinence (continuous leakage at rest)",
        }

        result = {"stamey_grade": grade, "description": descriptions[grade]}
        interpretation = f"Stamey Grade {grade}: {descriptions[grade]}."

        recommendations = ["Pelvic floor physical therapy initial option", "Surgical intervention if conservative failure"]

        # Map grade to severity/risk level
        risk_level_map = {
            0: "None",
            1: "Mild",
            2: "Moderate",
            3: "Severe"
        }
        risk_level = risk_level_map.get(grade, "Unknown")

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            recommendations=recommendations,
            risk_level=risk_level,
            references=self.references,
        )
