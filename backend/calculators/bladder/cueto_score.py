"""
CUETO BCG Risk Score Calculator.

Predicts BCG response failure in patients with non-muscle invasive
bladder cancer receiving BCG immunotherapy.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class CuetoCalculator(ClinicalCalculator):
    """
    CUETO BCG Risk Score Calculator.

    Predicts BCG failure based on:
    - Tumor category
    - Concurrent CIS
    - Grade
    - Age
    - Gender
    """

    @property
    def name(self) -> str:
        return "CUETO BCG Risk Score"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.BLADDER_CANCER

    @property
    def description(self) -> str:
        return "Predict BCG response failure in NMIBC"

    @property
    def references(self) -> List[str]:
        return [
            "Fernandez-Gomez JM, et al. Prognostic factors in patients with non-muscle-invasive bladder cancer treated with bacillus Calmette-Guérin: multivariate analysis of data from four randomized CUETO trials. Eur Urol. 2008;53(5):992-1002",
            "Luo HL, et al. Prognostic factors of complete response to BCG therapy in patients with T1 bladder cancer. Urol Oncol. 2013;31:909-915",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["t_category", "concurrent_cis", "grade", "age", "gender"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for CUETO BCG Risk Score calculator inputs."""
        return [
            InputMetadata(
                field_name="t_category",
                display_name="Tumor Category",
                input_type=InputType.ENUM,
                required=True,
                description="TNM stage of bladder tumor",
                allowed_values=["Ta", "T1"],
                example="T1",
                help_text="Ta: Non-muscle invasive, confined to mucosa. T1: Invades lamina propria but not muscle."
            ),
            InputMetadata(
                field_name="concurrent_cis",
                display_name="Concurrent CIS",
                input_type=InputType.ENUM,
                required=True,
                description="Presence of concurrent carcinoma in situ",
                allowed_values=["no", "yes"],
                example="no",
                help_text="Carcinoma in situ (CIS) is a high-grade flat lesion indicating aggressive disease."
            ),
            InputMetadata(
                field_name="grade",
                display_name="Tumor Grade",
                input_type=InputType.ENUM,
                required=True,
                description="WHO 1973 grading system",
                allowed_values=["G1", "G2", "G3"],
                example="G2",
                help_text="G1: Well differentiated. G2: Moderately differentiated. G3: Poorly differentiated (high-grade)."
            ),
            InputMetadata(
                field_name="age",
                display_name="Age",
                input_type=InputType.NUMERIC,
                required=True,
                description="Patient age in years",
                unit="years",
                min_value=18,
                max_value=120,
                example="65",
                help_text="Age >70 is a risk factor for BCG failure."
            ),
            InputMetadata(
                field_name="gender",
                display_name="Gender",
                input_type=InputType.ENUM,
                required=True,
                description="Patient biological sex",
                allowed_values=["male", "female"],
                example="male",
                help_text="Female gender is associated with increased BCG failure risk."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate CUETO inputs."""

        is_valid, msg = self._validate_required(
            inputs, ["t_category", "concurrent_cis", "grade", "age", "gender"]
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

        # Validate age
        is_valid, msg = self._validate_range(
            inputs["age"], min_val=18, max_val=120, param_name="age"
        )
        if not is_valid:
            return False, msg

        # Validate gender
        is_valid, msg = self._validate_enum(
            inputs["gender"],
            ["male", "female"],
            "gender"
        )
        if not is_valid:
            return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate CUETO BCG risk score."""

        t_category = inputs["t_category"]
        concurrent_cis = inputs["concurrent_cis"]
        grade = inputs["grade"]
        age = int(float(inputs["age"]))
        gender = inputs["gender"]

        # Initialize score
        total_score = 0

        # T category
        if t_category == "T1":
            total_score += 1

        # Concurrent CIS
        if concurrent_cis == "yes":
            total_score += 1

        # Grade
        if grade == "G3":
            total_score += 1

        # Age > 70
        if age > 70:
            total_score += 1

        # Female gender
        if gender == "female":
            total_score += 1

        # BCG failure risk stratification
        if total_score == 0:
            risk_group = "Low Risk"
            bcg_failure_prob = "~5-10%"
        elif total_score == 1:
            risk_group = "Intermediate Risk"
            bcg_failure_prob = "~15-20%"
        elif total_score == 2:
            risk_group = "High Risk"
            bcg_failure_prob = "~25-35%"
        else:
            risk_group = "Very High Risk"
            bcg_failure_prob = "~40-50%"

        # Build interpretation
        interpretation_parts = [
            f"CUETO BCG Risk Score: {total_score}/5",
            f"Risk Group: {risk_group}",
            f"BCG Failure Probability: {bcg_failure_prob}",
            f"Risk factors present: ",
        ]

        risk_factors = []
        if t_category == "T1":
            risk_factors.append("T1 disease")
        if concurrent_cis == "yes":
            risk_factors.append("Concurrent CIS")
        if grade == "G3":
            risk_factors.append("High-grade disease")
        if age > 70:
            risk_factors.append("Age > 70")
        if gender == "female":
            risk_factors.append("Female gender")

        result = {
            "total_score": total_score,
            "risk_group": risk_group,
            "bcg_failure_probability": bcg_failure_prob,
            "t_category": t_category,
            "grade": grade,
            "age": age,
            "gender": gender,
            "risk_factors": risk_factors,
        }

        recommendations = [
            f"Patient is in {risk_group} for BCG failure",
        ]

        if total_score >= 3:
            recommendations.append(
                "Consider alternative/intensified BCG regimen (dose or schedule)"
            )
            recommendations.append(
                "Early recognition of BCG failure recommended"
            )
            recommendations.append(
                "Lower threshold for cystectomy if BCG fails"
            )
        else:
            recommendations.append("Standard BCG induction therapy recommended")
            recommendations.append("Maintenance BCG may improve response")

        recommendations.append("Regular surveillance with cystoscopy")

        interpretation_str = interpretation_parts[0] + "\n" + interpretation_parts[1] + "\n" + interpretation_parts[2]
        if risk_factors:
            interpretation_str += "\n" + interpretation_parts[3] + " " + ", ".join(risk_factors)

        # Add recommendation summary to interpretation
        if total_score >= 3:
            interpretation_str += "\nRecommendation: Alternative/intensified BCG regimen recommended"
        else:
            interpretation_str += "\nRecommendation: Standard BCG induction"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation_str,
            risk_level=risk_group,
            recommendations=recommendations,
            references=self.references,
        )
