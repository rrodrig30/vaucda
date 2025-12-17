"""Pelvic Floor Distress Inventory (PFDI) Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class PFDICalculator(ClinicalCalculator):
    """Pelvic Floor Distress Inventory-20 for pelvic floor symptoms."""

    @property
    def name(self) -> str:
        return "PFDI-20"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.FEMALE_UROLOGY

    @property
    def description(self) -> str:
        return "Assess pelvic floor disorder symptom distress and impact"

    @property
    def references(self) -> List[str]:
        return [
            "Barber MD, et al. Short forms of two condition-specific quality-of-life questionnaires for women with pelvic floor disorders (PFDI-20 and PFIQ-7). Am J Obstet Gynecol. 2005;193(1):103-113"
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["popdi_scores", "cradi_scores", "udi_scores"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for PFDI-20 calculator inputs."""
        return [
            InputMetadata(
                field_name="popdi_scores",
                display_name="POPDI Scores (6 items)",
                input_type=InputType.TEXT,
                required=True,
                description="Pelvic Organ Prolapse Distress Inventory scores (JSON array of 6 numbers)",
                unit="scores",
                example="[2, 1, 3, 1, 2, 2]",
                help_text="6 items assessing prolapse symptoms. Each scored 0-4 (0=not at all, 4=a great deal). Provide as JSON array of numbers."
            ),
            InputMetadata(
                field_name="cradi_scores",
                display_name="CRADI Scores (8 items)",
                input_type=InputType.TEXT,
                required=True,
                description="Colorectal-Anal Distress Inventory scores (JSON array of 8 numbers)",
                unit="scores",
                example="[1, 0, 2, 1, 1, 0, 2, 1]",
                help_text="8 items assessing bowel/anal symptoms. Each scored 0-4. Provide as JSON array of numbers."
            ),
            InputMetadata(
                field_name="udi_scores",
                display_name="UDI Scores (6 items)",
                input_type=InputType.TEXT,
                required=True,
                description="Urinary Distress Inventory scores (JSON array of 6 numbers)",
                unit="scores",
                example="[2, 3, 1, 2, 2, 1]",
                help_text="6 items assessing urinary symptoms. Each scored 0-4. Provide as JSON array of numbers."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        for subscale in ["popdi_scores", "cradi_scores", "udi_scores"]:
            if subscale not in inputs:
                return False, f"{subscale} required"
            if not isinstance(inputs[subscale], list):
                return False, f"{subscale} must be a list"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        # POPDI (Pelvic Organ Prolapse Distress Inventory) - 6 items
        popdi_scores = inputs["popdi_scores"]
        popdi_mean = sum(popdi_scores) / len(popdi_scores) if popdi_scores else 0
        popdi_scale = (popdi_mean - 1) * 25  # Scale 0-100

        # CRADI (Colorectal-Anal Distress Inventory) - 8 items
        cradi_scores = inputs["cradi_scores"]
        cradi_mean = sum(cradi_scores) / len(cradi_scores) if cradi_scores else 0
        cradi_scale = (cradi_mean - 1) * 25

        # UDI (Urinary Distress Inventory) - 6 items
        udi_scores = inputs["udi_scores"]
        udi_mean = sum(udi_scores) / len(udi_scores) if udi_scores else 0
        udi_scale = (udi_mean - 1) * 25

        # Total PFDI-20 score
        total_score = popdi_scale + cradi_scale + udi_scale

        if total_score < 50:
            severity = "Mild"
        elif total_score < 100:
            severity = "Moderate"
        elif total_score < 150:
            severity = "Severe"
        else:
            severity = "Very severe"

        interpretation = f"PFDI-20 Total: {total_score:.1f}/300. Severity: {severity}. POPDI: {popdi_scale:.1f}, CRADI: {cradi_scale:.1f}, UDI: {udi_scale:.1f}"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                "total_score": round(total_score, 1),
                "popdi_score": round(popdi_scale, 1),
                "cradi_score": round(cradi_scale, 1),
                "udi_score": round(udi_scale, 1),
                "severity": severity
            },
            interpretation=interpretation,
            risk_level=severity,
            references=self.references
        )
