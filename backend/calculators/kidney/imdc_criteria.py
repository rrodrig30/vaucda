"""
IMDC Risk Criteria Calculator for Metastatic RCC.

Assesses risk factors in metastatic renal cell carcinoma and predicts
median overall survival and 2-year survival probability.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class IMDCCalculator(ClinicalCalculator):
    """
    IMDC Risk Criteria Calculator.

    Evaluates 6 risk factors in metastatic RCC:
    1. Karnofsky Performance Status < 80%
    2. Time from diagnosis to treatment < 1 year
    3. Hemoglobin < lower limit of normal
    4. Corrected calcium > upper limit of normal
    5. Neutrophils > upper limit of normal
    6. Platelets > upper limit of normal
    """

    @property
    def name(self) -> str:
        return "IMDC Risk Criteria"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.KIDNEY_CANCER

    @property
    def description(self) -> str:
        return "Assess risk factors in metastatic renal cell carcinoma"

    @property
    def references(self) -> List[str]:
        return [
            "Heng DY, et al. Prognostic factors for overall survival in patients with metastatic renal cell carcinoma treated with vascular endothelial growth factor-targeted agents. J Clin Oncol. 2009;27:5794-5799",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return [
            "kps",
            "time_diagnosis_to_treatment_months",
            "hemoglobin_g_dL",
            "calcium_mg_dL",
            "albumin_g_dL",
            "neutrophils_K_uL",
            "platelets_K_uL",
        ]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for IMDC Risk Criteria calculator inputs."""
        return [
            InputMetadata(
                field_name="kps",
                display_name="Karnofsky Performance Status",
                input_type=InputType.NUMERIC,
                required=True,
                description="Performance status score (0-100%)",
                unit="%",
                min_value=0,
                max_value=100,
                example="80",
                help_text="KPS 100=normal, 80=minor symptom, 60=significant symptom, 40=bedbound. <80% is a risk factor for poor outcomes."
            ),
            InputMetadata(
                field_name="time_diagnosis_to_treatment_months",
                display_name="Time from Diagnosis to Treatment",
                input_type=InputType.NUMERIC,
                required=True,
                description="Interval between RCC diagnosis and systemic treatment initiation",
                unit="months",
                min_value=0,
                max_value=120,
                example="6",
                help_text="<12 months (1 year) indicates rapid progression and is a risk factor. Normal range: 0-36 months."
            ),
            InputMetadata(
                field_name="hemoglobin_g_dL",
                display_name="Hemoglobin Level",
                input_type=InputType.NUMERIC,
                required=True,
                description="Hemoglobin concentration in peripheral blood",
                unit="g/dL",
                min_value=5,
                max_value=20,
                example="12.5",
                help_text="Normal: 13.5-17.5 g/dL (men), 12-15.5 g/dL (women). <13.0 g/dL indicates anemia, a risk factor."
            ),
            InputMetadata(
                field_name="calcium_mg_dL",
                display_name="Serum Calcium (uncorrected)",
                input_type=InputType.NUMERIC,
                required=True,
                description="Total serum calcium level before albumin correction",
                unit="mg/dL",
                min_value=6,
                max_value=15,
                example="9.2",
                help_text="Normal: 8.5-10.2 mg/dL. Corrected calcium = measured + 0.8(4-albumin). Elevated corrected calcium is a risk factor."
            ),
            InputMetadata(
                field_name="albumin_g_dL",
                display_name="Serum Albumin",
                input_type=InputType.NUMERIC,
                required=True,
                description="Serum albumin level used to correct calcium",
                unit="g/dL",
                min_value=1,
                max_value=6,
                example="3.8",
                help_text="Normal: 3.5-5.0 g/dL. Used for calcium correction. Lower albumin indicates worse nutritional status."
            ),
            InputMetadata(
                field_name="neutrophils_K_uL",
                display_name="Absolute Neutrophil Count",
                input_type=InputType.NUMERIC,
                required=True,
                description="Neutrophil count from complete blood count",
                unit="K/uL",
                min_value=0.5,
                max_value=50,
                example="6.5",
                help_text="Normal: 2.0-7.5 K/uL. >7.3 K/uL indicates elevation and is a risk factor for poor outcomes."
            ),
            InputMetadata(
                field_name="platelets_K_uL",
                display_name="Platelet Count",
                input_type=InputType.NUMERIC,
                required=True,
                description="Platelet count from complete blood count",
                unit="K/uL",
                min_value=20,
                max_value=1000,
                example="250",
                help_text="Normal: 150-400 K/uL. >400 K/uL (thrombocytosis) indicates a risk factor for metastatic disease."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate IMDC inputs."""

        is_valid, msg = self._validate_required(
            inputs,
            [
                "kps",
                "time_diagnosis_to_treatment_months",
                "hemoglobin_g_dL",
                "calcium_mg_dL",
                "albumin_g_dL",
                "neutrophils_K_uL",
                "platelets_K_uL",
            ]
        )
        if not is_valid:
            return False, msg

        # Validate ranges
        try:
            kps = int(inputs["kps"])
            if kps < 0 or kps > 100:
                return False, "KPS must be between 0 and 100"
        except (ValueError, TypeError):
            return False, "KPS must be an integer"

        is_valid, msg = self._validate_range(
            inputs["time_diagnosis_to_treatment_months"],
            min_val=0,
            max_val=120,
            param_name="time_diagnosis_to_treatment_months"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["hemoglobin_g_dL"],
            min_val=5,
            max_val=20,
            param_name="hemoglobin_g_dL"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["calcium_mg_dL"],
            min_val=6,
            max_val=15,
            param_name="calcium_mg_dL"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["albumin_g_dL"],
            min_val=1,
            max_val=6,
            param_name="albumin_g_dL"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["neutrophils_K_uL"],
            min_val=0.5,
            max_val=50,
            param_name="neutrophils_K_uL"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["platelets_K_uL"],
            min_val=20,
            max_val=1000,
            param_name="platelets_K_uL"
        )
        if not is_valid:
            return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate IMDC risk score."""

        kps = int(inputs["kps"])
        time_to_tx = float(inputs["time_diagnosis_to_treatment_months"])
        hemoglobin = float(inputs["hemoglobin_g_dL"])
        calcium_measured = float(inputs["calcium_mg_dL"])
        albumin = float(inputs["albumin_g_dL"])
        neutrophils = float(inputs["neutrophils_K_uL"])
        platelets = float(inputs["platelets_K_uL"])

        # Calculate corrected calcium
        corrected_calcium = calcium_measured + 0.8 * (4.0 - albumin)

        # Count risk factors (1 point each)
        risk_score = 0
        risk_factors = []

        # 1. KPS < 80%
        if kps < 80:
            risk_score += 1
            risk_factors.append(f"KPS {kps}% < 80%")

        # 2. Time from diagnosis to treatment < 1 year
        if time_to_tx < 12:
            risk_score += 1
            risk_factors.append(f"Time to treatment {time_to_tx:.0f} months < 12 months")

        # 3. Hemoglobin < lower limit of normal (< 13.0 g/dL for men, < 12.0 for women)
        # Using standard cutoff of 13.0 g/dL for men
        if hemoglobin < 13.0:
            risk_score += 1
            risk_factors.append(f"Hemoglobin {hemoglobin:.1f} g/dL < 13.0 g/dL")

        # 4. Corrected calcium > ULN (> 10.2 mg/dL)
        if corrected_calcium > 10.2:
            risk_score += 1
            risk_factors.append(f"Corrected calcium {corrected_calcium:.1f} mg/dL > 10.2 mg/dL")

        # 5. Neutrophils > ULN (> 7.3 K/uL)
        if neutrophils > 7.3:
            risk_score += 1
            risk_factors.append(f"Neutrophils {neutrophils:.1f} K/uL > 7.3 K/uL")

        # 6. Platelets > ULN (> 400 K/uL)
        if platelets > 400:
            risk_score += 1
            risk_factors.append(f"Platelets {platelets:.0f} K/uL > 400 K/uL")

        # Risk group classification
        if risk_score == 0:
            risk_group = "Favorable"
            median_os = "43 months"
            two_yr_os = "75%"
        elif risk_score <= 2:
            risk_group = "Intermediate"
            median_os = "23 months"
            two_yr_os = "53%"
        else:
            risk_group = "Poor"
            median_os = "8 months"
            two_yr_os = "15%"

        # Build interpretation
        risk_factors_str = "\n".join([f"  - {f}" for f in risk_factors]) if risk_factors else "No risk factors identified"

        interpretation_parts = [
            f"IMDC Risk Score: {risk_score}/6",
            f"Risk Group: {risk_group}",
            f"Risk Factors Present:",
            risk_factors_str,
            f"Median Overall Survival: {median_os}",
            f"2-Year Overall Survival: {two_yr_os}",
        ]

        result = {
            "imdc_score": risk_score,
            "risk_group": risk_group,
            "median_os_months": int(float(median_os.split()[0])),
            "two_year_os": two_yr_os,
            "kps": kps,
            "hemoglobin_g_dL": round(hemoglobin, 1),
            "corrected_calcium_mg_dL": round(corrected_calcium, 1),
            "neutrophils_K_uL": round(neutrophils, 1),
            "platelets_K_uL": round(platelets, 0),
        }

        recommendations = [
            f"Patient is in {risk_group} risk group for metastatic disease",
            "Discuss prognosis and treatment options including systemic therapy",
            "Consider first-line targeted therapy (VEGF inhibitors, mTOR inhibitors)",
            "Consider checkpoint inhibitors based on risk group and immunotherapy advances",
        ]

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
