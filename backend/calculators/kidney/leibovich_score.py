"""
Leibovich Score Calculator for Renal Cell Carcinoma.

Predicts cancer-specific survival using Fuhrman grade, tumor stage,
tumor size, and Eastern Cooperative Oncology Group performance status.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class LeibovichCalculator(ClinicalCalculator):
    """
    Leibovich Score Calculator.

    Combines four factors for CSS prediction:
    - Fuhrman nuclear grade
    - ECOG performance status
    - Tumor stage
    - Tumor size
    """

    @property
    def name(self) -> str:
        return "Leibovich Prognosis Score"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.KIDNEY_CANCER

    @property
    def description(self) -> str:
        return "Predict cancer-specific survival for renal cell carcinoma"

    @property
    def references(self) -> List[str]:
        return [
            "Leibovich BC, et al. Predicting cancer-specific survival after radical nephrectomy for primary clear cell renal carcinoma. J Urol. 2003;169:2143-2146",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["fuhrman_grade", "ecog_ps", "stage", "tumor_size_cm"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Leibovich Prognosis Score calculator inputs."""
        return [
            InputMetadata(
                field_name="fuhrman_grade",
                display_name="Fuhrman Nuclear Grade",
                input_type=InputType.ENUM,
                required=True,
                description="Nuclear grade of tumor cells",
                allowed_values=[1, 2, 3, 4],
                example="2",
                help_text="Grade 1: Uniform nuclei, fine chromatin (well-differentiated). Grade 4: Bizarre, multilobated nuclei (poorly differentiated). Higher grades correlate with worse prognosis."
            ),
            InputMetadata(
                field_name="ecog_ps",
                display_name="ECOG Performance Status",
                input_type=InputType.ENUM,
                required=True,
                description="Eastern Cooperative Oncology Group performance status",
                allowed_values=[0, 1, 2, 3],
                example="0",
                help_text="0: Fully active. 1: Restricted in strenuous activity. 2: Bedbound <50% of day. 3: Bedbound >50% of day. Higher scores worsen prognosis."
            ),
            InputMetadata(
                field_name="stage",
                display_name="TNM Stage",
                input_type=InputType.ENUM,
                required=True,
                description="TNM tumor stage classification",
                allowed_values=["I", "II", "III", "IV"],
                example="II",
                help_text="Stage I: T1 N0 M0. Stage II: T2 N0 M0. Stage III: T3-4 or N1+. Stage IV: M1+. Advanced stages have significantly worse prognosis."
            ),
            InputMetadata(
                field_name="tumor_size_cm",
                display_name="Maximum Tumor Diameter",
                input_type=InputType.NUMERIC,
                required=True,
                description="Size of primary tumor measured in greatest dimension",
                unit="cm",
                min_value=0.1,
                max_value=30,
                example="5.5",
                help_text="Measured on imaging (CT/MRI). Tumors ≤5 cm have better prognosis. Range: 0.1-30 cm (max is >20 cm)."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate Leibovich score inputs."""

        is_valid, msg = self._validate_required(
            inputs, ["fuhrman_grade", "ecog_ps", "stage", "tumor_size_cm"]
        )
        if not is_valid:
            return False, msg

        # Validate Fuhrman grade
        try:
            grade = int(inputs["fuhrman_grade"])
            if grade < 1 or grade > 4:
                return False, "Fuhrman grade must be 1-4"
        except (ValueError, TypeError):
            return False, "Fuhrman grade must be an integer"

        # Validate ECOG PS
        try:
            ecog = int(inputs["ecog_ps"])
            if ecog < 0 or ecog > 3:
                return False, "ECOG PS must be 0-3"
        except (ValueError, TypeError):
            return False, "ECOG PS must be an integer"

        # Validate stage
        valid_stages = ["I", "II", "III", "IV"]
        is_valid, msg = self._validate_enum(inputs["stage"], valid_stages, "stage")
        if not is_valid:
            return False, msg

        # Validate tumor size
        is_valid, msg = self._validate_range(
            inputs["tumor_size_cm"], min_val=0.1, max_val=30, param_name="tumor_size_cm"
        )
        if not is_valid:
            return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate Leibovich score."""

        fuhrman_grade = int(inputs["fuhrman_grade"])
        ecog_ps = int(inputs["ecog_ps"])
        stage = inputs["stage"]
        tumor_size = float(inputs["tumor_size_cm"])

        # Initialize score
        total_score = 0

        # Fuhrman grade scoring
        grade_points = {1: 0, 2: 1, 3: 3, 4: 4}
        grade_score = grade_points.get(fuhrman_grade, 0)
        total_score += grade_score

        # ECOG PS scoring
        ecog_points = {0: 0, 1: 2, 2: 4, 3: 4}
        ecog_score = ecog_points.get(ecog_ps, 0)
        total_score += ecog_score

        # Stage scoring
        stage_points = {"I": 0, "II": 2, "III": 4, "IV": 8}
        stage_score = stage_points.get(stage, 0)
        total_score += stage_score

        # Tumor size scoring
        if tumor_size <= 5:
            size_score = 0
        elif tumor_size <= 10:
            size_score = 1
        else:
            size_score = 2
        total_score += size_score

        # Risk stratification
        if total_score <= 2:
            risk_group = "Low Risk"
            css_5yr = "95%"
            css_10yr = "90%"
        elif total_score <= 5:
            risk_group = "Low-Intermediate Risk"
            css_5yr = "89%"
            css_10yr = "83%"
        elif total_score <= 9:
            risk_group = "Intermediate Risk"
            css_5yr = "75%"
            css_10yr = "64%"
        elif total_score <= 14:
            risk_group = "High Risk"
            css_5yr = "49%"
            css_10yr = "31%"
        else:
            risk_group = "Very High Risk"
            css_5yr = "24%"
            css_10yr = "12%"

        # Build interpretation
        interpretation_parts = [
            f"Leibovich Score: {total_score}",
            f"Risk Group: {risk_group}",
            f"5-Year Cancer-Specific Survival: {css_5yr}",
            f"10-Year Cancer-Specific Survival: {css_10yr}",
        ]

        result = {
            "total_score": total_score,
            "fuhrman_grade": fuhrman_grade,
            "ecog_ps": ecog_ps,
            "stage": stage,
            "tumor_size_cm": round(tumor_size, 1),
            "risk_group": risk_group,
            "css_5_year": css_5yr,
            "css_10_year": css_10yr,
        }

        recommendations = []
        if total_score >= 10:
            recommendations.append("Consider adjuvant systemic therapy")
            recommendations.append("Intensive surveillance recommended")
        if total_score >= 5:
            recommendations.append("Regular imaging and lab monitoring")

        recommendations.extend([
            "Discuss prognosis with patient",
            "Consider clinical trials for advanced disease",
        ])

        interpretation = ". ".join(interpretation_parts) + "."

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_group,
            recommendations=recommendations,
            references=self.references,
        )
