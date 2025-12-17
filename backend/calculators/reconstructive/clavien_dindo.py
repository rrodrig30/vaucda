from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class ClavienDindoCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Clavien-Dindo Complication Classification"
    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.RECONSTRUCTIVE
    @property
    def description(self) -> str:
        return "Classify surgical complications"
    @property
    def references(self) -> List[str]:
        return ["Dindo D, et al. Classification of surgical complications. Ann Surg. 2004;240:205-213"]
    @property
    def required_inputs(self) -> List[str]:
        return ["grade"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Clavien-Dindo Classification calculator inputs."""
        return [
            InputMetadata(
                field_name="grade",
                display_name="Clavien-Dindo Grade",
                input_type=InputType.ENUM,
                required=True,
                description="Severity grade of surgical complication",
                allowed_values=["I", "II", "IIIa", "IIIb", "IVa", "IVb", "V"],
                example="II",
                help_text="Grade I: Minor deviation from normal. Grade II: Pharmacological intervention. Grade III: Surgical intervention. Grade IV: Organ failure. Grade V: Death. More detailed classification: a=without, b=with re-operation."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        grade_val = inputs.get("grade") or inputs.get("complication_grade", "")
        grade_map = {"I": 1, "II": 2, "IIIa": 3, "IIIb": 3, "IVa": 4, "IVb": 4, "V": 5}

        try:
            if grade_val in grade_map:
                return True, None
            else:
                grade = int(grade_val)
                if grade < 1 or grade > 5:
                    return False, "Grade must be 1-5 or I-V"
                return True, None
        except:
            return False, "Invalid grade format"

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        grade_val = inputs.get("grade") or inputs.get("complication_grade", "")
        grade_map = {"I": 1, "II": 2, "IIIa": 3, "IIIb": 3, "IVa": 4, "IVb": 4, "V": 5}

        if grade_val in grade_map:
            grade = grade_map[grade_val]
        else:
            grade = int(grade_val)

        descriptions = {
            1: "Minor deviation from normal postoperative course",
            2: "Requires pharmacological management",
            3: "Requires intervention",
            4: "Organ failure",
            5: "Death"
        }

        description = descriptions.get(grade, "Unknown")

        interpretation = f"Clavien-Dindo Grade {grade_val}: {description}"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={"grade": grade, "grade_roman": grade_val, "description": description},
            interpretation=interpretation,
            risk_level=grade,  # Return numeric risk level (1-5)
            references=self.references
        )
