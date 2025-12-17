from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class StoneSizeCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Stone Size Calculator"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.STONES

    @property
    def description(self) -> str:
        return "Calculate stone size from ultrasound or CT measurements"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def references(self) -> List[str]:
        return ["Pearle MS, et al. Urolithiasis: 2014 AUA Guidelines. J Urol. 2015;193(1):54-61"]

    @property
    def required_inputs(self) -> List[str]:
        return ["length_mm", "width_mm", "height_mm"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Stone Size Calculator inputs."""
        return [
            InputMetadata(
                field_name="length_mm",
                display_name="Stone Length",
                input_type=InputType.NUMERIC,
                required=True,
                description="Stone dimension in one axis (typically longest)",
                unit="mm",
                min_value=0.1,
                max_value=100,
                example="25",
                help_text="Measured on imaging. Longest dimension of stone. Used with width/height to define size."
            ),
            InputMetadata(
                field_name="width_mm",
                display_name="Stone Width",
                input_type=InputType.NUMERIC,
                required=True,
                description="Stone dimension in transverse axis",
                unit="mm",
                min_value=0.1,
                max_value=100,
                example="20",
                help_text="Measured perpendicular to length. Intermediate dimension. All three dimensions define 3D volume."
            ),
            InputMetadata(
                field_name="height_mm",
                display_name="Stone Height",
                input_type=InputType.NUMERIC,
                required=True,
                description="Stone dimension in third axis (anterior-posterior if in kidney)",
                unit="mm",
                min_value=0.1,
                max_value=100,
                example="18",
                help_text="Measured in perpendicular direction. Smallest or medium dimension typically. Maximum of three determines size category."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = ["length_mm", "width_mm", "height_mm"]
        for key in required:
            if key not in inputs:
                return False, f"Missing required input: {key}"

        try:
            for key in required:
                val = float(inputs.get(key, 0))
                if val <= 0 or val > 100:
                    return False, f"{key} must be between 0.1 and 100 mm"
        except (ValueError, TypeError):
            return False, "Invalid numeric inputs"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        length_mm = float(inputs.get("length_mm", 0))
        width_mm = float(inputs.get("width_mm", 0))
        height_mm = float(inputs.get("height_mm", 0))

        # Maximum diameter is the largest dimension
        max_diameter = max(length_mm, width_mm, height_mm)

        # Categorize by size
        if max_diameter < 5:
            category = "Small"
            management = "Expectant management, hydration, pain control"
            risk_level = "low"
        elif max_diameter < 10:
            category = "Medium"
            management = "Conservative or minimal invasive treatment"
            risk_level = "moderate"
        else:
            category = "Large"
            management = "Intervention recommended (PCNL or other)"
            risk_level = "high"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                'max_diameter_mm': round(max_diameter, 1),
                'category': category,
                'management': management
            },
            interpretation=f"Maximum stone diameter: {max_diameter:.1f} mm ({category})",
            risk_level=risk_level,
            references=self.references
        )
