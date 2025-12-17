"""
PCPT Risk Calculator 2.0 (Prostate Cancer Prevention Trial).

Predicts risk of prostate cancer on biopsy using logistic regression.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class PCPTCalculator(ClinicalCalculator):
    """
    PCPT Risk Calculator 2.0.

    Uses logistic regression to predict:
    1. Risk of any prostate cancer
    2. Risk of high-grade cancer (Gleason >= 7)
    """

    @property
    def name(self) -> str:
        return "PCPT Risk Calculator 2.0"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.PROSTATE_CANCER

    @property
    def description(self) -> str:
        return "Predict risk of prostate cancer and high-grade disease on biopsy"

    @property
    def references(self) -> List[str]:
        return [
            "Thompson IM, et al. J Clin Oncol 2006;24:1467-1473",
            "Ankerst DP, et al. Eur Urol 2012;61:1019-1024",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["age", "psa", "dre_abnormal", "african_american", "family_history", "prior_negative_biopsy"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for PCPT Risk Calculator 2.0 inputs."""
        return [
            InputMetadata(
                field_name="age",
                display_name="Patient Age",
                input_type=InputType.NUMERIC,
                required=True,
                description="Patient age at time of PSA/DRE screening",
                unit="years",
                min_value=40,
                max_value=100,
                example="65",
                help_text="PCPT 2.0 developed in men aged 40-70. Older age increases cancer risk probability."
            ),
            InputMetadata(
                field_name="psa",
                display_name="PSA Level",
                input_type=InputType.NUMERIC,
                required=True,
                description="Serum prostate-specific antigen at screening",
                unit="ng/mL",
                min_value=0,
                max_value=50,
                example="5.5",
                help_text="Normal: <4 ng/mL. Model uses log(PSA) transformation. Higher PSA increases cancer probability."
            ),
            InputMetadata(
                field_name="dre_abnormal",
                display_name="Abnormal DRE",
                input_type=InputType.BOOLEAN,
                required=True,
                description="Presence of abnormal findings on digital rectal examination",
                example="false",
                help_text="Abnormal DRE (hard areas, nodules, asymmetry) increases cancer probability. Critical risk factor."
            ),
            InputMetadata(
                field_name="african_american",
                display_name="African American",
                input_type=InputType.BOOLEAN,
                required=True,
                description="Patient race/ethnicity as African American",
                example="false",
                help_text="African American men have higher prostate cancer incidence and mortality. Independent risk factor."
            ),
            InputMetadata(
                field_name="family_history",
                display_name="Family History of Prostate Cancer",
                input_type=InputType.BOOLEAN,
                required=True,
                description="History of prostate cancer in first-degree relatives",
                example="false",
                help_text="Family history (father, brother, or son) increases cancer probability. Indicates genetic susceptibility."
            ),
            InputMetadata(
                field_name="prior_negative_biopsy",
                display_name="Prior Negative Biopsy",
                input_type=InputType.BOOLEAN,
                required=True,
                description="Previous prostate biopsy with benign pathology",
                example="false",
                help_text="Prior negative biopsy reduces future cancer probability (negative predictive value). Protective factor."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate PCPT inputs."""

        # Check required fields
        valid, msg = self._validate_required(inputs, self.required_inputs)
        if not valid:
            return False, msg

        # Validate age
        valid, msg = self._validate_range(
            inputs["age"],
            min_val=40,
            max_val=100,
            param_name="age"
        )
        if not valid:
            return False, msg

        # Validate PSA
        valid, msg = self._validate_range(
            inputs["psa"],
            min_val=0,
            max_val=50,
            param_name="psa"
        )
        if not valid:
            return False, msg

        # Validate boolean fields
        for field in ["dre_abnormal", "african_american", "family_history", "prior_negative_biopsy"]:
            if not isinstance(inputs[field], bool):
                return False, f"{field} must be boolean (True/False)"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate PCPT risk scores."""

        age = inputs["age"]
        psa = inputs["psa"]
        dre_abnormal = 1 if inputs["dre_abnormal"] else 0
        african_american = 1 if inputs["african_american"] else 0
        family_history = 1 if inputs["family_history"] else 0
        prior_negative_biopsy = 1 if inputs["prior_negative_biopsy"] else 0

        # Calculate log(PSA) for regression (PCPT 2.0 uses log transformation)
        log_psa = math.log(psa) if psa > 0 else 0

        # Logistic regression coefficients for ANY prostate cancer
        # Reference: Ankerst DP, et al. Eur Urol 2012 (PCPT 2.0)
        # Model uses log(PSA) transformation for better calibration
        # logit(P) = intercept + Σ(coefficient × variable)
        logit_any = (
            -3.35 +  # Calibrated intercept for log(PSA) model
            0.0187 * age +
            0.4467 * african_american +
            0.2893 * family_history -
            0.1465 * prior_negative_biopsy +
            0.7173 * log_psa +  # Coefficient for log(PSA), not linear PSA
            0.3746 * dre_abnormal
        )

        # Convert logit to probability
        prob_any = math.exp(logit_any) / (1 + math.exp(logit_any))
        prob_any_percent = prob_any * 100

        # Logistic regression coefficients for HIGH-GRADE cancer (Gleason >= 7)
        # Reference: Ankerst DP, et al. Eur Urol 2012 (PCPT 2.0)
        # Model uses log(PSA) transformation
        logit_high = (
            -5.54 +  # Calibrated intercept for log(PSA) model
            0.0354 * age +
            0.5038 * african_american +
            0.2885 * family_history -
            0.1886 * prior_negative_biopsy +
            0.8677 * log_psa +  # Coefficient for log(PSA), not linear PSA
            0.6691 * dre_abnormal
        )

        # Convert logit to probability
        prob_high = math.exp(logit_high) / (1 + math.exp(logit_high))
        prob_high_percent = prob_high * 100

        # Determine risk categories
        if prob_any_percent < 10:
            any_risk_category = "Low Risk"
        elif prob_any_percent < 25:
            any_risk_category = "Moderate Risk"
        else:
            any_risk_category = "High Risk"

        if prob_high_percent < 5:
            high_risk_category = "Low Risk"
        elif prob_high_percent < 15:
            high_risk_category = "Moderate Risk"
        else:
            high_risk_category = "High Risk"

        # Build interpretation
        interpretation = (
            f"Risk of any prostate cancer: {prob_any_percent:.1f}% ({any_risk_category}). "
            f"Risk of high-grade cancer (Gleason ≥7): {prob_high_percent:.1f}% ({high_risk_category})."
        )

        # Build recommendations
        recommendations = []
        if prob_any_percent >= 25:
            recommendations.append("High risk - biopsy strongly recommended")
        elif prob_any_percent >= 10:
            recommendations.append("Moderate risk - consider prostate biopsy")
            recommendations.append("Discuss risks and benefits with patient")
        else:
            recommendations.append("Low risk - consider continued surveillance")
            recommendations.append("Shared decision-making regarding biopsy")

        if prob_high_percent >= 15:
            recommendations.append("Elevated risk of high-grade disease if cancer present")
            recommendations.append("Consider MRI-targeted biopsy if available")

        result = {
            "risk_any_cancer": f"{prob_any_percent:.1f}%",
            "risk_high_grade": f"{prob_high_percent:.1f}%",
            "any_cancer_category": any_risk_category,
            "high_grade_category": high_risk_category,
            "inputs_used": {
                "age": age,
                "psa": psa,
                "dre_abnormal": "Yes" if dre_abnormal else "No",
                "african_american": "Yes" if african_american else "No",
                "family_history": "Yes" if family_history else "No",
                "prior_negative_biopsy": "Yes" if prior_negative_biopsy else "No",
            }
        }

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            category=any_risk_category,
            risk_level=any_risk_category,
            recommendations=recommendations,
            references=self.references,
        )
