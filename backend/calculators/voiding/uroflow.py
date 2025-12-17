"""
Uroflowmetry Pattern Analysis Calculator.

Analyzes uroflow parameters and identifies flow pattern abnormalities
suggesting obstruction, detrusor dysfunction, or other voiding disorders.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class UroflowCalculator(ClinicalCalculator):
    """
    Uroflowmetry Pattern Analysis Calculator.

    Analyzes:
    - Qmax (maximum flow rate)
    - Qave (average flow rate)
    - Voided volume
    - Flow time and time to Qmax
    - Flow curve pattern
    """

    @property
    def name(self) -> str:
        return "Uroflow Pattern Analysis"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_VOIDING

    @property
    def description(self) -> str:
        return "Analyze uroflowmetry patterns to identify voiding dysfunction"

    @property
    def references(self) -> List[str]:
        return [
            "Siroky MB. Urodynamics. Urology. 2001;58:139-151",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return [
            "qmax",
            "qave",
            "voided_volume",
            "flow_pattern",
        ]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get input schema for Uroflowmetry calculator."""
        return [
            InputMetadata("qmax", "Maximum Flow Rate (Qmax)", InputType.NUMERIC, True, "Peak urinary flow", unit="mL/s", min_value=1, max_value=50, example="18", help_text="Normal >15 mL/s (men) or >20 mL/s (women). <10 suggests obstruction or weak detrusor."),
            InputMetadata("qave", "Average Flow Rate (Qave)", InputType.NUMERIC, True, "Mean urinary flow", unit="mL/s", min_value=1, max_value=40, example="10", help_text="Qave = voided volume / flow time. Normal 8-15 mL/s."),
            InputMetadata("voided_volume", "Voided Volume", InputType.NUMERIC, True, "Total urine voided", unit="mL", min_value=100, max_value=600, example="300", help_text="Optimal 200-400 mL. <150 may be unreliable."),
            InputMetadata("flow_pattern", "Flow Pattern Type", InputType.ENUM, True, "Shape of flow curve", allowed_values=["normal", "plateau", "interrupted", "fractionated", "reduced"], example="normal", help_text="Normal: smooth peak. Plateau: sustained. Interrupted: obstruction. Fractionated: instability."),
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate uroflow inputs."""

        is_valid, msg = self._validate_required(
            inputs,
            [
                "qmax",
                "qave",
                "voided_volume",
                "flow_pattern",
            ]
        )
        if not is_valid:
            return False, msg

        # Validate numeric ranges
        is_valid, msg = self._validate_range(
            inputs["qmax"], min_val=1, max_val=50, param_name="qmax"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["qave"], min_val=0.5, max_val=40, param_name="qave"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["voided_volume"],
            min_val=50,
            max_val=1000,
            param_name="voided_volume"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["flow_time"],
            min_val=1,
            max_val=120,
            param_name="flow_time"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["time_to_qmax"],
            min_val=0.5,
            max_val=60,
            param_name="time_to_qmax"
        )
        if not is_valid:
            return False, msg

        # Validate pattern
        valid_patterns = ["bell_shaped", "plateau", "intermittent", "superflow", "tower", "other"]
        is_valid, msg = self._validate_enum(
            inputs["flow_pattern"],
            valid_patterns,
            "flow_pattern"
        )
        if not is_valid:
            return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate uroflow analysis."""

        # Accept alternative parameter names
        qmax = float(inputs.get("qmax") or inputs.get("flow_rate", 0))
        qave = float(inputs.get("qave", 10))
        voided_volume = float(inputs.get("voided_volume") or inputs.get("void_volume", 0))
        flow_time = float(inputs.get("flow_time", 0))
        time_to_qmax = float(inputs.get("time_to_qmax", 0))
        flow_pattern = inputs.get("flow_pattern", "normal")

        # Calculate derived parameters
        if flow_time > 0 and time_to_qmax > 0:
            time_to_qmax_percent = (time_to_qmax / flow_time) * 100
        else:
            time_to_qmax_percent = 0

        # Assess parameters
        interpretations = []

        # Qmax assessment
        if qmax < 10:
            qmax_status = "Severely reduced"
            interpretations.append("Qmax < 10 mL/s suggests severe obstruction or weak detrusor")
        elif qmax < 15:
            qmax_status = "Reduced"
            interpretations.append("Qmax 10-15 mL/s suggests possible obstruction")
        else:
            qmax_status = "Normal"
            interpretations.append("Qmax > 15 mL/s is within normal range")

        # Flow time assessment
        if flow_time > 20:
            interpretations.append(f"Prolonged flow time ({flow_time:.0f} sec) suggests obstruction or weak detrusor")
        else:
            interpretations.append("Flow time is normal")

        # Time to Qmax assessment
        if time_to_qmax_percent > 33:
            interpretations.append(
                "Delayed time to Qmax suggests gradual pressure rise (obstruction pattern)"
            )

        # Flow pattern interpretation
        pattern_interpretations = {
            "bell_shaped": "Normal bell-shaped curve",
            "plateau": "Plateau pattern suggests obstruction or stricture",
            "intermittent": "Intermittent pattern suggests abdominal straining or detrusor underactivity",
            "superflow": "Superflow (high Qmax with low volume) suggests low outlet resistance",
            "tower": "Tower pattern may suggest straining or neurogenic bladder",
            "other": "Non-standard pattern",
        }
        interpretations.append(f"Flow Pattern: {pattern_interpretations.get(flow_pattern, 'Unknown')}")

        # Overall assessment
        obstruction_score = 0
        if qmax < 15:
            obstruction_score += 1
        if flow_time > 20:
            obstruction_score += 1
        if time_to_qmax_percent > 33:
            obstruction_score += 1
        if flow_pattern in ["plateau", "tower"]:
            obstruction_score += 1

        if obstruction_score >= 3:
            overall_pattern = "Pattern suggestive of obstruction"
            recommendation = "Consider urodynamic testing or imaging"
        elif obstruction_score >= 1:
            overall_pattern = "Pattern possibly suggestive of obstruction"
            recommendation = "Close clinical correlation; may need further evaluation"
        elif flow_pattern == "intermittent":
            overall_pattern = "Pattern suggestive of detrusor dysfunction or straining"
            recommendation = "Evaluate for abdominal straining or weak detrusor"
        else:
            overall_pattern = "Normal voiding pattern"
            recommendation = "No evidence of obstruction on uroflow"

        interpretations.append(f"Overall Assessment: {overall_pattern}")

        # Build result
        interpretation_text = "\n".join(interpretations)

        result = {
            "qmax_mL_s": round(qmax, 1),
            "qave_mL_s": round(qave, 1),
            "voided_volume_mL": round(voided_volume, 0),
            "flow_time_sec": round(flow_time, 1),
            "time_to_qmax_sec": round(time_to_qmax, 1),
            "time_to_qmax_percent": round(time_to_qmax_percent, 1),
            "flow_pattern": flow_pattern,
            "overall_pattern": overall_pattern,
        }

        recommendations = [
            recommendation,
            "Valid study requires voided volume > 150 mL",
            "Repeat uroflow if voided volume marginal",
        ]

        # Determine risk_level based on obstruction score
        if obstruction_score >= 3:
            risk_level = "Abnormal"
        elif obstruction_score >= 1:
            risk_level = "Borderline"
        else:
            risk_level = "Normal"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation_text,
            risk_level=risk_level,
            recommendations=recommendations,
            references=self.references,
        )
