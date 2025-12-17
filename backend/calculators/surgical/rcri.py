from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator, CalculatorCategory, CalculatorResult,
    InputMetadata, InputType,
)

class RCRICalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Revised Cardiac Risk Index"
    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.SURGICAL_PLANNING
    @property
    def description(self) -> str:
        return "Assess perioperative cardiac risk"
    @property
    def references(self) -> List[str]:
        return ["Lee TH, et al. Derivation and prospective validation of a simple index for prediction of cardiac risk of major noncardiac surgery. Circulation. 1999;100:1043-1049"]
    @property
    def required_inputs(self) -> List[str]:
        return ["risk_factors_count"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get input schema for Revised Cardiac Risk Index."""
        return [
            InputMetadata("risk_factors_count", "Number of RCRI Risk Factors", InputType.NUMERIC, True, "Count of positive risk factors", unit="factors", min_value=0, max_value=6, example="2", help_text="Risk factors: high-risk surgery, CAD history, CHF, cerebrovascular disease, insulin-dependent DM, Cr >2. Higher count = higher MACE risk."),
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        try:
            count = int(inputs["risk_factors_count"])
            if count < 0 or count > 6: return False, "0-6 factors"
        except: return False, "Invalid"
        return True, None
    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        count = int(inputs["risk_factors_count"])
        mace_risk = {0: "0.4%", 1: "0.9%", 2: "6.6%", 3: "11%"}
        risk = mace_risk.get(min(count, 3), ">11%")

        if count == 0:
            risk_level = "Low"
        elif count == 1:
            risk_level = "Moderate"
        else:
            risk_level = "High"

        return CalculatorResult(calculator_id=self.calculator_id, calculator_name=self.name, result={"rcri_score": count, "mace_risk": risk}, interpretation=f"RCRI {count}: {risk} MACE risk.", risk_level=risk_level,
            references=self.references)
