from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class GuyScoreCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Guy's Stone Score (PCNL)"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.STONES

    @property
    def description(self) -> str:
        return "Predict PCNL outcomes based on stone complexity"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def references(self) -> List[str]:
        return ["Thomas K, et al. Guy's Stone Score. Eur Urol. 2011;59:784-796"]

    @property
    def required_inputs(self) -> List[str]:
        return ["location", "size_cm", "number", "anatomy"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Guy's Stone Score calculator inputs."""
        return [
            InputMetadata(
                field_name="location",
                display_name="Stone Location",
                input_type=InputType.ENUM,
                required=True,
                description="Anatomic location of stone within the collecting system",
                allowed_values=["renal_pelvis", "upper_calyx", "middle_calyx", "lower_calyx"],
                example="renal_pelvis",
                help_text="Renal pelvis/upper calyx: Better access for PCNL. Lower calyx: More difficult access, lower success rates."
            ),
            InputMetadata(
                field_name="size_cm",
                display_name="Stone Size (Maximum Diameter)",
                input_type=InputType.NUMERIC,
                required=True,
                description="Largest dimension of stone",
                unit="cm",
                min_value=0.1,
                max_value=10,
                example="2.5",
                help_text="Small <1 cm: Easy PCNL. Medium 1-3 cm: Routine. Large >3 cm: Complex procedure, higher morbidity."
            ),
            InputMetadata(
                field_name="number",
                display_name="Number of Stones",
                input_type=InputType.NUMERIC,
                required=True,
                description="Count of renal calculi",
                unit="stones",
                min_value=1,
                max_value=20,
                example="2",
                help_text="Single stone: Best prognosis. Multiple stones: More time, more punctures, higher morbidity."
            ),
            InputMetadata(
                field_name="anatomy",
                display_name="Renal Anatomy",
                input_type=InputType.ENUM,
                required=True,
                description="Presence of anatomic abnormalities",
                allowed_values=["normal", "abnormal"],
                example="normal",
                help_text="Normal anatomy: Easier PCNL. Abnormality (UPJO, calyceal diverticulum, duplicated system, etc): Increased difficulty."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = ["location", "size_cm", "number", "anatomy"]
        for key in required:
            if key not in inputs:
                return False, f"Missing required input: {key}"

        try:
            float(inputs.get("size_cm", 0))
            int(inputs.get("number", 0))
        except (ValueError, TypeError):
            return False, "Invalid numeric inputs"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        # Score based on stone characteristics
        size_cm = float(inputs.get("size_cm", 0))
        number = int(inputs.get("number", 0))
        location = inputs.get("location", "")
        anatomy = inputs.get("anatomy", "")

        score = 0

        # Size points (0-3)
        if size_cm < 1:
            score += 1
        elif size_cm < 2:
            score += 1
        elif size_cm < 3:
            score += 2
        else:
            score += 3

        # Number of stones (0-2)
        if number <= 2:
            score += 1
        else:
            score += 2

        # Location points
        if location in ["upper_calyx", "renal_pelvis"]:
            score += 1
        elif location in ["middle_calyx", "lower_calyx"]:
            score += 2
        else:
            score += 1

        # Anatomy (normal adds 0, abnormal adds 1)
        if anatomy == "normal":
            score += 0
        else:
            score += 1

        # Determine grade and success rate
        if score <= 3:
            grade = "Grade I"
            success_rate = "90%+"
            risk_level = "low"
        elif score <= 5:
            grade = "Grade II"
            success_rate = "70-90%"
            risk_level = "moderate"
        elif score <= 7:
            grade = "Grade III"
            success_rate = "50-70%"
            risk_level = "high"
        else:
            grade = "Grade IV"
            success_rate = "<50%"
            risk_level = "high"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                'score': score,
                'grade': grade,
                'success_rate': success_rate
            },
            interpretation=f"{grade}: {success_rate} stone-free rate",
            risk_level=risk_level,
            references=self.references
        )
