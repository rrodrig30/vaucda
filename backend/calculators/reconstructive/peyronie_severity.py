from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class PeyronieCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Peyronie's Disease Severity Assessment"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.RECONSTRUCTIVE

    @property
    def description(self) -> str:
        return "Assess severity and impact of Peyronie's disease based on curvature and functional impairment"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def references(self) -> List[str]:
        return ["Mulhall JP, et al. Peyronie's disease. Nat Clin Pract Urol. 2006;3(8):432-443",
                "Lue TF. Peyronie's disease: An update. J Sex Med. 2005;2:110-120"]

    @property
    def required_inputs(self) -> List[str]:
        return ["curvature_degrees", "plaque_size_cm", "functional_impairment", "duration_months"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Peyronie's Disease Severity Assessment calculator inputs."""
        return [
            InputMetadata(
                field_name="curvature_degrees",
                display_name="Penile Curvature Angle",
                input_type=InputType.NUMERIC,
                required=True,
                description="Maximum angle of penile curvature measured in erect state",
                unit="degrees",
                min_value=0,
                max_value=180,
                example="35",
                help_text="Normal: 0-5 degrees. Mild: <20 degrees. Moderate: 20-40 degrees. Severe: >40 degrees. Severity correlates with functional impairment."
            ),
            InputMetadata(
                field_name="plaque_size_cm",
                display_name="Palpable Plaque Size",
                input_type=InputType.NUMERIC,
                required=True,
                description="Maximum diameter of palpable penile plaque",
                unit="cm",
                min_value=0,
                max_value=10,
                example="2.5",
                help_text="Plaque size measured by palpation. Larger plaques may indicate more advanced disease. Impacts treatment decisions."
            ),
            InputMetadata(
                field_name="functional_impairment",
                display_name="Functional Impairment Level",
                input_type=InputType.ENUM,
                required=True,
                description="Degree of erectile/sexual dysfunction related to disease",
                allowed_values=["none", "mild", "moderate", "severe"],
                example="moderate",
                help_text="None: No dysfunction. Mild: Minimal impact. Moderate: Significant impact on intercourse. Severe: Complete inability. Guides treatment."
            ),
            InputMetadata(
                field_name="duration_months",
                display_name="Disease Duration",
                input_type=InputType.NUMERIC,
                required=True,
                description="Time since onset of Peyronie's disease symptoms",
                unit="months",
                min_value=0,
                max_value=240,
                example="12",
                help_text="Early phase (<12 months) may respond to medical therapy. Chronic phase (>12 months) usually requires surgical intervention."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = ["curvature_degrees", "plaque_size_cm", "functional_impairment", "duration_months"]
        for key in required:
            if key not in inputs:
                return False, f"Missing required input: {key}"

        try:
            curve = float(inputs.get("curvature_degrees", 0))
            if curve < 0 or curve > 180:
                return False, "curvature_degrees must be 0-180"

            plaque = float(inputs.get("plaque_size_cm", 0))
            if plaque < 0 or plaque > 10:
                return False, "plaque_size_cm must be 0-10"

            duration = int(inputs.get("duration_months", 0))
            if duration < 0 or duration > 240:
                return False, "duration_months must be 0-240"
        except (ValueError, TypeError):
            return False, "Invalid numeric inputs"

        valid_impairment = ["none", "mild", "moderate", "severe"]
        if inputs.get("functional_impairment", "").lower() not in valid_impairment:
            return False, f"functional_impairment must be one of {valid_impairment}"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        curvature = float(inputs.get("curvature_degrees", 0))
        plaque_size = float(inputs.get("plaque_size_cm", 0))
        functional_impairment = inputs.get("functional_impairment", "").lower()
        duration = int(inputs.get("duration_months", 0))

        # Determine severity based on curvature
        if curvature < 20:
            curvature_severity = "Mild"
            curve_points = 1
        elif curvature < 40:
            curvature_severity = "Moderate"
            curve_points = 2
        else:
            curvature_severity = "Severe"
            curve_points = 3

        # Determine functional impact
        impact_score = 0
        if functional_impairment == "none":
            impact_score = 0
        elif functional_impairment == "mild":
            impact_score = 1
        elif functional_impairment == "moderate":
            impact_score = 2
        else:  # severe
            impact_score = 3

        # Overall severity
        total_score = curve_points + impact_score

        if total_score <= 2:
            severity = "Mild"
            risk_level = "low"
            recommendation = "Observation, PDE5i, or topical treatments"
        elif total_score <= 4:
            severity = "Moderate"
            risk_level = "moderate"
            recommendation = "Consider medical or surgical intervention"
        else:
            severity = "Severe"
            risk_level = "high"
            recommendation = "Surgical intervention recommended"

        interpretation = f"Peyronie's disease severity: {severity}. Curvature: {curvature_severity}. Functional impairment: {functional_impairment}."

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                'curvature_degrees': curvature,
                'curvature_severity': curvature_severity,
                'plaque_size_cm': plaque_size,
                'functional_impairment': functional_impairment,
                'overall_severity': severity
            },
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=[recommendation, "Regular follow-up assessment recommended"],
            references=self.references
        )
