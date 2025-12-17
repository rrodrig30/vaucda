from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class HypogonadismRiskCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "LOH Diagnostic Algorithm"
    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.HYPOGONADISM
    @property
    def description(self) -> str:
        return "Diagnose late-onset hypogonadism"
    @property
    def references(self) -> List[str]:
        return ["Bhasin S. Diagnosis of late-onset hypogonadism. J Clin Endocrinol Metab. 2006;91:1681-1684"]
    @property
    def required_inputs(self) -> List[str]:
        return ["age", "testosterone", "symptoms"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for LOH Diagnostic Algorithm calculator inputs."""
        return [
            InputMetadata(
                field_name="age",
                display_name="Age",
                input_type=InputType.NUMERIC,
                required=True,
                description="Patient age in years",
                unit="years",
                min_value=18,
                max_value=120,
                example="65",
                help_text="Late-onset hypogonadism typically occurs in men >50 years."
            ),
            InputMetadata(
                field_name="testosterone",
                display_name="Total Testosterone",
                input_type=InputType.NUMERIC,
                required=True,
                description="Serum total testosterone level",
                unit="ng/dL",
                min_value=0,
                max_value=1500,
                example="250",
                help_text="<300 ng/dL with symptoms = confirmed hypogonadism. 300-400 borderline."
            ),
            InputMetadata(
                field_name="symptoms",
                display_name="Symptom Count",
                input_type=InputType.NUMERIC,
                required=True,
                description="Number of clinical symptoms of hypogonadism present",
                unit="count",
                min_value=0,
                max_value=10,
                example="3",
                help_text="Symptoms: decreased libido, erection weakness, low energy, decreased strength, mood changes. >=2 with T<300 = diagnosis."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = ["age", "testosterone", "symptoms"]
        for field in required:
            if field not in inputs:
                return False, f"{field} is required"

        try:
            age = int(inputs.get("age", 0))
            if age < 18 or age > 120:
                return False, "age must be 18-120"

            t = float(inputs.get("testosterone", 0))
            if t < 0 or t > 1500:
                return False, "testosterone must be 0-1500"

            symptoms = int(inputs.get("symptoms", 0))
            if symptoms < 0 or symptoms > 10:
                return False, "symptoms must be 0-10"
        except:
            return False, "Invalid input values"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        age = int(inputs.get("age", 50))
        testosterone = float(inputs.get("testosterone", 400))
        symptoms = int(inputs.get("symptoms", 0))

        # Hypogonadism diagnosis based on testosterone levels and symptoms
        if testosterone < 300:
            if symptoms >= 2:
                diagnosis = "Confirmed hypogonadism"
                risk_level = "high"
            else:
                diagnosis = "Low testosterone without symptoms"
                risk_level = "moderate"
        elif testosterone < 400:
            if symptoms >= 3:
                diagnosis = "Possible hypogonadism"
                risk_level = "moderate"
            else:
                diagnosis = "Borderline testosterone"
                risk_level = "low"
        else:
            diagnosis = "Normal testosterone"
            risk_level = "low"

        result = {
            'age': age,
            'testosterone_ng_dl': testosterone,
            'symptom_count': symptoms,
            'diagnosis': diagnosis
        }

        interpretation = f"Hypogonadism Risk: {diagnosis}. Age {age}, Testosterone {testosterone} ng/dL, {symptoms} symptoms reported."

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=["Recheck testosterone level with morning sample", "Consider endocrinology referral if confirmed low", "Discuss testosterone replacement therapy options"],
            references=self.references
        )
