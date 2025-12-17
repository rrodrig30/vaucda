from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class TTEvaluationCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Testosterone Evaluation Algorithm"
    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.HYPOGONADISM
    @property
    def description(self) -> str:
        return "Diagnose testosterone deficiency and classify etiology"
    @property
    def references(self) -> List[str]:
        return ["Bhasin S, et al. Testosterone replacement therapy. J Clin Endocrinol Metab. 2018;103:1715-1744"]
    @property
    def required_inputs(self) -> List[str]:
        return ["total_testosterone", "age"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Testosterone Evaluation Algorithm calculator inputs."""
        return [
            InputMetadata(
                field_name="total_testosterone",
                display_name="Total Testosterone",
                input_type=InputType.NUMERIC,
                required=True,
                description="Serum total testosterone level",
                unit="ng/dL",
                min_value=0,
                max_value=1500,
                example="280",
                help_text="<300 ng/dL indicates hypogonadism. Check LH/FSH to determine primary vs. secondary."
            ),
            InputMetadata(
                field_name="age",
                display_name="Age",
                input_type=InputType.NUMERIC,
                required=True,
                description="Patient age in years",
                unit="years",
                min_value=18,
                max_value=120,
                example="55",
                help_text="Testosterone declines ~1% per year after age 30. Interpretation age-adjusted."
            ),
            InputMetadata(
                field_name="lh",
                display_name="LH (Optional)",
                input_type=InputType.NUMERIC,
                required=False,
                description="Luteinizing hormone level",
                unit="mIU/mL",
                min_value=0,
                max_value=50,
                example="3.5",
                help_text="Normal: 1.7-8.6 mIU/mL. Elevated (>8.6) with low T = primary hypogonadism. Low (<1.7) = secondary."
            ),
            InputMetadata(
                field_name="fsh",
                display_name="FSH (Optional)",
                input_type=InputType.NUMERIC,
                required=False,
                description="Follicle-stimulating hormone level",
                unit="mIU/mL",
                min_value=0,
                max_value=50,
                example="2.8",
                help_text="Normal: 1.7-8.6 mIU/mL. Elevated FSH with low T suggests testicular failure."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = ["total_testosterone", "age"]
        for field in required:
            if field not in inputs:
                return False, f"{field} is required"

        try:
            t = float(inputs.get("total_testosterone", 0))
            if t < 0 or t > 1500:
                return False, "total_testosterone must be 0-1500"

            age = int(inputs.get("age", 0))
            if age < 18 or age > 120:
                return False, "age must be 18-120"
        except:
            return False, "Invalid input values"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        testosterone = float(inputs.get("total_testosterone", 0))
        age = int(inputs.get("age", 50))
        lh = float(inputs.get("lh", 5.0))
        fsh = float(inputs.get("fsh", 5.0))

        # Testosterone evaluation based on Endocrine Society 2018 guidelines
        if testosterone < 300:
            if lh > 8.6:
                diagnosis = "Primary hypogonadism (elevated LH)"
                risk_level = "high"
            elif lh < 1.7:
                diagnosis = "Secondary hypogonadism (low LH)"
                risk_level = "high"
            else:
                diagnosis = "Possible compensated hypogonadism"
                risk_level = "moderate"
        elif testosterone < 400:
            diagnosis = "Borderline testosterone"
            risk_level = "moderate"
        else:
            diagnosis = "Normal testosterone"
            risk_level = "low"

        result = {
            'total_testosterone_ng_dl': testosterone,
            'age': age,
            'diagnosis': diagnosis,
            'lh': lh,
            'fsh': fsh
        }

        interpretation = f"Testosterone level {testosterone} ng/dL in {age}-year-old: {diagnosis}"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=[
                "Repeat morning testosterone testing if low",
                "Check LH/FSH if testosterone <300 ng/dL",
                "Consider testosterone replacement if symptomatic with low levels"
            ],
            references=self.references
        )
