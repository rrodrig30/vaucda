"""Testosterone Evaluation Calculator for Fertility Assessment."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class TestosteroneCalculator(ClinicalCalculator):
    """Testosterone evaluation for male fertility assessment."""

    @property
    def name(self) -> str:
        return "Testosterone Fertility Evaluation"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_FERTILITY

    @property
    def description(self) -> str:
        return "Evaluate testosterone levels in context of male fertility"

    @property
    def references(self) -> List[str]:
        return [
            "Bhasin S, et al. Testosterone therapy in men with hypogonadism: an Endocrine Society clinical practice guideline. J Clin Endocrinol Metab. 2018;103(5):1715-1744"
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["total_testosterone", "age"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Testosterone Fertility Evaluation calculator inputs."""
        return [
            InputMetadata(
                field_name="total_testosterone",
                display_name="Total Testosterone",
                input_type=InputType.NUMERIC,
                required=True,
                description="Serum total testosterone level",
                unit="ng/dL",
                min_value=0,
                max_value=2000,
                example="350",
                help_text="Normal: 300-1000 ng/dL. <200 ng/dL = severe deficiency affecting fertility."
            ),
            InputMetadata(
                field_name="age",
                display_name="Age",
                input_type=InputType.NUMERIC,
                required=True,
                description="Patient age",
                unit="years",
                min_value=18,
                max_value=120,
                example="45",
                help_text="Age-adjusted interpretation. Lower age has higher normal range. <30: >=300 ng/dL expected."
            ),
            InputMetadata(
                field_name="free_testosterone",
                display_name="Free Testosterone (Optional)",
                input_type=InputType.NUMERIC,
                required=False,
                description="Serum free testosterone level",
                unit="pg/mL",
                min_value=0,
                max_value=100,
                example="8.5",
                help_text="Normal: 8.7-25 pg/mL. More specific indicator of bioavailable testosterone."
            ),
            InputMetadata(
                field_name="shbg",
                display_name="SHBG (Optional)",
                input_type=InputType.NUMERIC,
                required=False,
                description="Sex hormone-binding globulin",
                unit="nmol/L",
                min_value=0,
                max_value=200,
                example="45",
                help_text="Normal: 24.6-122 nmol/L. Affects free testosterone calculation and bioavailability."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if "total_testosterone" not in inputs or inputs["total_testosterone"] < 0:
            return False, "Total testosterone must be >= 0 ng/dL"
        if "age" not in inputs or inputs["age"] < 18:
            return False, "Age must be >= 18"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        total_t = inputs["total_testosterone"]
        age = inputs["age"]
        free_t = inputs.get("free_testosterone")
        shbg = inputs.get("shbg")

        # Classification based on total testosterone
        if total_t < 200:
            t_status = "Severely low"
            fertility_impact = "High"
        elif total_t < 300:
            t_status = "Low"
            fertility_impact = "Moderate to High"
        elif total_t < 350:
            t_status = "Borderline low"
            fertility_impact = "Moderate"
        elif total_t < 1000:
            t_status = "Normal"
            fertility_impact = "Minimal"
        else:
            t_status = "Elevated"
            fertility_impact = "Variable"

        # Age-adjusted interpretation
        if age < 30:
            lower_limit = 300
        elif age < 40:
            lower_limit = 280
        elif age < 50:
            lower_limit = 260
        else:
            lower_limit = 240

        interpretation = f"Total testosterone: {total_t} ng/dL. Status: {t_status}. "
        interpretation += f"Age-adjusted lower limit: {lower_limit} ng/dL. "
        interpretation += f"Fertility impact: {fertility_impact}."

        if total_t < lower_limit:
            interpretation += " Consider further evaluation and possible treatment."

        result_data = {
            "total_testosterone": total_t,
            "testosterone_status": t_status,
            "fertility_impact": fertility_impact,
            "age_adjusted_lower_limit": lower_limit
        }

        if free_t is not None:
            result_data["free_testosterone"] = free_t
        if shbg is not None:
            result_data["shbg"] = shbg

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result_data,
            interpretation=interpretation,
            risk_level=t_status,
            references=self.references
        )
