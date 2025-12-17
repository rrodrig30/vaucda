from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class ADAMCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "ADAM Questionnaire"
    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.HYPOGONADISM
    @property
    def description(self) -> str:
        return "Screen for androgen deficiency in aging males"
    @property
    def references(self) -> List[str]:
        return ["Morley JE, et al. Characteristics of men with late-onset hypogonadism. J Gerontol. 2002;57:M245-M250"]
    @property
    def required_inputs(self) -> List[str]:
        return ["decreased_libido", "erection_strength", "symptoms_count"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for ADAM Questionnaire calculator inputs."""
        return [
            InputMetadata(
                field_name="decreased_libido",
                display_name="Question 1: Decreased Libido",
                input_type=InputType.BOOLEAN,
                required=True,
                description="Presence of decreased sexual desire",
                example="false",
                help_text="Key symptom for ADAM screening. Yes = 1 point. Positive if this OR question 7 present."
            ),
            InputMetadata(
                field_name="erection_strength",
                display_name="Question 7: Weaker Erections",
                input_type=InputType.BOOLEAN,
                required=True,
                description="Weaker erections compared to previously",
                example="false",
                help_text="Key symptom for ADAM screening. Yes = 1 point. Positive if this OR question 1 present."
            ),
            InputMetadata(
                field_name="symptoms_count",
                display_name="Number of Other Positive Symptoms",
                input_type=InputType.NUMERIC,
                required=True,
                description="Count of positive answers to remaining ADAM questions (Q2-Q6, Q8-Q10)",
                unit="count",
                min_value=0,
                max_value=10,
                example="2",
                help_text="Screen positive if: decreased libido OR weaker erections OR >= 3 other symptoms."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = ["decreased_libido", "erection_strength", "symptoms_count"]
        for field in required:
            if field not in inputs:
                return False, f"{field} is required"

        try:
            for key in ["decreased_libido", "erection_strength"]:
                val = int(inputs.get(key, 0))
                if val < 0 or val > 1:
                    return False, f"{key} must be 0 or 1"

            symptoms = int(inputs.get("symptoms_count", 0))
            if symptoms < 0 or symptoms > 10:
                return False, "symptoms_count must be 0-10"
        except:
            return False, "Invalid input values"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        decreased_libido = int(inputs.get("decreased_libido", 0))
        erection_strength = int(inputs.get("erection_strength", 0))
        symptoms_count = int(inputs.get("symptoms_count", 0))

        # ADAM positive if: Q1 (libido) OR Q7 (erections) OR >=3 positive symptoms
        screen_positive = bool(decreased_libido) or bool(erection_strength) or (symptoms_count >= 3)

        risk_level = "high" if screen_positive else "low"

        result = {
            'screen_positive': screen_positive,
            'decreased_libido': bool(decreased_libido),
            'erection_strength': bool(erection_strength),
            'positive_symptoms_count': symptoms_count
        }

        interpretation = f"ADAM screen: {'POSITIVE' if screen_positive else 'NEGATIVE'}. Consider testosterone testing if positive."

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=["Testosterone testing if positive", "Check early morning testosterone level", "Consider treatment if testosterone low"],
            references=self.references
        )
