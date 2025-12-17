"""Post-Void Residual (PVR) Assessment Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator, CalculatorCategory, CalculatorResult,
    InputMetadata, InputType,
)


class PVRUACalculator(ClinicalCalculator):
    """Post-Void Residual Assessment with clinical interpretation."""

    @property
    def name(self) -> str:
        return "Post-Void Residual Interpretation"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_VOIDING

    @property
    def description(self) -> str:
        return "Assess post-void residual volume and clinical significance"

    @property
    def references(self) -> List[str]:
        return ["Abrams P, et al. Standardisation of terminology of lower urinary tract function. Neurourol Urodyn. 2002;21:167-178"]

    @property
    def required_inputs(self) -> List[str]:
        return ["pvr_ml", "bladder_capacity"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get input schema for PVR/UA calculator."""
        return [
            InputMetadata("pvr_ml", "Post-Void Residual", InputType.NUMERIC, True, "Urine remaining after void", unit="mL", min_value=0, max_value=500, example="75", help_text="Normal: <50 mL. >100 mL suggests retention. Measured by ultrasound or catheterization."),
            InputMetadata("bladder_capacity", "Functional Bladder Capacity", InputType.NUMERIC, True, "Average voided volume", unit="mL", min_value=100, max_value=600, example="250", help_text="Normal: 200-400 mL. Calculated from diary or cystometry."),
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate PVR input."""
        required = ["pvr_ml", "bladder_capacity"]
        for field in required:
            if field not in inputs:
                return False, f"{field} is required"

        is_valid, msg = self._validate_range(inputs["pvr_ml"], min_val=0, max_val=2000, param_name="PVR volume")
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(inputs["bladder_capacity"], min_val=50, max_val=1000, param_name="bladder capacity")
        return is_valid, msg

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate PVR interpretation."""
        # Accept both parameter names
        pvr = float(inputs.get("pvr_ml") or inputs.get("post_void_residual", 0))
        bladder_capacity = float(inputs.get("bladder_capacity", 500))

        if pvr < 50:
            category, action = "Normal", "Reassurance, routine follow-up"
        elif pvr < 100:
            category, action = "Mildly elevated", "Monitor, repeat PVR in 3-6 months"
        elif pvr < 200:
            category, action = "Moderately elevated", "Consider intervention, assess etiology"
        elif pvr < 300:
            category, action = "Significantly elevated", "Intervention recommended"
        elif pvr < 500:
            category, action = "Severe retention", "Treatment necessary, consider catheterization"
        else:
            category, action = "Chronic retention", "Evaluate for neurogenic/obstructive cause"

        interpretation = f"PVR {pvr:.0f} mL: {category}. {action}."

        result = {
            "pvr_volume_mL": round(pvr, 0),
            "category": category,
            "recommendation": action,
        }

        recommendations = [action, "Repeat measurement to confirm if elevated", "Assess symptoms and etiology"]

        # Map category to risk_level
        if pvr < 50:
            risk_level = "Normal"
        elif pvr < 100:
            risk_level = "Borderline"
        elif pvr < 200:
            risk_level = "Abnormal"
        else:
            risk_level = "Severely Abnormal"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=recommendations,
            references=self.references,
        )
