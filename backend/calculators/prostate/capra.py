"""
CAPRA Score Calculator (Cancer of the Prostate Risk Assessment).

Predicts biochemical recurrence-free survival following radical prostatectomy.
"""

from typing import Any, Dict, List, Optional, Tuple

from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class CAPRACalculator(ClinicalCalculator):
    """
    CAPRA Score Calculator.

    Scoring components (Cooperberg et al. 2005):
    1. PSA at diagnosis (0-3 points): <6=0, 6-10=1, 10.1-20=2, >20=3
    2. Gleason pattern (0-3 points): 3+3=0, 3+4=1, 4+3=2, 4+4/higher=3
    3. Clinical T stage (0-2 points): T1-T2a=0, T2b-c=1, T3a-b=2
    4. Percent positive cores (0-1 points): <34%=0, ≥34%=1

    Total: 0-9 points (max achievable)
    Risk groups: Low (0-2), Intermediate (3-5), High (6-10)
    """

    @property
    def name(self) -> str:
        return "CAPRA Score"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.PROSTATE_CANCER

    @property
    def description(self) -> str:
        return "Predict biochemical recurrence-free survival after radical prostatectomy"

    @property
    def references(self) -> List[str]:
        return [
            "Cooperberg MR, et al. Cancer 2006;107:2276-2283",
            "UCSF Urologic Oncology Program",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["psa", "gleason_primary", "gleason_secondary", "t_stage", "percent_positive_cores"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for CAPRA Score calculator inputs."""
        return [
            InputMetadata(
                field_name="psa",
                display_name="PSA",
                input_type=InputType.NUMERIC,
                required=True,
                description="Prostate-Specific Antigen level at diagnosis",
                unit="ng/mL",
                min_value=0.0,
                max_value=500.0,
                example="6.5",
                help_text="Normal range: 0-4 ng/mL. PSA >10 suggests higher risk."
            ),
            InputMetadata(
                field_name="gleason_primary",
                display_name="Gleason Primary Score",
                input_type=InputType.ENUM,
                required=True,
                description="Primary (most common) Gleason grade pattern",
                allowed_values=[1, 2, 3, 4, 5],
                example="3",
                help_text="Most common pattern. Grade 1 (well differentiated) to 5 (poorly differentiated)."
            ),
            InputMetadata(
                field_name="gleason_secondary",
                display_name="Gleason Secondary Score",
                input_type=InputType.ENUM,
                required=True,
                description="Secondary (second most common) Gleason grade pattern",
                allowed_values=[1, 2, 3, 4, 5],
                example="4",
                help_text="Second most common pattern. Combined with primary to form Gleason sum."
            ),
            InputMetadata(
                field_name="t_stage",
                display_name="Clinical T Stage",
                input_type=InputType.ENUM,
                required=True,
                description="Clinical tumor stage based on DRE and imaging",
                allowed_values=["T1a", "T1b", "T1c", "T2a", "T2b", "T2c", "T3a", "T3b"],
                example="T2a",
                help_text="T1: Non-palpable, T2: Confined to prostate, T3: Extraprostatic extension"
            ),
            InputMetadata(
                field_name="percent_positive_cores",
                display_name="Percent Positive Biopsy Cores",
                input_type=InputType.NUMERIC,
                required=True,
                description="Percentage of biopsy cores positive for cancer",
                unit="%",
                min_value=0.0,
                max_value=100.0,
                example="40",
                help_text="Calculate as (positive cores / total cores) × 100. ≥34% indicates higher risk."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate CAPRA inputs."""

        # Check required fields
        valid, msg = self._validate_required(inputs, self.required_inputs)
        if not valid:
            return False, msg

        # Validate PSA
        valid, msg = self._validate_range(
            inputs["psa"],
            min_val=0,
            max_val=500,
            param_name="psa"
        )
        if not valid:
            return False, msg

        # Validate Gleason scores
        for score_type in ["gleason_primary", "gleason_secondary"]:
            valid, msg = self._validate_enum(
                inputs[score_type],
                [1, 2, 3, 4, 5],
                param_name=score_type
            )
            if not valid:
                return False, msg

        # Validate T stage
        valid, msg = self._validate_enum(
            inputs["t_stage"],
            ["T1a", "T1b", "T1c", "T2a", "T2b", "T2c", "T3a", "T3b"],
            param_name="t_stage"
        )
        if not valid:
            return False, msg

        # Validate percent positive cores
        valid, msg = self._validate_range(
            inputs["percent_positive_cores"],
            min_val=0,
            max_val=100,
            param_name="percent_positive_cores"
        )
        if not valid:
            return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate CAPRA score."""

        total_score = 0
        breakdown = {}

        # 1. PSA at diagnosis (ng/mL)
        # Per Cooperberg et al. 2005: <6=0, 6-10=1, 10.1-20=2, >20=3
        psa = inputs["psa"]
        if psa < 6:
            psa_points = 0
        elif psa <= 10:
            psa_points = 1
        elif psa <= 20:
            psa_points = 2
        else:  # >20
            psa_points = 3

        total_score += psa_points
        breakdown["PSA"] = {"value": psa, "points": psa_points}

        # 2. Gleason pattern
        # Per Cooperberg et al. 2005: 3+3=0, 3+4=1, 4+3=2, 4+4/4+5/5+4/5+5=3
        primary = inputs["gleason_primary"]
        secondary = inputs["gleason_secondary"]

        if primary == 3 and secondary == 3:
            gleason_points = 0
        elif primary == 3 and secondary >= 4:
            gleason_points = 1
        elif primary >= 4 and secondary == 3:
            gleason_points = 2
        elif primary >= 4 and secondary >= 4:
            gleason_points = 3
        else:
            gleason_points = 0  # Default for unusual patterns

        total_score += gleason_points
        breakdown["Gleason"] = {
            "primary": primary,
            "secondary": secondary,
            "points": gleason_points
        }

        # 3. Clinical T stage
        t_stage = inputs["t_stage"]
        if t_stage in ["T1a", "T1b", "T1c", "T2a"]:
            t_points = 0
        elif t_stage in ["T2b", "T2c"]:
            t_points = 1
        else:  # T3a, T3b
            t_points = 2

        total_score += t_points
        breakdown["T_stage"] = {"value": t_stage, "points": t_points}

        # 4. Percent positive biopsy cores
        percent_positive = inputs["percent_positive_cores"]
        if percent_positive < 34:
            cores_points = 0
        else:
            cores_points = 1

        total_score += cores_points
        breakdown["Positive_cores"] = {"value": f"{percent_positive}%", "points": cores_points}

        # Determine risk category and prognosis
        if total_score <= 2:
            category = "Low Risk"
            three_year_rfs = 91
            five_year_rfs = 85
            ten_year_rfs = 75
        elif total_score <= 5:
            category = "Intermediate Risk"
            three_year_rfs = 75
            five_year_rfs = 65
            ten_year_rfs = 50
        else:  # 6-10
            category = "High Risk"
            three_year_rfs = 53
            five_year_rfs = 40
            ten_year_rfs = 25

        # Build interpretation
        interpretation = (
            f"CAPRA Score: {total_score}/10 ({category}). "
            f"Estimated recurrence-free survival: 3-year {three_year_rfs}%, "
            f"5-year {five_year_rfs}%, 10-year {ten_year_rfs}%."
        )

        # Build recommendations
        recommendations = []
        if total_score <= 2:
            recommendations.append("Excellent prognosis after surgery")
            recommendations.append("Standard follow-up protocol appropriate")
        elif total_score <= 5:
            recommendations.append("Consider adjuvant therapy discussion")
            recommendations.append("Close follow-up recommended")
        else:
            recommendations.append("High risk for biochemical recurrence")
            recommendations.append("Consider multimodal therapy")
            recommendations.append("Enrollment in clinical trials if available")

        result = {
            "total_score": total_score,
            "category": category,
            "breakdown": breakdown,
            "prognosis": {
                "3_year_rfs": f"{three_year_rfs}%",
                "5_year_rfs": f"{five_year_rfs}%",
                "10_year_rfs": f"{ten_year_rfs}%",
            }
        }

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            category=category,
            risk_level=category,
            recommendations=recommendations,
            references=self.references,
        )
