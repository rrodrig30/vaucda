"""
DRE Prostate Volume Estimation Calculator.

Estimates prostate volume based on digital rectal examination findings.
Uses multiple estimation methods for comparison.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class DREVolumeCalculator(ClinicalCalculator):
    """
    DRE Prostate Volume Estimation Calculator.

    Estimates prostate volume from DRE examination findings using:
    1. Standard formula based on length, width, depth
    2. Classification by size categories
    3. Comparison with ultrasound estimates
    """

    @property
    def name(self) -> str:
        return "DRE Prostate Volume Estimation"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.PROSTATE_CANCER

    @property
    def description(self) -> str:
        return "Estimate prostate volume from digital rectal examination findings"

    @property
    def references(self) -> List[str]:
        return [
            "Roehrborn CG. BPH: epidemiology and comorbidities. Am J Manag Care. 2006;12:S122-S128",
            "Boyle P, et al. Prostate volume predicts outcome of treatment of benign prostatic hyperplasia with finasteride. Lancet. 1996;348:1523-1527",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["length_cm", "width_cm", "depth_cm"]

    @property
    def optional_inputs(self) -> List[str]:
        return ["consistency", "nodularity", "symmetry"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for DRE Prostate Volume calculator inputs."""
        return [
            InputMetadata(
                field_name="length_cm",
                display_name="Prostate Length (Cephalocaudal)",
                input_type=InputType.NUMERIC,
                required=True,
                description="Prostate length measured head-to-toe on DRE",
                unit="cm",
                min_value=0.5,
                max_value=8,
                example="3.5",
                help_text="Normal prostate length: 2.5-3.5 cm. Measured along the midline from apex to base during DRE."
            ),
            InputMetadata(
                field_name="width_cm",
                display_name="Prostate Width (Transverse)",
                input_type=InputType.NUMERIC,
                required=True,
                description="Prostate width measured side-to-side on DRE",
                unit="cm",
                min_value=0.5,
                max_value=6,
                example="3.0",
                help_text="Normal prostate width: 2.5-3.0 cm. Measured across the widest lateral dimension."
            ),
            InputMetadata(
                field_name="depth_cm",
                display_name="Prostate Depth (Anterior-Posterior)",
                input_type=InputType.NUMERIC,
                required=True,
                description="Prostate depth measured front-to-back on DRE",
                unit="cm",
                min_value=0.5,
                max_value=6,
                example="2.5",
                help_text="Normal prostate depth: 2.0-2.5 cm. Measured from anterior surface to posterior rectal wall."
            ),
            InputMetadata(
                field_name="consistency",
                display_name="Prostate Consistency",
                input_type=InputType.ENUM,
                required=False,
                description="Texture and firmness of prostate on DRE palpation",
                allowed_values=["soft", "firm", "hard"],
                example="firm",
                help_text="Soft: May suggest benign hyperplasia. Firm: Typical of benign hyperplasia. Hard/nodular: Concerning for malignancy, may warrant biopsy."
            ),
            InputMetadata(
                field_name="nodularity",
                display_name="Nodularity Present",
                input_type=InputType.ENUM,
                required=False,
                description="Presence of palpable nodules or irregularities",
                allowed_values=["absent", "present"],
                example="absent",
                help_text="Nodular areas on DRE may indicate focal pathology. Present requires further evaluation (ultrasound, biopsy)."
            ),
            InputMetadata(
                field_name="symmetry",
                display_name="Prostate Symmetry",
                input_type=InputType.ENUM,
                required=False,
                description="Symmetry of prostate lobes on DRE",
                allowed_values=["symmetric", "asymmetric"],
                example="symmetric",
                help_text="Asymmetry may suggest focal pathology. Compare size and consistency of left and right lobes."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate DRE volume inputs."""

        # Check required fields
        is_valid, msg = self._validate_required(
            inputs, ["length_cm", "width_cm", "depth_cm"]
        )
        if not is_valid:
            return False, msg

        # Validate ranges
        for param, max_val in [
            ("length_cm", 8.0),
            ("width_cm", 6.0),
            ("depth_cm", 6.0),
        ]:
            is_valid, msg = self._validate_range(
                inputs[param], min_val=0.5, max_val=max_val, param_name=param
            )
            if not is_valid:
                return False, msg

        # Validate optional enum
        if "consistency" in inputs:
            is_valid, msg = self._validate_enum(
                inputs["consistency"],
                ["soft", "firm", "hard"],
                param_name="consistency"
            )
            if not is_valid:
                return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate DRE prostate volume."""

        length = float(inputs["length_cm"])
        width = float(inputs["width_cm"])
        depth = float(inputs["depth_cm"])

        # Calculate volume using standard formula
        # Volume (mL) = length × width × depth × 0.52
        # Coefficient 0.52 accounts for prolate spheroid shape
        volume_mL = length * width * depth * 0.52

        # Categorize size
        if volume_mL < 20:
            size_category = "Small"
            clinical_significance = "Minimal"
        elif volume_mL < 30:
            size_category = "Normal to Mildly Enlarged"
            clinical_significance = "Mild"
        elif volume_mL < 50:
            size_category = "Moderately Enlarged"
            clinical_significance = "Moderate"
        else:
            size_category = "Significantly Enlarged"
            clinical_significance = "Significant"

        # Consistency-based interpretation
        consistency = inputs.get("consistency", "not assessed")
        consistency_findings = []

        if consistency == "soft":
            consistency_findings.append("Soft consistency suggests benign hyperplasia")
        elif consistency == "firm":
            consistency_findings.append(
                "Firm consistency is typical of benign hyperplasia"
            )
        elif consistency == "hard":
            consistency_findings.append(
                "Hard or asymmetric areas warrant concern for malignancy"
            )

        # Nodularity
        nodularity = inputs.get("nodularity", "absent")
        nodule_findings = []
        if nodularity == "present":
            nodule_findings.append(
                "Nodularity detected - consider ultrasound or biopsy evaluation"
            )

        # Symmetry
        symmetry = inputs.get("symmetry", "symmetric")
        symmetry_findings = []
        if symmetry == "asymmetric":
            symmetry_findings.append(
                "Asymmetry detected - may suggest focal pathology"
            )

        # Build interpretation
        interpretation_parts = [
            f"DRE prostate volume estimated at {volume_mL:.1f} mL",
            f"Categorized as: {size_category}",
        ]

        interpretation_parts.extend(consistency_findings)
        interpretation_parts.extend(nodule_findings)
        interpretation_parts.extend(symmetry_findings)

        # Recommendations
        recommendations = []
        if volume_mL > 30:
            recommendations.append(
                "Consider PSA measurement if not recently done"
            )
            recommendations.append(
                "Ultrasound evaluation can provide more precise volume measurement"
            )
        if nodularity == "present" or consistency == "hard":
            recommendations.append("Consider PSA level assessment")
            recommendations.append(
                "Evaluation for prostate cancer may be indicated"
            )
        if volume_mL > 50:
            recommendations.append(
                "Consider imaging (TRUS or ultrasound) for surgical planning if intervention contemplated"
            )

        interpretation = ". ".join(interpretation_parts) + "."

        result = {
            "volume_mL": round(volume_mL, 1),
            "size_category": size_category,
            "clinical_significance": clinical_significance,
            "consistency": consistency,
            "nodularity": nodularity,
            "symmetry": symmetry,
        }

        # Determine risk level based on volume and exam findings
        if nodularity == "present" or consistency == "hard":
            risk_level = "Abnormal"
        elif volume_mL < 20:
            risk_level = "Normal"
        elif volume_mL < 30:
            risk_level = "Borderline"
        elif volume_mL < 50:
            risk_level = "Abnormal"
        else:
            risk_level = "Severely Abnormal"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=recommendations,
            references=self.references,
        )
