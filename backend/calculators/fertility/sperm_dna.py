from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class SpermDNACalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Sperm DNA Fragmentation Index"
    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_FERTILITY
    @property
    def description(self) -> str:
        return "Assess sperm DNA fragmentation"
    @property
    def references(self) -> List[str]:
        return ["Agarwal A, et al. Sperm DNA fragmentation. Fertil Steril. 2016;105:53-69"]
    @property
    def required_inputs(self) -> List[str]:
        return ["dfi_percent"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Sperm DNA Fragmentation Index calculator inputs."""
        return [
            InputMetadata(
                field_name="dfi_percent",
                display_name="DNA Fragmentation Index",
                input_type=InputType.NUMERIC,
                required=True,
                description="Percentage of sperm with fragmented DNA",
                unit="%",
                min_value=0,
                max_value=100,
                example="18",
                help_text="<15% = Normal (good fertility prognosis). 15-25% = Elevated (borderline, may reduce fertility). >25% = High (likely fertility impact, ICSI recommended)."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = self.required_inputs
        for field in required:
            if field not in inputs:
                return False, f"{field} is required"
        return self._validate_range(inputs["dfi_percent"], 0, 100, "DFI")
    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        dfi = float(inputs["dfi_percent"])
        if dfi < 15:
            cat, rec, interp = "Low", "Natural conception possible", f"Low DNA fragmentation (DFI {dfi:.1f}%). Normal range, good prognosis."
            risk_level = "Normal"
        elif dfi < 25:
            cat, rec, interp = "Elevated", "May need assistance", f"Elevated DNA fragmentation (DFI {dfi:.1f}%). Borderline range, may impact fertility."
            risk_level = "Abnormal"
        else:
            cat, rec, interp = "High", "ICSI recommended", f"High DNA fragmentation (DFI {dfi:.1f}%). Likely to impact fertility."
            risk_level = "Severely Abnormal"
        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={"dfi_percent": dfi, "category": cat},
            interpretation=interp,
            recommendations=[rec],
            risk_level=risk_level,
            references=self.references
        )
