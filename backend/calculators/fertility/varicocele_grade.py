from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class VaricoceleCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Varicocele Clinical Grading"
    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_FERTILITY
    @property
    def description(self) -> str:
        return "Grade varicocele severity"
    @property
    def references(self) -> List[str]:
        return ["Dubin L, Amelar RD. Varicocele. Fertil Steril. 1975;26:621-628"]
    @property
    def required_inputs(self) -> List[str]:
        return ["grade"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Varicocele Clinical Grading calculator inputs."""
        return [
            InputMetadata(
                field_name="grade",
                display_name="Varicocele Grade",
                input_type=InputType.ENUM,
                required=True,
                description="Severity of varicocele on physical examination",
                allowed_values=["Subclinical", "Grade I", "Grade II", "Grade III", 0, 1, 2, 3],
                example="Grade II",
                help_text="Subclinical/0: Only visible on Doppler/ultrasound. Grade I/1: Palpable with Valsalva only. Grade II/2: Palpable at rest. Grade III/3: Visibly prominent through skin."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        grade_val = inputs.get("grade", "")
        grade_map_str = {"Grade I": 1, "Grade II": 2, "Grade III": 3, "Subclinical": 0}

        try:
            if isinstance(grade_val, str) and grade_val in grade_map_str:
                grade = grade_map_str[grade_val]
            else:
                grade = int(grade_val)
                if grade < 0 or grade > 3:
                    return False, "Grade must be 0-3 or named grade"
        except:
            return False, "Invalid grade format"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        grade_val = inputs.get("grade", "")
        grade_map_str = {"Grade I": 1, "Grade II": 2, "Grade III": 3, "Subclinical": 0}

        if isinstance(grade_val, str) and grade_val in grade_map_str:
            grade = grade_map_str[grade_val]
        else:
            grade = int(grade_val)

        desc = {0: "Subclinical", 1: "Palpable with Valsalva", 2: "Palpable at rest", 3: "Visible through skin"}[grade]

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={"grade": grade, "description": desc},
            interpretation=f"Varicocele Grade {grade}: {desc}",
            risk_level="low" if grade <= 1 else "moderate" if grade == 2 else "high",
            recommendations=["Surgery if palpable with subfertility"],
            references=self.references
        )
