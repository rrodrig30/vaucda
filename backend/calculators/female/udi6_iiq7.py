"""UDI-6/IIQ-7 Questionnaire Calculators."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class UDI6IIQ7Calculator(ClinicalCalculator):
    """Calculates UDI-6 and IIQ-7 incontinence symptom and impact scores."""

    @property
    def name(self) -> str:
        return "UDI-6 / IIQ-7 Questionnaires"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.FEMALE_UROLOGY

    @property
    def description(self) -> str:
        return "Assess urinary incontinence distress and quality of life impact"

    @property
    def references(self) -> List[str]:
        return ["Uebersax JS, et al. Short forms to assess life quality and symptom distress for urinary incontinence. Obstet Gynecol. 1995;89:989-996"]

    @property
    def required_inputs(self) -> List[str]:
        return [
            "udi6_q1", "udi6_q2", "udi6_q3", "udi6_q4", "udi6_q5", "udi6_q6",
            "iiq7_q1", "iiq7_q2", "iiq7_q3", "iiq7_q4", "iiq7_q5", "iiq7_q6", "iiq7_q7",
        ]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for UDI-6 / IIQ-7 Questionnaires calculator inputs."""
        schema = []

        # UDI-6 questions
        udi_questions = [
            ("udi6_q1", "Leaking urine involuntarily?"),
            ("udi6_q2", "Leaking urine during physical activity?"),
            ("udi6_q3", "Leaking before reaching toilet?"),
            ("udi6_q4", "Frequent strong urge to urinate?"),
            ("udi6_q5", "Frequent urination day and night?"),
            ("udi6_q6", "Leaking urine while sleeping?"),
        ]

        for field, description in udi_questions:
            schema.append(InputMetadata(
                field_name=field,
                display_name=f"UDI-6 {field[-2:]}: {description}",
                input_type=InputType.ENUM,
                required=True,
                description=description,
                allowed_values=[0, 1, 2, 3],
                example="1",
                help_text="0: Not at all. 1: Slightly. 2: Moderately. 3: Greatly."
            ))

        # IIQ-7 questions
        iiq_questions = [
            ("iiq7_q1", "Physical activity limitation?"),
            ("iiq7_q2", "Travel limitation?"),
            ("iiq7_q3", "Social/leisure activity limitation?"),
            ("iiq7_q4", "Emotional health impact?"),
            ("iiq7_q5", "Sexual function impact?"),
            ("iiq7_q6", "Relationship impact?"),
            ("iiq7_q7", "Overall quality of life impact?"),
        ]

        for field, description in iiq_questions:
            schema.append(InputMetadata(
                field_name=field,
                display_name=f"IIQ-7 {field[-2:]}: {description}",
                input_type=InputType.ENUM,
                required=True,
                description=description,
                allowed_values=[0, 1, 2, 3],
                example="1",
                help_text="0: Not at all. 1: Slightly. 2: Moderately. 3: Greatly."
            ))

        return schema

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        is_valid, msg = self._validate_required(inputs, self.required_inputs)
        if not is_valid:
            return False, msg

        for q in self.required_inputs:
            try:
                score = int(inputs[q])
                max_val = 3 if "udi6" in q else 3
                if score < 0 or score > max_val:
                    return False, f"{q} must be 0-{max_val}"
            except (ValueError, TypeError):
                return False, f"{q} must be an integer"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate UDI-6 and IIQ-7 scores."""

        udi6_sum = sum(int(inputs[f"udi6_q{i}"]) for i in range(1, 7))
        udi6_score = (udi6_sum / 18) * 100

        iiq7_sum = sum(int(inputs[f"iiq7_q{i}"]) for i in range(1, 8))
        iiq7_score = (iiq7_sum / 21) * 100

        result = {
            "udi6_raw_score": udi6_sum,
            "udi6_transformed_score": round(udi6_score, 1),
            "iiq7_raw_score": iiq7_sum,
            "iiq7_transformed_score": round(iiq7_score, 1),
        }

        interpretation = f"UDI-6 symptom distress: {udi6_score:.1f}/100 (higher = worse distress). IIQ-7 impact: {iiq7_score:.1f}/100 (higher = worse impact)."

        recommendations = ["Higher scores indicate greater symptom burden and quality of life impact", "Consider incontinence treatment options"]

        if udi6_score >= 60 or iiq7_score >= 60:
            severity = "High"
        elif udi6_score >= 30 or iiq7_score >= 30:
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
