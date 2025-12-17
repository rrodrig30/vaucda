"""
EORTC Progression Score Calculator for NMIBC.

Predicts 1-year and 5-year progression probability to muscle-invasive
disease for non-muscle invasive bladder cancer.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class EORTCProgressionCalculator(ClinicalCalculator):
    """
    EORTC Progression Score Calculator.

    Calculates progression risk (0-23 points) based on:
    - Number of tumors
    - T category
    - Concurrent CIS
    - Grade (WHO 1973)
    """

    @property
    def name(self) -> str:
        return "EORTC Progression Score"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.BLADDER_CANCER

    @property
    def description(self) -> str:
        return "Predict progression risk to muscle-invasive disease"

    @property
    def references(self) -> List[str]:
        return [
            "Sylvester RJ, et al. Predicting recurrence and progression in individual patients with stage Ta, T1 bladder cancer. J Urol. 2006;175:2090-2095",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["number_of_tumors", "t_category", "concurrent_cis", "grade"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for EORTC Progression Score calculator inputs."""
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
                example="3",
                help_text="Count all tumors identified on cystoscopy. Higher numbers increase progression risk."
            ),
            InputMetadata(
                field_name="t_category",
                display_name="Tumor Category",
                input_type=InputType.ENUM,
                required=True,
                description="TNM stage of bladder tumor",
                allowed_values=["Ta", "T1"],
                example="T1",
                help_text="Ta: Non-muscle invasive, confined to mucosa. T1: Invades lamina propria. T1 disease has higher progression risk."
            ),
            InputMetadata(
                field_name="concurrent_cis",
                display_name="Concurrent CIS",
                input_type=InputType.ENUM,
                required=True,
                description="Presence of concurrent carcinoma in situ",
                allowed_values=["no", "yes"],
                example="no",
                help_text="Carcinoma in situ significantly increases progression risk. CIS is high-grade dysplasia."
            ),
            InputMetadata(
                field_name="grade",
                display_name="Tumor Grade",
                input_type=InputType.ENUM,
                required=True,
                description="WHO 1973 grading system",
                allowed_values=["G1", "G2", "G3"],
                example="G2",
                help_text="G1: Well differentiated. G2: Moderately differentiated. G3: Poorly differentiated (high-grade, highest risk)."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate EORTC progression inputs."""

        is_valid, msg = self._validate_required(
            inputs, ["number_of_tumors", "t_category", "concurrent_cis", "grade"]
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
        """Calculate EORTC progression score."""

        number_of_tumors = int(inputs["number_of_tumors"])
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
            tumor_count_score = 3
        total_score += tumor_count_score

        # T category
        t_score = 0 if t_category == "Ta" else 4
        total_score += t_score

        # Concurrent CIS
        cis_score = 0 if concurrent_cis == "no" else 6
        total_score += cis_score

        # Grade
        grade_scores = {"G1": 0, "G2": 2, "G3": 5}
        grade_score = grade_scores.get(grade, 0)
        total_score += grade_score

        # Progression probability
        if total_score == 0:
            progression_1yr = "0.2%"
            progression_5yr = "0.8%"
            risk_category = "Very Low Risk"
        elif total_score <= 6:
            progression_1yr = "1%"
            progression_5yr = "6%"
            risk_category = "Low Risk"
        elif total_score <= 13:
            progression_1yr = "5%"
            progression_5yr = "17%"
            risk_category = "Intermediate Risk"
        else:
            progression_1yr = "17%"
            progression_5yr = "45%"
            risk_category = "High Risk"

        # Build interpretation
        interpretation_parts = [
            f"EORTC Progression Score: {total_score}",
            f"Risk Category: {risk_category}",
            f"1-Year Progression Probability: {progression_1yr}",
            f"5-Year Progression Probability: {progression_5yr}",
        ]

        result = {
            "total_score": total_score,
            "risk_category": risk_category,
            "progression_1_year": progression_1yr,
            "progression_5_year": progression_5yr,
            "number_of_tumors": number_of_tumors,
            "t_category": t_category,
            "grade": grade,
            "concurrent_cis": concurrent_cis,
        }

        recommendations = [
            f"Patient is in {risk_category} for progression",
            "Regular surveillance with cystoscopy and upper tract imaging",
        ]

        if total_score >= 10:
            recommendations.append(
                "Consider early radical cystoprostatectomy given high progression risk"
            )
            recommendations.append("Discuss aggressive treatment options with patient")
        else:
            recommendations.append("Intravesical BCG therapy recommended for intermediate/high risk")

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
