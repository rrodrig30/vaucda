"""Bladder Diary Analysis Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator, CalculatorCategory, CalculatorResult,
    InputMetadata, InputType,
)


class BladderDiaryCalculator(ClinicalCalculator):
    """Analyzes bladder diary parameters."""

    @property
    def name(self) -> str:
        return "Bladder Diary Analysis"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_VOIDING

    @property
    def description(self) -> str:
        return "Analyze bladder diary for polyuria, nocturia, and functional capacity"

    @property
    def references(self) -> List[str]:
        return ["Abrams P, et al. Standardisation of terminology. Neurourol Urodyn. 2002;21:167-178"]

    @property
    def required_inputs(self) -> List[str]:
        return ["daytime_voids", "nocturnal_voids", "mean_voided_volume", "max_voided_volume", "total_24hr_volume"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get input schema for Bladder Diary Analysis."""
        return [
            InputMetadata("daytime_voids", "Daytime Frequency", InputType.NUMERIC, True, "Daytime voids", unit="voids", min_value=1, max_value=20, example="7", help_text="Normal: 5-8 voids/day. >8 = frequency."),
            InputMetadata("nocturnal_voids", "Nocturnal Frequency", InputType.NUMERIC, True, "Nighttime voids", unit="voids", min_value=0, max_value=10, example="1", help_text="Normal: 0-2. >2 = nocturia."),
            InputMetadata("mean_voided_volume", "Mean Voided Volume", InputType.NUMERIC, True, "Average void volume", unit="mL", min_value=50, max_value=500, example="250", help_text="Normal 200-300 mL."),
            InputMetadata("max_voided_volume", "Maximum Voided Volume", InputType.NUMERIC, True, "Largest void", unit="mL", min_value=100, max_value=800, example="400", help_text="Functional bladder capacity."),
            InputMetadata("total_24hr_volume", "24-Hour Urine Output", InputType.NUMERIC, True, "Total daily urine volume", unit="mL", min_value=400, max_value=4000, example="1800", help_text="Normal: 1500-2000 mL. >2500 = polyuria."),
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        is_valid, msg = self._validate_required(inputs, self.required_inputs)
        if not is_valid:
            return False, msg

        for param in ["daytime_voids", "nocturnal_voids"]:
            try:
                if int(inputs[param]) < 0:
                    return False, f"{param} cannot be negative"
            except (ValueError, TypeError):
                return False, f"{param} must be an integer"

        for param in ["mean_voided_volume", "max_voided_volume", "total_24hr_volume"]:
            is_valid, msg = self._validate_range(inputs[param], min_val=0, max_val=5000, param_name=param)
            if not is_valid:
                return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate bladder diary metrics."""

        day_voids = int(inputs["daytime_voids"])
        night_voids = int(inputs["nocturnal_voids"])
        mean_vol = float(inputs["mean_voided_volume"])
        max_vol = float(inputs["max_voided_volume"])
        total_vol = float(inputs["total_24hr_volume"])

        findings = []

        # Daytime frequency
        if day_voids > 8:
            findings.append(f"Daytime frequency elevated ({day_voids} voids vs normal 4-7)")

        # Nocturia
        if night_voids >= 2:
            findings.append(f"Nocturia present ({night_voids} voids)")

        # Polyuria
        polyuria_index = (float(night_voids) / (day_voids + night_voids)) * 100 if (day_voids + night_voids) > 0 else 0

        if total_vol > 3000:
            findings.append(f"24-hr polyuria ({total_vol:.0f} mL - normal 1.5-2.5 L)")

        if polyuria_index > 33:
            findings.append(f"Nocturnal polyuria ({polyuria_index:.0f}% of output at night)")

        # Functional capacity
        fbc = max_vol
        if fbc < 300:
            findings.append(f"Reduced functional bladder capacity ({fbc:.0f} mL vs normal 400-600 mL)")

        interpretation = "; ".join(findings) if findings else "Bladder diary parameters within normal limits"

        result = {
            "daytime_frequency": day_voids,
            "nocturnal_frequency": night_voids,
            "mean_voided_volume_mL": round(mean_vol, 0),
            "functional_bladder_capacity_mL": round(fbc, 0),
            "total_24hr_volume_mL": round(total_vol, 0),
            "nocturnal_polyuria_index": round(polyuria_index, 1),
        }

        recommendations = ["Evaluate for nocturnal polyuria if present", "Consider fluid management counseling if polyuria"]

        # Determine risk_level based on number of abnormal findings
        if len(findings) == 0:
            risk_level = "Normal"
        elif len(findings) <= 2:
            risk_level = "Borderline"
        else:
            risk_level = "Abnormal"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=recommendations,
            references=self.references,
        )
