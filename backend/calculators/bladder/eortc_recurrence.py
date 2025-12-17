"""
EORTC Recurrence Score Calculator for NMIBC.

Predicts 1-year and 5-year recurrence probability for non-muscle invasive
bladder cancer based on clinical and pathological factors.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class EORTCRecurrenceCalculator(ClinicalCalculator):
    """
    EORTC Recurrence Score Calculator.

    Calculates recurrence risk (0-17 points) based on:
    - Number of tumors
    - Tumor diameter
    - Prior recurrence rate
    - T category
    - Concurrent CIS
    - Grade (WHO 1973)
    """

    @property
    def name(self) -> str:
        return "EORTC Recurrence Score"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.BLADDER_CANCER

    @property
    def description(self) -> str:
        return "Predict recurrence risk in non-muscle invasive bladder cancer"

    @property
    def references(self) -> List[str]:
        return [
            "Sylvester RJ, et al. Predicting recurrence and progression in individual patients with stage Ta, T1 bladder cancer. J Urol. 2006;175:2090-2095",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return [
            "number_of_tumors",
            "tumor_diameter_cm",
            "prior_recurrence_rate",
            "t_category",
            "concurrent_cis",
            "grade",
        ]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for EORTC Recurrence Score calculator inputs."""
        return [
            InputMetadata(
                field_name="number_of_tumors",
                display_name="Number of Tumors",
                input_type=InputType.NUMERIC,
                required=True,
                description="Total number of bladder tumors",
                unit="count",
                min_value=1,
                max_value=50,
                example="2",
                help_text="Count all tumors present. Multiple tumors increase recurrence risk."
            ),
            InputMetadata(
                field_name="tumor_diameter_cm",
                display_name="Tumor Diameter",
                input_type=InputType.NUMERIC,
                required=True,
                description="Size of the largest tumor",
                unit="cm",
                min_value=0.1,
                max_value=10,
                example="2.5",
                help_text="Measure largest tumor dimension. Diameter >=3 cm increases recurrence risk."
            ),
            InputMetadata(
                field_name="prior_recurrence_rate",
                display_name="Prior Recurrence Rate",
                input_type=InputType.ENUM,
                required=True,
                description="Patient's history of recurrence",
                allowed_values=["primary", "less_than_1_per_year", "more_than_1_per_year"],
                example="primary",
                help_text="Primary: first occurrence. <1/year: low recurrence history. >1/year: frequent recurrences indicating aggressive disease."
            ),
            InputMetadata(
                field_name="t_category",
                display_name="Tumor Category",
                input_type=InputType.ENUM,
                required=True,
                description="TNM stage of bladder tumor",
                allowed_values=["Ta", "T1"],
                example="Ta",
                help_text="Ta: Non-muscle invasive, confined to mucosa (lower risk). T1: Invades lamina propria (higher risk)."
            ),
            InputMetadata(
                field_name="concurrent_cis",
                display_name="Concurrent CIS",
                input_type=InputType.ENUM,
                required=True,
                description="Presence of concurrent carcinoma in situ",
                allowed_values=["no", "yes"],
                example="no",
                help_text="CIS (high-grade flat dysplasia) is an independent risk factor for recurrence."
            ),
            InputMetadata(
                field_name="grade",
                display_name="Tumor Grade",
                input_type=InputType.ENUM,
                required=True,
                description="WHO 1973 grading system",
                allowed_values=["G1", "G2", "G3"],
                example="G2",
                help_text="G1: Well differentiated (low risk). G2: Moderately differentiated. G3: Poorly differentiated (high-grade, highest recurrence risk)."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate EORTC recurrence inputs."""

        is_valid, msg = self._validate_required(
            inputs,
            [
                "number_of_tumors",
                "tumor_diameter_cm",
                "prior_recurrence_rate",
                "t_category",
                "concurrent_cis",
                "grade",
            ]
        )
        if not is_valid:
            return False, msg

        # Validate number of tumors
        try:
            num_tumors = int(inputs["number_of_tumors"])
            if num_tumors < 1:
                return False, "Number of tumors must be >= 1"
        except (ValueError, TypeError):
            return False, "Number of tumors must be an integer"

        # Validate tumor diameter
        is_valid, msg = self._validate_range(
            inputs["tumor_diameter_cm"], min_val=0.1, max_val=10, param_name="tumor_diameter_cm"
        )
        if not is_valid:
            return False, msg

        # Validate prior recurrence rate
        valid_rates = ["primary", "less_than_1_per_year", "more_than_1_per_year"]
        is_valid, msg = self._validate_enum(
            inputs["prior_recurrence_rate"],
            valid_rates,
            "prior_recurrence_rate"
        )
        if not is_valid:
            return False, msg

        # Validate T category
        is_valid, msg = self._validate_enum(
            inputs["t_category"],
            ["Ta", "T1"],
            "t_category"
        )
        if not is_valid:
            return False, msg

        # Validate CIS
        is_valid, msg = self._validate_enum(
            inputs["concurrent_cis"],
            ["no", "yes"],
            "concurrent_cis"
        )
        if not is_valid:
            return False, msg

        # Validate grade
        valid_grades = ["G1", "G2", "G3"]
        is_valid, msg = self._validate_enum(inputs["grade"], valid_grades, "grade")
        if not is_valid:
            return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate EORTC recurrence score."""

        number_of_tumors = int(inputs["number_of_tumors"])
        tumor_diameter = float(inputs["tumor_diameter_cm"])
        prior_recurrence_rate = inputs["prior_recurrence_rate"]
        t_category = inputs["t_category"]
        concurrent_cis = inputs["concurrent_cis"]
        grade = inputs["grade"]

        # Initialize score
        total_score = 0

        # Number of tumors
        if number_of_tumors == 1:
            tumor_count_score = 0
        elif number_of_tumors <= 7:
            tumor_count_score = 3
        else:
            tumor_count_score = 6
        total_score += tumor_count_score

        # Tumor diameter
        if tumor_diameter < 3:
            diameter_score = 0
        else:
            diameter_score = 3
        total_score += diameter_score

        # Prior recurrence rate
        recurrence_scores = {
            "primary": 0,
            "less_than_1_per_year": 2,
            "more_than_1_per_year": 4,
        }
        recurrence_score = recurrence_scores.get(prior_recurrence_rate, 0)
        total_score += recurrence_score

        # T category
        t_score = 0 if t_category == "Ta" else 1
        total_score += t_score

        # Concurrent CIS
        cis_score = 0 if concurrent_cis == "no" else 1
        total_score += cis_score

        # Grade
        grade_scores = {"G1": 0, "G2": 1, "G3": 2}
        grade_score = grade_scores.get(grade, 0)
        total_score += grade_score

        # Recurrence probability based on score
        if total_score == 0:
            recurrence_1yr = "15%"
            recurrence_5yr = "31%"
        elif total_score <= 4:
            recurrence_1yr = "24%"
            recurrence_5yr = "46%"
        elif total_score <= 9:
            recurrence_1yr = "38%"
            recurrence_5yr = "62%"
        else:
            recurrence_1yr = "61%"
            recurrence_5yr = "78%"

        # Risk category
        if total_score <= 2:
            risk_category = "Low Risk"
        elif total_score <= 5:
            risk_category = "Low-Intermediate Risk"
        elif total_score <= 9:
            risk_category = "Intermediate Risk"
        else:
            risk_category = "High Risk"

        # Build interpretation
        interpretation_parts = [
            f"EORTC Recurrence Score: {total_score}",
            f"Risk Category: {risk_category}",
            f"1-Year Recurrence Probability: {recurrence_1yr}",
            f"5-Year Recurrence Probability: {recurrence_5yr}",
        ]

        result = {
            "total_score": total_score,
            "risk_category": risk_category,
            "recurrence_1_year": recurrence_1yr,
            "recurrence_5_year": recurrence_5yr,
            "number_of_tumors": number_of_tumors,
            "tumor_diameter_cm": round(tumor_diameter, 1),
            "t_category": t_category,
            "grade": grade,
        }

        recommendations = [
            f"Patient is in {risk_category}",
            "Adjuvant intravesical therapy should be considered",
            "Ensure complete TURBT prior to intravesical therapy",
        ]

        if total_score >= 10:
            recommendations.append("Consider early re-resection TURBT")

        recommendations.append("Regular cystoscopic surveillance as per guidelines")

        interpretation = ". ".join(interpretation_parts) + "."

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_category,
            recommendations=recommendations,
            references=self.references,
        )
