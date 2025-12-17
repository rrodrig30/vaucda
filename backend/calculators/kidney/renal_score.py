"""
RENAL Nephrometry Score Calculator.

Scores renal masses based on five anatomic characteristics to predict
surgical complexity and guide management decisions.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class RENALScoreCalculator(ClinicalCalculator):
    """
    RENAL Nephrometry Score Calculator.

    Calculates complexity score (0-12) based on:
    - R: Radius (maximal diameter)
    - E: Exophytic/Endophytic
    - N: Nearness to collecting system
    - A: Anterior/Posterior (suffix, not scored)
    - L: Location relative to polar lines
    - h: Hilar (suffix)
    """

    @property
    def name(self) -> str:
        return "RENAL Nephrometry Score"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.KIDNEY_CANCER

    @property
    def description(self) -> str:
        return "Score renal mass complexity based on anatomic characteristics"

    @property
    def references(self) -> List[str]:
        return [
            "Kutcher R, et al. The RENAL Nephrometry Score: a comprehensive standardized system for assessing the complexity of renal masses. J Urol. 2009;182:844-853",
            "Okhunov Z, et al. RENAL Nephrometry Scoring System: prospective assessment of a new renal complexity scoring system. J Urol. 2011;186:861-867",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["radius_points", "exophytic_points", "nearness_points", "location_points"]

    @property
    def optional_inputs(self) -> List[str]:
        return ["anterior_posterior", "hilar"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for RENAL Nephrometry Score calculator inputs."""
        return [
            InputMetadata(
                field_name="radius_points",
                display_name="Radius Points",
                input_type=InputType.ENUM,
                required=True,
                description="Maximum tumor diameter in greatest dimension",
                allowed_values=[1, 2, 3],
                example="2",
                help_text="1 point: ≤4 cm. 2 points: >4 to <7 cm. 3 points: ≥7 cm. Larger tumors indicate higher surgical complexity."
            ),
            InputMetadata(
                field_name="exophytic_points",
                display_name="Exophytic Points",
                input_type=InputType.ENUM,
                required=True,
                description="Degree of tumor exophytism relative to kidney surface",
                allowed_values=[1, 2, 3],
                example="2",
                help_text="1 point: ≥50% exophytic (protruding). 2 points: <50% exophytic. 3 points: Entirely endophytic (within kidney). Endophytic tumors are more complex."
            ),
            InputMetadata(
                field_name="nearness_points",
                display_name="Nearness to Collecting System Points",
                input_type=InputType.ENUM,
                required=True,
                description="Distance from tumor to urinary collecting system and renal sinus",
                allowed_values=[1, 2, 3],
                example="1",
                help_text="1 point: ≥7 mm away. 2 points: >4 to <7 mm. 3 points: ≤4 mm. Close proximity increases complexity and risk of urine leak."
            ),
            InputMetadata(
                field_name="location_points",
                display_name="Location Relative to Polar Lines Points",
                input_type=InputType.ENUM,
                required=True,
                description="Anatomic location of tumor relative to upper and lower polar lines",
                allowed_values=[1, 2, 3],
                example="1",
                help_text="1 point: Entirely above or below polar line. 2 points: Crosses polar line. 3 points: >50% crosses midline or between polar lines. Central tumors are more complex."
            ),
            InputMetadata(
                field_name="anterior_posterior",
                display_name="Anterior/Posterior Location",
                input_type=InputType.ENUM,
                required=False,
                description="Anterior-posterior designation of tumor (suffix, not scored)",
                allowed_values=["anterior", "posterior", "indeterminate"],
                example="anterior",
                help_text="Anterior (a): Ventral aspect. Posterior (p): Dorsal aspect. Indeterminate: Cannot be clearly determined. This is descriptive only."
            ),
            InputMetadata(
                field_name="hilar",
                display_name="Hilar Involvement",
                input_type=InputType.ENUM,
                required=False,
                description="Indicates involvement of renal hilum or sinus",
                allowed_values=["no", "yes"],
                example="no",
                help_text="Hilar involvement indicates tumor at the renal hilum/sinus, significantly increasing surgical complexity and complications risk."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate RENAL score inputs."""

        # Check required fields
        is_valid, msg = self._validate_required(
            inputs,
            ["radius_points", "exophytic_points", "nearness_points", "location_points"]
        )
        if not is_valid:
            return False, msg

        # Validate point ranges
        for param, max_points in [
            ("radius_points", 3),
            ("exophytic_points", 3),
            ("nearness_points", 3),
            ("location_points", 3),
        ]:
            try:
                points = int(inputs[param])
                if points < 1 or points > max_points:
                    return False, f"{param} must be between 1 and {max_points}"
            except (ValueError, TypeError):
                return False, f"{param} must be an integer"

        # Validate optional enum fields
        if "anterior_posterior" in inputs:
            is_valid, msg = self._validate_enum(
                inputs["anterior_posterior"],
                ["anterior", "posterior", "indeterminate"],
                param_name="anterior_posterior"
            )
            if not is_valid:
                return False, msg

        if "hilar" in inputs:
            is_valid, msg = self._validate_enum(
                inputs["hilar"],
                ["no", "yes"],
                param_name="hilar"
            )
            if not is_valid:
                return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate RENAL Nephrometry Score."""

        radius_points = int(inputs["radius_points"])
        exophytic_points = int(inputs["exophytic_points"])
        nearness_points = int(inputs["nearness_points"])
        location_points = int(inputs["location_points"])

        # Total score
        total_score = radius_points + exophytic_points + nearness_points + location_points

        # Complexity classification
        if total_score <= 6:
            complexity = "Low"
            complexity_desc = "4-6 points"
            surgical_consideration = "Nephron-sparing surgery likely feasible"
        elif total_score <= 9:
            complexity = "Moderate"
            complexity_desc = "7-9 points"
            surgical_consideration = (
                "Nephron-sparing surgery feasible with appropriate approach"
            )
        else:
            complexity = "High"
            complexity_desc = "10-12 points"
            surgical_consideration = (
                "Nephron-sparing surgery challenging; consider radical nephrectomy"
            )

        # Component interpretation
        radius_desc = self._interpret_radius(radius_points)
        exo_desc = self._interpret_exophytic(exophytic_points)
        near_desc = self._interpret_nearness(nearness_points)
        loc_desc = self._interpret_location(location_points)

        # Hilar involvement
        hilar = inputs.get("hilar", "no")
        hilar_note = ""
        if hilar == "yes":
            hilar_note = "(with hilar involvement)"
            surgical_consideration += " - hilar involvement increases complexity"

        # A/P designation
        ap = inputs.get("anterior_posterior", "not specified")
        ap_note = f"({ap.capitalize()})" if ap != "not specified" else ""

        # Build interpretation
        interpretation_parts = [
            f"RENAL Nephrometry Score: {total_score} {ap_note}",
            f"Complexity Classification: {complexity} ({complexity_desc})",
            f"Radius component: {radius_desc}",
            f"Exophytic component: {exo_desc}",
            f"Nearness component: {near_desc}",
            f"Location component: {loc_desc}",
            hilar_note if hilar_note else "",
            f"Surgical consideration: {surgical_consideration}",
        ]

        # Filter out empty strings
        interpretation_parts = [p for p in interpretation_parts if p]

        result = {
            "total_score": total_score,
            "complexity": complexity,
            "radius_points": radius_points,
            "exophytic_points": exophytic_points,
            "nearness_points": nearness_points,
            "location_points": location_points,
            "anterior_posterior": ap,
            "hilar_involvement": hilar,
        }

        recommendations = [
            f"Surgical approach should be tailored to {complexity.lower()}-complexity lesion",
            "Consider patient comorbidities and renal function in treatment planning",
            "Discuss nephron-sparing vs. radical approach based on complexity and patient factors",
        ]

        if complexity == "High":
            recommendations.append(
                "Consider expert surgical consultation for treatment planning"
            )
            recommendations.append("Radical nephrectomy may be more appropriate")

        interpretation = ". ".join(interpretation_parts) + "."

        # Map complexity to risk_level
        if complexity == "Low":
            risk_level = "Low"
        elif complexity == "Moderate":
            risk_level = "Intermediate"
        else:  # High
            risk_level = "High"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            category=complexity,
            risk_level=risk_level,
            recommendations=recommendations,
            references=self.references,
        )

    @staticmethod
    def _interpret_radius(points: int) -> str:
        """Interpret radius scoring."""
        if points == 1:
            return "≤4 cm (1 point)"
        elif points == 2:
            return ">4 to <7 cm (2 points)"
        else:
            return "≥7 cm (3 points)"

    @staticmethod
    def _interpret_exophytic(points: int) -> str:
        """Interpret exophytic scoring."""
        if points == 1:
            return "≥50% exophytic (1 point)"
        elif points == 2:
            return "<50% exophytic (2 points)"
        else:
            return "Entirely endophytic (3 points)"

    @staticmethod
    def _interpret_nearness(points: int) -> str:
        """Interpret nearness to collecting system."""
        if points == 1:
            return "≥7 mm from collecting system (1 point)"
        elif points == 2:
            return ">4 to <7 mm (2 points)"
        else:
            return "≤4 mm (3 points)"

    @staticmethod
    def _interpret_location(points: int) -> str:
        """Interpret location relative to polar lines."""
        if points == 1:
            return "Entirely above/below polar line (1 point)"
        elif points == 2:
            return "Crosses polar line (2 points)"
        else:
            return ">50% crosses midline or between polar lines (3 points)"
