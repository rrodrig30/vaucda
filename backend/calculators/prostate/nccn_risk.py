"""
NCCN Risk Stratification for Prostate Cancer.

Classifies patients into risk categories based on PSA, Gleason Grade Group, and T stage.
"""

from typing import Any, Dict, List, Optional, Tuple

from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class NCCNRiskCalculator(ClinicalCalculator):
    """
    NCCN Risk Stratification Calculator.

    Risk categories:
    - Very Low Risk
    - Low Risk
    - Intermediate Favorable
    - Intermediate Unfavorable
    - High Risk
    - Very High Risk
    """

    @property
    def name(self) -> str:
        return "NCCN Risk Stratification"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.PROSTATE_CANCER

    @property
    def description(self) -> str:
        return "Classify prostate cancer into NCCN risk categories"

    @property
    def references(self) -> List[str]:
        return [
            "NCCN Clinical Practice Guidelines in Oncology: Prostate Cancer Version 4.2024",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["psa", "grade_group", "t_stage"]

    @property
    def optional_inputs(self) -> List[str]:
        return ["num_positive_cores", "total_cores", "psad", "primary_gleason_pattern"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for NCCN Risk Stratification calculator inputs."""
        return [
            InputMetadata(
                field_name="psa",
                display_name="PSA Level",
                input_type=InputType.NUMERIC,
                required=True,
                description="Serum prostate-specific antigen at diagnosis",
                unit="ng/mL",
                min_value=0,
                max_value=500,
                example="8.5",
                help_text="Normal: <4 ng/mL. 4-10 ng/mL: Gray zone. >10 ng/mL: Elevated. Used with grade and stage for NCCN risk classification."
            ),
            InputMetadata(
                field_name="grade_group",
                display_name="Gleason Grade Group",
                input_type=InputType.ENUM,
                required=True,
                description="Grade group based on new prostate cancer grading system",
                allowed_values=[1, 2, 3, 4, 5],
                example="1",
                help_text="Grade Group 1 (3+3=6): Best prognosis. Grade Group 5 (4+5, 5+4, 5+5): Worst prognosis. Higher groups indicate aggressive disease."
            ),
            InputMetadata(
                field_name="t_stage",
                display_name="Clinical T Stage",
                input_type=InputType.ENUM,
                required=True,
                description="Clinical tumor stage based on DRE and imaging",
                allowed_values=["T1a", "T1b", "T1c", "T2a", "T2b", "T2c", "T3a", "T3b", "T4"],
                example="T2a",
                help_text="T1: Impalpable. T2: Confined to prostate. T3: Extraprostatic extension. T4: Invades other structures. Higher stages indicate more advanced disease."
            ),
            InputMetadata(
                field_name="num_positive_cores",
                display_name="Number of Positive Biopsy Cores",
                input_type=InputType.NUMERIC,
                required=False,
                description="Count of biopsy cores positive for cancer",
                unit="cores",
                min_value=0,
                max_value=50,
                example="2",
                help_text="Used to calculate percent positive cores. Helps distinguish intermediate favorable vs. unfavorable disease."
            ),
            InputMetadata(
                field_name="total_cores",
                display_name="Total Biopsy Cores",
                input_type=InputType.NUMERIC,
                required=False,
                description="Total number of biopsy cores obtained",
                unit="cores",
                min_value=1,
                max_value=50,
                example="12",
                help_text="Standard biopsy protocols obtain 10-12 cores. Calculate percent positive cores as (positive/total) × 100."
            ),
            InputMetadata(
                field_name="psad",
                display_name="PSA Density",
                input_type=InputType.NUMERIC,
                required=False,
                description="PSA level divided by prostate volume",
                unit="ng/mL/cm3",
                min_value=0,
                max_value=2,
                example="0.15",
                help_text="PSAD <0.15 is favorable, ≥0.15 is unfavorable. Helps refine intermediate risk stratification."
            ),
            InputMetadata(
                field_name="primary_gleason_pattern",
                display_name="Primary Gleason Pattern",
                input_type=InputType.ENUM,
                required=False,
                description="Primary (most common) Gleason pattern for very high risk assessment",
                allowed_values=[1, 2, 3, 4, 5],
                example="5",
                help_text="Pattern 5 in primary position indicates very high risk disease regardless of secondary pattern."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate NCCN inputs."""

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

        # Validate Grade Group
        valid, msg = self._validate_enum(
            inputs["grade_group"],
            [1, 2, 3, 4, 5],
            param_name="grade_group"
        )
        if not valid:
            return False, msg

        # Validate T stage
        valid_t_stages = ["T1a", "T1b", "T1c", "T2a", "T2b", "T2c", "T3a", "T3b", "T4"]
        valid, msg = self._validate_enum(
            inputs["t_stage"],
            valid_t_stages,
            param_name="t_stage"
        )
        if not valid:
            return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate NCCN risk stratification."""

        psa = inputs["psa"]
        grade_group = inputs["grade_group"]
        t_stage = inputs["t_stage"]

        # Optional inputs
        num_positive_cores = inputs.get("num_positive_cores")
        total_cores = inputs.get("total_cores")
        psad = inputs.get("psad")
        primary_gleason = inputs.get("primary_gleason_pattern")

        # Calculate percent positive cores if available
        percent_positive_cores = None
        if num_positive_cores is not None and total_cores is not None and total_cores > 0:
            percent_positive_cores = (num_positive_cores / total_cores) * 100

        # Determine risk category
        risk_category = self._determine_risk_category(
            psa, grade_group, t_stage, percent_positive_cores, psad, primary_gleason
        )

        # Get treatment recommendations
        recommendations = self._get_recommendations(risk_category)

        # Get surveillance criteria
        surveillance = self._get_surveillance(risk_category)

        # Build interpretation
        interpretation = f"NCCN Risk Category: {risk_category}. "

        if risk_category == "Very Low Risk":
            interpretation += "Excellent prognosis, active surveillance strongly recommended."
        elif risk_category == "Low Risk":
            interpretation += "Favorable prognosis, active surveillance or definitive treatment."
        elif risk_category == "Intermediate Favorable":
            interpretation += "Good prognosis, definitive treatment recommended."
        elif risk_category == "Intermediate Unfavorable":
            interpretation += "Moderate risk, definitive treatment with consideration of multimodal therapy."
        elif risk_category == "High Risk":
            interpretation += "Significant risk of progression, multimodal therapy recommended."
        else:  # Very High Risk
            interpretation += "Very high risk of progression, aggressive multimodal therapy indicated."

        result = {
            "risk_category": risk_category,
            "criteria_met": self._get_criteria_met(psa, grade_group, t_stage, percent_positive_cores, psad),
            "treatment_options": recommendations,
            "surveillance_criteria": surveillance if risk_category in ["Very Low Risk", "Low Risk"] else None,
        }

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            category=risk_category,
            risk_level=risk_category,
            recommendations=recommendations,
            references=self.references,
        )

    def _determine_risk_category(
        self,
        psa: float,
        grade_group: int,
        t_stage: str,
        percent_positive: Optional[float],
        psad: Optional[float],
        primary_gleason: Optional[int]
    ) -> str:
        """Determine NCCN risk category based on criteria."""

        # Very Low Risk (all criteria must be met)
        # Requires <=3 positive cores (or no core info provided)
        if (
            t_stage == "T1c" and
            grade_group == 1 and
            psa < 10 and
            (percent_positive is None or percent_positive <= 30) and
            (psad is None or psad < 0.15)
        ):
            return "Very Low Risk"

        # Low Risk (all criteria must be met, not qualifying for very low)
        if (
            t_stage in ["T1a", "T1b", "T1c", "T2a"] and
            grade_group == 1 and
            psa < 10
        ):
            return "Low Risk"

        # Very High Risk (any one criterion)
        if (
            t_stage in ["T3b", "T4"] or
            (primary_gleason == 5) or
            (grade_group >= 4 and percent_positive is not None and percent_positive > 50)
        ):
            return "Very High Risk"

        # High Risk (any one criterion)
        if (
            t_stage == "T3a" or
            grade_group in [4, 5] or
            psa > 20
        ):
            return "High Risk"

        # Intermediate (has one or more intermediate risk factors)
        if (
            t_stage in ["T2b", "T2c"] or
            grade_group in [2, 3] or
            (10 <= psa <= 20)
        ):
            # Determine favorable vs unfavorable
            if grade_group >= 3 or (percent_positive is not None and percent_positive >= 50):
                return "Intermediate Unfavorable"
            else:
                return "Intermediate Favorable"

        # Default to low if no other category fits
        return "Low Risk"

    def _get_criteria_met(
        self,
        psa: float,
        grade_group: int,
        t_stage: str,
        percent_positive: Optional[float],
        psad: Optional[float]
    ) -> List[str]:
        """Get list of criteria met for risk stratification."""

        criteria = []

        if t_stage in ["T1a", "T1b", "T1c", "T2a"]:
            criteria.append(f"Clinical stage {t_stage}")
        elif t_stage in ["T2b", "T2c"]:
            criteria.append(f"Clinical stage {t_stage} (intermediate risk factor)")
        elif t_stage in ["T3a", "T3b", "T4"]:
            criteria.append(f"Clinical stage {t_stage} (high/very high risk)")

        if psa < 10:
            criteria.append(f"PSA {psa} ng/mL (low)")
        elif psa <= 20:
            criteria.append(f"PSA {psa} ng/mL (intermediate risk factor)")
        else:
            criteria.append(f"PSA {psa} ng/mL (high risk)")

        criteria.append(f"Grade Group {grade_group}")

        if percent_positive is not None:
            if percent_positive < 50:
                criteria.append(f"{percent_positive:.1f}% positive cores (favorable)")
            else:
                criteria.append(f"{percent_positive:.1f}% positive cores (unfavorable)")

        if psad is not None:
            if psad < 0.15:
                criteria.append(f"PSA density {psad:.3f} (favorable)")
            else:
                criteria.append(f"PSA density {psad:.3f}")

        return criteria

    def _get_recommendations(self, risk_category: str) -> List[str]:
        """Get treatment recommendations based on risk category."""

        if risk_category == "Very Low Risk":
            return [
                "Active surveillance (preferred)",
                "Radical prostatectomy (alternative)",
                "Radiation therapy (alternative)",
            ]
        elif risk_category == "Low Risk":
            return [
                "Active surveillance",
                "Radical prostatectomy",
                "Radiation therapy (EBRT or brachytherapy)",
            ]
        elif risk_category == "Intermediate Favorable":
            return [
                "Radical prostatectomy with pelvic lymph node dissection",
                "Radiation therapy + short-term ADT (4-6 months)",
            ]
        elif risk_category == "Intermediate Unfavorable":
            return [
                "Radical prostatectomy with pelvic lymph node dissection",
                "Radiation therapy + ADT (4-6 months)",
            ]
        elif risk_category == "High Risk":
            return [
                "Radiation therapy + long-term ADT (18-36 months)",
                "Radical prostatectomy with pelvic lymph node dissection (selected patients)",
            ]
        else:  # Very High Risk
            return [
                "Radiation therapy + long-term ADT (24-36 months)",
                "Consider docetaxel in addition to ADT",
                "Clinical trial enrollment encouraged",
            ]

    def _get_surveillance(self, risk_category: str) -> Optional[Dict]:
        """Get active surveillance criteria."""

        if risk_category in ["Very Low Risk", "Low Risk"]:
            return {
                "psa_frequency": "Every 3-6 months",
                "dre_frequency": "Every 6-12 months",
                "confirmatory_biopsy": "Within 6-12 months",
                "surveillance_biopsies": "Every 2-4 years",
                "mri": "As indicated",
                "triggers_for_intervention": [
                    "Grade Group progression (≥ Grade Group 2)",
                    "Increased tumor volume on biopsy",
                    "Patient preference change",
                ]
            }

        return None
