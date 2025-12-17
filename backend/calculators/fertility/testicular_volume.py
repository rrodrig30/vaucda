from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class TesticularVolumeCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Testicular Volume Calculator"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_FERTILITY

    @property
    def description(self) -> str:
        return "Calculate testicular volume from ultrasound measurements using ellipsoid formula"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def references(self) -> List[str]:
        return ["Nieschlag E, Behre HM. Andrology. Heidelberg: Springer; 2010"]

    @property
    def required_inputs(self) -> List[str]:
        return ["length_cm", "width_cm", "height_cm"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Testicular Volume Calculator inputs."""
        return [
            InputMetadata(
                field_name="length_cm",
                display_name="Testicular Length",
                input_type=InputType.NUMERIC,
                required=True,
                description="Length of testis on ultrasound (longest dimension)",
                unit="cm",
                min_value=0.1,
                max_value=10,
                example="4.5",
                help_text="Measured on ultrasound in longitudinal axis. Normal: 4-5 cm."
            ),
            InputMetadata(
                field_name="width_cm",
                display_name="Testicular Width",
                input_type=InputType.NUMERIC,
                required=True,
                description="Width of testis on ultrasound",
                unit="cm",
                min_value=0.1,
                max_value=10,
                example="2.8",
                help_text="Measured on ultrasound in transverse axis. Normal: 2.5-3.5 cm."
            ),
            InputMetadata(
                field_name="height_cm",
                display_name="Testicular Height",
                input_type=InputType.NUMERIC,
                required=True,
                description="Anteroposterior dimension of testis",
                unit="cm",
                min_value=0.1,
                max_value=10,
                example="2.5",
                help_text="Anteroposterior dimension on ultrasound. Normal: 2.5-3 cm."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        try:
            for key in ["length_cm", "width_cm", "height_cm"]:
                val = float(inputs.get(key, 0))
                if val <= 0 or val > 10:
                    return False, f"{key} must be between 0.1 and 10 cm"
            return True, None
        except (ValueError, TypeError):
            return False, "Invalid input values"

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        l = float(inputs["length_cm"])
        w = float(inputs["width_cm"])
        h = float(inputs["height_cm"])

        # Volume using ellipsoid formula: V = 0.52 × L × W × H
        volume_ml = l * w * h * 0.52

        # Categorize based on volume
        if volume_ml >= 15:
            category = "Normal"
            risk_level = "low"
        elif volume_ml >= 10:
            category = "Mild atrophy"
            risk_level = "moderate"
        else:
            category = "Moderate atrophy"
            risk_level = "high"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                'volume_ml': round(volume_ml, 1),
                'category': category
            },
            interpretation=f"Volume {volume_ml:.1f} mL: {category}",
            risk_level=risk_level,
            references=self.references
        )
