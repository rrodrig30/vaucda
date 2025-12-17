from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class SemenAnalysisCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "WHO 2021 Semen Analysis Interpretation"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_FERTILITY

    @property
    def description(self) -> str:
        return "Interpret semen analysis parameters using WHO 2021 criteria"

    @property
    def references(self) -> List[str]:
        return ["WHO. World Health Organization Laboratory Manual. 6th ed. 2021"]

    @property
    def required_inputs(self) -> List[str]:
        return ["volume_ml", "concentration", "progressive_motility", "normal_morphology"]

    @property
    def optional_inputs(self) -> List[str]:
        return ["total_count", "total_motility", "vitality_percent"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for WHO 2021 Semen Analysis Interpretation calculator inputs."""
        return [
            InputMetadata(
                field_name="volume_ml",
                display_name="Semen Volume",
                input_type=InputType.NUMERIC,
                required=True,
                description="Total volume of ejaculate",
                unit="mL",
                min_value=0.1,
                max_value=10,
                example="2.5",
                help_text="WHO 2021 normal: >=1.5 mL. <1.5 mL = hypospermia (low volume)."
            ),
            InputMetadata(
                field_name="concentration",
                display_name="Sperm Concentration",
                input_type=InputType.NUMERIC,
                required=True,
                description="Sperm concentration per milliliter",
                unit="million/mL",
                min_value=0,
                max_value=500,
                example="25",
                help_text="WHO 2021 normal: >=15 million/mL. <15 = oligozoospermia (low sperm count)."
            ),
            InputMetadata(
                field_name="progressive_motility",
                display_name="Progressive Motility",
                input_type=InputType.NUMERIC,
                required=True,
                description="Percentage of sperm with forward progressive movement",
                unit="%",
                min_value=0,
                max_value=100,
                example="45",
                help_text="WHO 2021 normal: >=32%. <32% = asthenozoospermia (poor sperm motility)."
            ),
            InputMetadata(
                field_name="normal_morphology",
                display_name="Normal Sperm Morphology",
                input_type=InputType.NUMERIC,
                required=True,
                description="Percentage of sperm with normal morphology",
                unit="%",
                min_value=0,
                max_value=100,
                example="6",
                help_text="WHO 2021 normal: >=4%. <4% = teratozoospermia (abnormal sperm shape)."
            ),
            InputMetadata(
                field_name="total_count",
                display_name="Total Sperm Count (Optional)",
                input_type=InputType.NUMERIC,
                required=False,
                description="Total number of sperm in ejaculate",
                unit="million",
                min_value=0,
                max_value=10000,
                example="60",
                help_text="If not provided, calculated as volume × concentration. WHO 2021 normal: >=39 million total."
            ),
            InputMetadata(
                field_name="total_motility",
                display_name="Total Motility (Optional)",
                input_type=InputType.NUMERIC,
                required=False,
                description="Total percentage of motile sperm (progressive + non-progressive)",
                unit="%",
                min_value=0,
                max_value=100,
                example="50",
                help_text="WHO 2021 normal: >=40%. If not provided, use progressive motility."
            ),
            InputMetadata(
                field_name="vitality_percent",
                display_name="Vitality (Optional)",
                input_type=InputType.NUMERIC,
                required=False,
                description="Percentage of live (viable) sperm",
                unit="%",
                min_value=0,
                max_value=100,
                example="60",
                help_text="WHO 2021 normal: >=54% live. <54% = necrozoospermia (high sperm death rate)."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = self.required_inputs
        for field in required:
            if field not in inputs:
                return False, f"{field} is required"

        for param in self.required_inputs:
            is_valid, msg = self._validate_range(inputs[param], 0, 500, param)
            if not is_valid:
                return False, msg
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        # Support both parameter name variations
        vol = float(inputs.get("volume_ml") or inputs.get("volume", 0))
        conc = float(inputs.get("concentration", 0))
        prog_mot = float(inputs.get("progressive_motility", inputs.get("motility_progressive", 0)))
        morph = float(inputs.get("normal_morphology") or inputs.get("morphology", 0))

        # Optional parameters
        total_mot = float(inputs.get("total_motility", prog_mot))
        vitality = float(inputs.get("vitality_percent", 50))

        # Calculate or use provided total count
        if "total_count" in inputs:
            total_count = float(inputs["total_count"])
        else:
            total_count = vol * conc

        # Determine abnormalities based on WHO 2021 criteria
        findings = []
        interpretation_parts = []

        # Volume: ≥1.5 mL (normal)
        if vol < 1.5:
            findings.append("Hypospermia")
            interpretation_parts.append(f"Low semen volume: {vol:.1f} mL (normal ≥1.5 mL)")

        # Concentration: ≥15 million/mL
        if conc < 15:
            findings.append("Oligozoospermia")
            interpretation_parts.append(f"Low sperm concentration: {conc:.0f} million/mL (normal ≥15 million/mL)")

        # Total Count: ≥39 million/ejaculate
        if total_count < 39:
            if "Oligozoospermia" not in findings:
                findings.append("Low total sperm count")
            interpretation_parts.append(f"Low total sperm count: {total_count:.0f} million (normal ≥39 million)")

        # Progressive Motility: ≥32%
        if prog_mot < 32:
            findings.append("Asthenozoospermia")
            interpretation_parts.append(f"Poor progressive motility: {prog_mot:.0f}% (normal ≥32%)")

        # Total Motility: ≥40%
        if total_mot < 40:
            if "Asthenozoospermia" not in findings:
                interpretation_parts.append(f"Reduced total motility: {total_mot:.0f}% (normal ≥40%)")

        # Morphology: ≥4% normal forms
        if morph < 4:
            findings.append("Teratozoospermia")
            interpretation_parts.append(f"Poor sperm morphology: {morph:.0f}% normal (normal ≥4%)")

        # Vitality: ≥54% live
        if vitality < 54:
            interpretation_parts.append(f"Reduced vitality: {vitality:.0f}% live (normal ≥54%)")

        # Determine diagnosis
        if not findings:
            diagnosis = "Normozoospermia"
            risk_level = "Normal"
            interpretation = "Normal semen analysis. All parameters within WHO 2021 reference ranges."
        else:
            diagnosis = "; ".join(findings)
            risk_level = "Abnormal"
            interpretation = f"Semen Analysis Interpretation: {diagnosis}. "
            if interpretation_parts:
                interpretation += ". ".join(interpretation_parts)

        # Special case: Azoospermia (zero sperm count)
        if total_count == 0 or conc == 0:
            diagnosis = "Azoospermia"
            risk_level = "Severely Abnormal"
            interpretation = "Azoospermia: No sperm present in ejaculate. Requires further evaluation (obstructive vs. non-obstructive)."

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                "diagnosis": diagnosis,
                "total_count": round(total_count, 2),
                "concentration": round(conc, 2),
                "volume_ml": round(vol, 2),
                "progressive_motility": round(prog_mot, 1),
                "normal_morphology": round(morph, 1),
                "findings": findings
            },
            interpretation=interpretation,
            recommendations=["Repeat if abnormal", "Hormonal evaluation if indicated", "Consider assisted reproductive techniques if needed"],
            risk_level=risk_level,
            references=self.references
        )
