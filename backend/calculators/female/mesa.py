"""Microsurgical Epididymal Sperm Aspiration (MESA) Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class MESACalculator(ClinicalCalculator):
    """MESA success prediction calculator."""

    @property
    def name(self) -> str:
        return "MESA Success Predictor"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.FEMALE_UROLOGY

    @property
    def description(self) -> str:
        return "Predict success of microsurgical epididymal sperm aspiration"

    @property
    def references(self) -> List[str]:
        return [
            "Silber SJ. Microsurgical TESE and MESA. Hum Reprod Update. 2000;6(4):377-378"
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["obstruction_type", "previous_attempts", "testicular_volume"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for MESA Success Predictor calculator inputs."""
        return [
            InputMetadata(
                field_name="obstruction_type",
                display_name="Type of Obstruction",
                input_type=InputType.ENUM,
                required=True,
                description="Cause of male factor infertility",
                allowed_values=["congenital", "post_vasectomy", "post_infection", "idiopathic"],
                example="post_vasectomy",
                help_text="Congenital: CBAVD. Post-vasectomy: reversal candidate. Post-infection: infectious etiology. Idiopathic: unknown cause."
            ),
            InputMetadata(
                field_name="previous_attempts",
                display_name="Previous MESA Attempts",
                input_type=InputType.NUMERIC,
                required=True,
                description="Number of prior MESA procedures",
                unit="count",
                min_value=0,
                max_value=10,
                example="0",
                help_text="Each failed attempt reduces success rate. First attempt has highest success probability."
            ),
            InputMetadata(
                field_name="testicular_volume",
                display_name="Testicular Volume",
                input_type=InputType.NUMERIC,
                required=True,
                description="Testicular volume by ultrasound",
                unit="mL",
                min_value=0.5,
                max_value=30,
                example="18",
                help_text="Normal testicular volume: 15-25 mL. Smaller volume (<10 mL) reduces MESA success."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if "obstruction_type" not in inputs:
            return False, "Obstruction type required"
        if "previous_attempts" not in inputs or inputs["previous_attempts"] < 0:
            return False, "Previous attempts must be >= 0"
        if "testicular_volume" not in inputs or inputs["testicular_volume"] <= 0:
            return False, "Testicular volume must be positive"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        obstruction_type = inputs["obstruction_type"]
        previous_attempts = inputs["previous_attempts"]
        testicular_volume = inputs["testicular_volume"]

        # Success rates based on obstruction type
        base_success = {
            "congenital": 95,
            "post_vasectomy": 90,
            "post_infection": 75,
            "idiopathic": 60
        }.get(obstruction_type, 50)

        # Adjust for previous attempts
        success_rate = base_success - (previous_attempts * 5)

        # Adjust for testicular volume
        if testicular_volume < 10:
            success_rate -= 10
        elif testicular_volume < 15:
            success_rate -= 5

        success_rate = max(10, min(95, success_rate))

        if success_rate >= 80:
            prognosis = "Excellent"
        elif success_rate >= 60:
            prognosis = "Good"
        elif success_rate >= 40:
            prognosis = "Fair"
        else:
            prognosis = "Poor"

        interpretation = f"Estimated MESA success rate: {success_rate}%. Prognosis: {prognosis}"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={"success_rate": success_rate, "prognosis": prognosis},
            interpretation=interpretation,
            risk_level=prognosis,
            references=self.references
        )
