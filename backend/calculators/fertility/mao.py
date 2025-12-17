"""Male Aging and Hypogonadism (MAO) Questionnaire Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class MAOCalculator(ClinicalCalculator):
    """Male Aging and Hypogonadism Questionnaire for screening testosterone deficiency."""

    @property
    def name(self) -> str:
        return "MAO Questionnaire"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_FERTILITY

    @property
    def description(self) -> str:
        return "Screen for androgen deficiency in aging males"

    @property
    def references(self) -> List[str]:
        return [
            "Morley JE, et al. Validation of a screening questionnaire for androgen deficiency in aging males. Metabolism. 2000;49(9):1239-1242"
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["decreased_libido", "decreased_energy", "decreased_strength", "lost_height",
                "decreased_enjoyment", "sad_grumpy", "erections_less_strong", "sports_ability_decline",
                "falling_asleep", "decreased_work_performance"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for MAO Questionnaire calculator inputs."""
        symptoms = [
            ("decreased_libido", "Decreased sexual desire?"),
            ("decreased_energy", "Lack of energy/fatigue?"),
            ("decreased_strength", "Loss of muscle strength?"),
            ("lost_height", "Loss of height (>3 cm)?"),
            ("decreased_enjoyment", "Decreased enjoyment of life?"),
            ("sad_grumpy", "Feeling sad or irritable?"),
            ("erections_less_strong", "Weaker erections?"),
            ("sports_ability_decline", "Decreased ability in sports?"),
            ("falling_asleep", "Difficulty falling asleep?"),
            ("decreased_work_performance", "Decreased work performance?"),
        ]
        return [
            InputMetadata(
                field_name=field,
                display_name=f"Q{i+1}: {description}",
                input_type=InputType.BOOLEAN,
                required=True,
                description=description,
                example="false",
                help_text="Yes/True = symptom present. No/False = symptom absent. Positive if libido OR erection issue OR >=3 other symptoms."
            )
            for i, (field, description) in enumerate(symptoms)
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = self.required_inputs
        for field in required:
            if field not in inputs or inputs[field] not in [True, False, 0, 1]:
                return False, f"{field} must be True/False"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        positive_count = sum([
            bool(inputs.get("decreased_libido")),
            bool(inputs.get("decreased_energy")),
            bool(inputs.get("decreased_strength")),
            bool(inputs.get("lost_height")),
            bool(inputs.get("decreased_enjoyment")),
            bool(inputs.get("sad_grumpy")),
            bool(inputs.get("erections_less_strong")),
            bool(inputs.get("sports_ability_decline")),
            bool(inputs.get("falling_asleep")),
            bool(inputs.get("decreased_work_performance"))
        ])

        # Positive if decreased libido OR erections less strong OR >= 3 other symptoms
        libido_issue = bool(inputs.get("decreased_libido"))
        erection_issue = bool(inputs.get("erections_less_strong"))
        other_symptoms = positive_count - int(libido_issue) - int(erection_issue)

        is_positive = libido_issue or erection_issue or (other_symptoms >= 3)

        if is_positive:
            result_text = "Positive for possible androgen deficiency"
            recommendation = "Consider serum testosterone measurement"
            risk_level = "Positive"
        else:
            result_text = "Negative for androgen deficiency"
            recommendation = "No immediate testosterone testing indicated"
            risk_level = "Negative"

        interpretation = f"{result_text}. Positive symptoms: {positive_count}/10. {recommendation}"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={"positive_symptoms": positive_count, "screen_positive": is_positive},
            interpretation=interpretation,
            risk_level=risk_level,
            references=self.references
        )
