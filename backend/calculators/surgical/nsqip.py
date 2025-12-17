from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator, CalculatorCategory, CalculatorResult,
    InputMetadata, InputType,
)

class NSQIPCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "NSQIP Risk Calculator Link"
    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.SURGICAL_PLANNING
    @property
    def description(self) -> str:
        return "Link to ACS NSQIP Surgical Risk Calculator"
    @property
    def references(self) -> List[str]:
        return ["https://riskcalculator.facs.org/"]
    @property
    def required_inputs(self) -> List[str]:
        return ["procedure_cpt"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get input schema for NSQIP Risk Calculator."""
        return [
            InputMetadata(
                field_name="procedure_cpt",
                display_name="Procedure CPT Code",
                input_type=InputType.TEXT,
                required=True,
                description="CPT code for procedure",
                example="27447",
                help_text="Enter CPT code for proposed procedure (e.g. 27447 for total knee arthroplasty). Visit https://riskcalculator.facs.org/ for full risk calculation."
            ),
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = self.required_inputs
        for field in required:
            if field not in inputs:
                return False, f"{field} is required"
        return True, None
    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        cpt = inputs.get("procedure_cpt", "Unknown")
        interpretation = f"For detailed perioperative risk assessment using CPT {cpt}, visit https://riskcalculator.facs.org/ (ACS NSQIP Risk Calculator)"
        risk_level = "Normal"
        return CalculatorResult(calculator_id=self.calculator_id, calculator_name=self.name, result={"calculator_url": "https://riskcalculator.facs.org/"}, interpretation=interpretation, recommendations=["Use online ACS NSQIP calculator at https://riskcalculator.facs.org/"], risk_level=risk_level,
            references=self.references)
