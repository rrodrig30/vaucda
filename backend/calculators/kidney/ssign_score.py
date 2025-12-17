"""
SSIGN Score (Stage Size Grade Necrosis) Calculator.

Predicts metastasis-free survival for patients with clear cell renal cancer
using TNM stage, tumor size, nuclear grade, and necrosis.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class SSIGNCalculator(ClinicalCalculator):
    """
    SSIGN Score Calculator.

    Calculates metastasis-free survival prediction based on:
    - TNM Stage
    - Tumor Size
    - Nuclear Grade
    - Tumor Necrosis
    """

    @property
    def name(self) -> str:
        return "SSIGN Prognostic Score"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.KIDNEY_CANCER

    @property
    def description(self) -> str:
        return "Predict metastasis-free survival for clear cell renal cancer"

    @property
    def references(self) -> List[str]:
        return [
            "Frank I, et al. An outcome prediction model for patients with clear cell renal cancer. J Urol. 2005;174:48-52",
            "Karakiewicz PI, et al. Multi-institutional validation of the SSIGN score for high-risk clear cell renal cell carcinoma. J Urol. 2009;181:32-36",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["tnm_stage", "tumor_size", "nuclear_grade", "necrosis"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for SSIGN Prognostic Score calculator inputs."""
        return [
            InputMetadata(
                field_name="tnm_stage",
                display_name="TNM Stage (T component)",
                input_type=InputType.ENUM,
                required=True,
                description="Tumor stage based on TNM classification",
                allowed_values=["T1a", "T1b", "T2", "T3a", "T3b", "T3c", "T4"],
                example="T1b",
                help_text="T1a: ≤4 cm confined to kidney. T1b: 4-7 cm. T2: >7 cm. T3a: Renal vein/IVC invasion. T3b/c: IVC extension. T4: Beyond Gerota fascia. Higher stages indicate worse prognosis."
            ),
            InputMetadata(
                field_name="tumor_size",
                display_name="Maximum Tumor Diameter",
                input_type=InputType.NUMERIC,
                required=True,
                description="Largest tumor dimension measured on imaging",
                unit="cm",
                min_value=0.1,
                max_value=30,
                example="6.5",
                help_text="Size measured on CT/MRI. Tumors <5 cm have significantly better prognosis than ≥5 cm. Score cutoff at 5 cm."
            ),
            InputMetadata(
                field_name="nuclear_grade",
                display_name="Nuclear Grade (Fuhrman)",
                input_type=InputType.ENUM,
                required=True,
                description="Nuclear grade of tumor cells",
                allowed_values=[1, 2, 3, 4],
                example="2",
                help_text="Grade 1: Small, uniform, fine chromatin (best). Grade 4: Bizarre, multilobated nuclei (worst). Grades 3-4 indicate high-grade disease with poor prognosis."
            ),
            InputMetadata(
                field_name="necrosis",
                display_name="Tumor Necrosis",
                input_type=InputType.ENUM,
                required=True,
                description="Presence of tumor necrosis on pathology",
                allowed_values=["absent", "present"],
                example="absent",
                help_text="Tumor necrosis is a powerful independent prognostic factor indicating aggressive behavior and higher risk of metastasis."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate SSIGN inputs."""

        is_valid, msg = self._validate_required(
            inputs, ["tnm_stage", "tumor_size", "nuclear_grade", "necrosis"]
        )
        if not is_valid:
            return False, msg

        # Validate enums
        valid_stages = ["T1a", "T1b", "T2", "T3a", "T3b", "T3c", "T4"]
        is_valid, msg = self._validate_enum(inputs["tnm_stage"], valid_stages, "tnm_stage")
        if not is_valid:
            return False, msg

        # Validate size
        is_valid, msg = self._validate_range(
            inputs["tumor_size"], min_val=0.1, max_val=30, param_name="tumor_size"
        )
        if not is_valid:
            return False, msg

        # Validate grade
        valid_grades = [1, 2, 3, 4]
        try:
            grade = int(inputs["nuclear_grade"])
            if grade not in valid_grades:
                return False, "Nuclear grade must be 1, 2, 3, or 4"
        except (ValueError, TypeError):
            return False, "Nuclear grade must be an integer"

        # Validate necrosis
        valid_necrosis = ["absent", "present"]
        is_valid, msg = self._validate_enum(inputs["necrosis"], valid_necrosis, "necrosis")
        if not is_valid:
            return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate SSIGN score."""

        tnm_stage = inputs["tnm_stage"]
        tumor_size = float(inputs["tumor_size"])
        nuclear_grade = int(inputs["nuclear_grade"])
        necrosis = inputs["necrosis"]

        # Initialize score
        total_score = 0

        # TNM Stage scoring
        stage_points = {
            "T1a": 0, "T1b": 0,
            "T2": 1,
            "T3a": 2, "T3b": 2, "T3c": 2,
            "T4": 4,
        }
        stage_score = stage_points.get(tnm_stage, 0)
        total_score += stage_score

        # Tumor Size scoring
        if tumor_size < 5:
            size_score = 0
        else:
            size_score = 2
        total_score += size_score

        # Nuclear Grade scoring
        grade_points = {1: 0, 2: 0, 3: 1, 4: 3}
        grade_score = grade_points.get(nuclear_grade, 0)
        total_score += grade_score

        # Necrosis scoring
        necrosis_score = 2 if necrosis == "present" else 0
        total_score += necrosis_score

        # N and M components (if applicable)
        # Note: These are handled as additional inputs if needed
        # For now, assuming M0 N0 status
        n_score = inputs.get("n_score", 0)
        m_score = inputs.get("m_score", 0)
        total_score += n_score + m_score

        # Risk stratification and survival estimates
        if total_score <= 2:
            risk_group = "Low Risk"
            mfs_5yr = "97%"
            mfs_10yr = "94%"
            interpretation_note = "Excellent prognosis"
        elif total_score <= 4:
            risk_group = "Intermediate Risk"
            mfs_5yr = "90%"
            mfs_10yr = "82%"
            interpretation_note = "Good prognosis"
        elif total_score <= 6:
            risk_group = "High-Intermediate Risk"
            mfs_5yr = "78%"
            mfs_10yr = "65%"
            interpretation_note = "Moderately good prognosis"
        elif total_score <= 9:
            risk_group = "High Risk"
            mfs_5yr = "55%"
            mfs_10yr = "38%"
            interpretation_note = "Poor prognosis; consider adjuvant therapy"
        else:
            risk_group = "Very High Risk"
            mfs_5yr = "25%"
            mfs_10yr = "15%"
            interpretation_note = "Very poor prognosis; consider clinical trial or targeted therapy"

        # Build interpretation
        interpretation_parts = [
            f"SSIGN Score: {total_score}",
            f"Risk Group: {risk_group}",
            f"5-Year Metastasis-Free Survival: {mfs_5yr}",
            f"10-Year Metastasis-Free Survival: {mfs_10yr}",
            f"Prognosis: {interpretation_note}",
        ]

        result = {
            "total_score": total_score,
            "tnm_stage": tnm_stage,
            "tumor_size_cm": round(tumor_size, 1),
            "nuclear_grade": nuclear_grade,
            "necrosis": necrosis,
            "risk_group": risk_group,
            "mfs_5_year": mfs_5yr,
            "mfs_10_year": mfs_10yr,
        }

        recommendations = []
        if total_score >= 7:
            recommendations.append("Consider adjuvant systemic therapy")
            recommendations.append("Patient eligible for clinical trials")
        if total_score >= 5:
            recommendations.append("Close surveillance recommended")
            recommendations.append("Consider imaging every 3-4 months initially")

        recommendations.extend([
            "Discuss prognosis and treatment options with patient",
            "Consider systemic therapy options based on performance status",
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
