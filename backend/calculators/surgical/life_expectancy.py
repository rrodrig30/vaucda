from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator, CalculatorCategory, CalculatorResult,
    InputMetadata, InputType,
)

class LifeExpectancyCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Life Expectancy Calculator"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.SURGICAL_PLANNING

    @property
    def description(self) -> str:
        return "Estimate life expectancy based on age, gender, and health status"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def references(self) -> List[str]:
        return ["Lee SJ, et al. Development and validation of a prognostic index for 4-year mortality. JAMA. 2006;295(7):801-808",
                "Social Security Administration Actuarial Life Tables"]

    @property
    def required_inputs(self) -> List[str]:
        return ["age", "gender", "health_status", "comorbidities"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get input schema for Life Expectancy Calculator."""
        return [
            InputMetadata("age", "Age", InputType.NUMERIC, True, "Patient age", unit="years", min_value=40, max_value=100, example="70", help_text="Baseline life expectancy determined from actuarial tables."),
            InputMetadata("gender", "Gender", InputType.ENUM, True, "Biological sex", allowed_values=["male", "female"], example="male", help_text="Women typically have longer life expectancy."),
            InputMetadata("health_status", "Health Status", InputType.ENUM, True, "Overall health", allowed_values=["excellent", "good", "fair", "poor"], example="good", help_text="Excellent to poor. Significantly impacts mortality."),
            InputMetadata("comorbidities", "Number of Comorbidities", InputType.NUMERIC, True, "Count of significant conditions", unit="conditions", min_value=0, max_value=20, example="2", help_text="Each condition reduces life expectancy."),
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        is_valid, msg = self._validate_range(inputs.get("age", 0), 40, 100, "age")
        if not is_valid:
            return False, msg

        gender = inputs.get("gender", "").lower()
        if gender not in ["male", "female"]:
            return False, "gender must be 'male' or 'female'"

        health = inputs.get("health_status", "").lower()
        if health not in ["excellent", "good", "fair", "poor"]:
            return False, "health_status must be 'excellent', 'good', 'fair', or 'poor'"

        is_valid, msg = self._validate_range(inputs.get("comorbidities", 0), 0, 20, "comorbidities")
        return is_valid, msg

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        age = int(float(inputs.get("age", 65)))
        gender = inputs.get("gender", "").lower()
        health_status = inputs.get("health_status", "").lower()
        comorbidities = int(inputs.get("comorbidities", 0))

        # Base life expectancy by age and gender (from SSA tables)
        base_le_table = {
            (65, "male"): 17.5,
            (65, "female"): 20.3,
            (75, "male"): 9.5,
            (75, "female"): 11.5,
            (85, "male"): 4.5,
            (85, "female"): 5.5,
        }

        # Find base life expectancy
        base_le = 10  # default
        for (age_threshold, gender_key), le in sorted(base_le_table.items(), reverse=True):
            if age >= age_threshold and gender == gender_key:
                base_le = le
                break

        # Adjust for health status
        health_adjustment = {
            "excellent": 0.9,  # 10% better than average
            "good": 0.95,       # 5% better
            "fair": 1.05,       # 5% worse
            "poor": 1.2,        # 20% worse
        }
        health_factor = health_adjustment.get(health_status, 1.0)

        # Adjust for comorbidities (roughly 0.5 years per condition)
        comorbidity_adjustment = comorbidities * 0.5

        # Calculate adjusted life expectancy
        adjusted_le = max(0, (base_le * health_factor) - comorbidity_adjustment)

        # Determine risk category
        if adjusted_le > 15:
            risk_category = "Good prognosis"
            risk_level = "low"
        elif adjusted_le > 5:
            risk_category = "Moderate prognosis"
            risk_level = "moderate"
        else:
            risk_category = "Limited prognosis"
            risk_level = "high"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                'age': age,
                'gender': gender,
                'base_life_expectancy_years': round(base_le, 1),
                'adjusted_life_expectancy_years': round(adjusted_le, 1),
                'risk_category': risk_category
            },
            interpretation=f"Estimated life expectancy: {adjusted_le:.1f} years based on age {age}, {health_status} health status, and {comorbidities} comorbidities",
            risk_level=risk_level,
            recommendations=[
                "Use for surgical decision-making and goals of care discussions",
                "Should not be sole factor in treatment decisions",
                "Discuss with patient and family"
            ],
            references=self.references
        )
