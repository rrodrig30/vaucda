from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class HormonalEvalCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Male Fertility Hormonal Evaluation"
    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_FERTILITY
    @property
    def description(self) -> str:
        return "Interpret male fertility hormone panel"
    @property
    def references(self) -> List[str]:
        return ["Andrology American Society. Male Infertility Evaluation"]
    @property
    def required_inputs(self) -> List[str]:
        return ["testosterone", "fsh", "lh"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Male Fertility Hormonal Evaluation calculator inputs."""
        return [
            InputMetadata(
                field_name="testosterone",
                display_name="Total Testosterone",
                input_type=InputType.NUMERIC,
                required=True,
                description="Serum total testosterone level",
                unit="ng/dL",
                min_value=0,
                max_value=1000,
                example="450",
                help_text="Normal range: 300-1000 ng/dL. <300 indicates hypogonadism affecting fertility."
            ),
            InputMetadata(
                field_name="fsh",
                display_name="FSH",
                input_type=InputType.NUMERIC,
                required=True,
                description="Follicle-stimulating hormone level",
                unit="mIU/mL",
                min_value=0,
                max_value=100,
                example="5.5",
                help_text="Normal range: 1.7-8.6 mIU/mL. >7.6 suggests testicular failure (primary hypogonadism)."
            ),
            InputMetadata(
                field_name="lh",
                display_name="LH",
                input_type=InputType.NUMERIC,
                required=True,
                description="Luteinizing hormone level",
                unit="mIU/mL",
                min_value=0,
                max_value=100,
                example="6.0",
                help_text="Normal range: 1.7-8.6 mIU/mL. Elevated LH may indicate testicular failure."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        for p in self.required_inputs:
            is_valid, msg = self._validate_range(inputs[p], 0, 1000, p)
            if not is_valid: return False, msg
        return True, None
    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        t, fsh, lh = float(inputs["testosterone"]), float(inputs["fsh"]), float(inputs["lh"])
        findings = []
        if t < 300: findings.append("Low testosterone")
        if fsh > 7.6: findings.append("Elevated FSH (testicular failure)")
        if lh > 8.6: findings.append("Elevated LH")
        pattern = "; ".join(findings) if findings else "Normal hormonal pattern"
        overall_status = "Abnormal" if findings else "Normal"
        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={"pattern": pattern},
            interpretation=f"Hormonal pattern: {pattern}",
            recommendations=["Repeat if abnormal", "Imaging if secondary hypogonadism"],
            risk_level=overall_status,
            references=self.references
        )
