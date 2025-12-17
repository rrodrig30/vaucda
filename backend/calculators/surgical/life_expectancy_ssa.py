"""
SSA Actuarial Life Expectancy Calculator

Based on Social Security Administration Period Life Tables (2024)
and CDC National Vital Statistics System data.

References:
- Social Security Administration. Period Life Tables, 2024.
  https://www.ssa.gov/oact/HistEst/PerLifeTables/2024/PerLifeTables2024.html
- CDC National Vital Statistics Reports. United States Life Tables, 2023.
  https://www.cdc.gov/nchs/data/nvsr/nvsr74/nvsr74-06.pdf
- Arias E, Xu JQ. United States life tables, 2023. National Vital Statistics Reports;
  vol 74 no 6. Hyattsville, MD: National Center for Health Statistics. 2025.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator, CalculatorCategory, CalculatorResult,
    InputMetadata, InputType,
)


class SSALifeExpectancyCalculator(ClinicalCalculator):
    """
    SSA Actuarial Life Expectancy Calculator.

    Uses comprehensive U.S. life tables (ages 0-100) from Social Security Administration
    and CDC National Vital Statistics System. Adjusts for health status and comorbidities.
    """

    # SSA 2024 Period Life Table - Expectation of Life (years remaining)
    # Source: SSA Actuarial Life Tables 2024 + CDC NVSS 2023
    LIFE_TABLE_MALE = {
        0: 74.8, 10: 65.3, 20: 55.6, 30: 46.2, 40: 36.8,
        50: 27.8, 60: 19.6, 70: 12.6, 80: 7.2, 90: 3.5, 100: 1.9
    }

    LIFE_TABLE_FEMALE = {
        0: 80.2, 10: 70.7, 20: 60.9, 30: 51.2, 40: 41.5,
        50: 32.0, 60: 23.0, 70: 14.9, 80: 8.6, 90: 4.2, 100: 2.2
    }

    @property
    def name(self) -> str:
        return "SSA Life Expectancy Calculator"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.SURGICAL_PLANNING

    @property
    def description(self) -> str:
        return "Estimate life expectancy using SSA actuarial tables adjusted for health status and comorbidities"

    @property
    def version(self) -> str:
        return "2.0"

    @property
    def references(self) -> List[str]:
        return [
            "Social Security Administration. Period Life Tables, 2024. https://www.ssa.gov/oact/HistEst/PerLifeTables/2024/PerLifeTables2024.html",
            "Arias E, Xu JQ. United States life tables, 2023. National Vital Statistics Reports; vol 74 no 6. Hyattsville, MD: National Center for Health Statistics. 2025.",
            "CDC National Vital Statistics System. https://www.cdc.gov/nchs/nvss/life-expectancy.htm"
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["age", "gender"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get input schema for SSA Life Expectancy Calculator."""
        return [
            InputMetadata(
                "age", "Age", InputType.NUMERIC, True,
                "Patient age in years",
                unit="years", min_value=0, max_value=100, example="40",
                help_text="Age from 0-100 years. Uses SSA actuarial tables."
            ),
            InputMetadata(
                "gender", "Gender", InputType.ENUM, True,
                "Biological sex",
                allowed_values=["male", "female"], example="male",
                help_text="Females have ~5-6 years longer life expectancy on average."
            ),
            InputMetadata(
                "health_status", "Health Status", InputType.ENUM, False,
                "Overall health assessment",
                allowed_values=["excellent", "good", "fair", "poor"], example="good",
                help_text="Excellent: +10% LE. Good: +5%. Fair: -5%. Poor: -15%."
            ),
            InputMetadata(
                "comorbidities", "Number of Comorbidities", InputType.NUMERIC, False,
                "Count of significant chronic conditions",
                unit="conditions", min_value=0, max_value=20, example="2",
                help_text="Each major comorbidity reduces LE by ~1-2 years."
            ),
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate calculator inputs."""
        # Validate age
        is_valid, msg = self._validate_range(inputs.get("age", 0), 0, 100, "age")
        if not is_valid:
            return False, msg

        # Validate gender
        gender = str(inputs.get("gender", "")).lower()
        if gender not in ["male", "female"]:
            return False, "gender must be 'male' or 'female'"

        # Validate optional health status
        if "health_status" in inputs and inputs["health_status"]:
            health = str(inputs["health_status"]).lower()
            if health not in ["excellent", "good", "fair", "poor"]:
                return False, "health_status must be 'excellent', 'good', 'fair', or 'poor'"

        # Validate optional comorbidities
        if "comorbidities" in inputs and inputs["comorbidities"] is not None:
            # Handle both list and numeric inputs
            if isinstance(inputs["comorbidities"], list):
                comorbidity_count = len(inputs["comorbidities"])
            else:
                try:
                    comorbidity_count = int(float(inputs["comorbidities"]))
                except (ValueError, TypeError):
                    return False, "comorbidities must be a number or list"

            if comorbidity_count < 0 or comorbidity_count > 20:
                return False, "comorbidities must be between 0 and 20"

        return True, None

    def _interpolate_life_expectancy(self, age: int, gender: str) -> float:
        """
        Interpolate life expectancy for any age using SSA actuarial tables.

        Uses linear interpolation between known data points for ages 0-100.
        """
        table = self.LIFE_TABLE_MALE if gender == "male" else self.LIFE_TABLE_FEMALE

        # Get sorted age keys
        ages = sorted(table.keys())

        # Exact match
        if age in table:
            return table[age]

        # Find surrounding ages for interpolation
        lower_age = max([a for a in ages if a <= age], default=ages[0])
        upper_age = min([a for a in ages if a >= age], default=ages[-1])

        if lower_age == upper_age:
            return table[lower_age]

        # Linear interpolation
        lower_le = table[lower_age]
        upper_le = table[upper_age]

        proportion = (age - lower_age) / (upper_age - lower_age)
        interpolated_le = lower_le + (upper_le - lower_le) * proportion

        return interpolated_le

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate life expectancy using SSA actuarial tables."""

        age = int(float(inputs.get("age", 40)))
        gender = str(inputs.get("gender", "male")).lower()
        health_status = str(inputs.get("health_status", "good")).lower() if inputs.get("health_status") else "good"

        # Handle comorbidities as either count or list
        comorbidities_input = inputs.get("comorbidities", 0)
        if isinstance(comorbidities_input, list):
            comorbidity_count = len(comorbidities_input)
        else:
            comorbidity_count = int(float(comorbidities_input)) if comorbidities_input else 0

        # Get base life expectancy from SSA tables
        base_le = self._interpolate_life_expectancy(age, gender)

        # Health status adjustment (evidence-based modifiers)
        health_multipliers = {
            "excellent": 1.10,  # +10% (excellent health, no chronic disease)
            "good": 1.05,       # +5% (minor conditions, well-controlled)
            "fair": 0.95,       # -5% (multiple conditions, moderately controlled)
            "poor": 0.85,       # -15% (significant functional impairment)
        }
        health_multiplier = health_multipliers.get(health_status, 1.0)
        adjusted_le = base_le * health_multiplier

        # Comorbidity adjustment (Charlson-based estimate: ~1.5 years per condition)
        comorbidity_reduction = comorbidity_count * 1.5
        final_le = max(0.5, adjusted_le - comorbidity_reduction)

        # Determine prognostic category
        if final_le >= 20:
            prognosis = "Excellent prognosis"
            risk_level = "low"
        elif final_le >= 10:
            prognosis = "Good prognosis"
            risk_level = "low"
        elif final_le >= 5:
            prognosis = "Moderate prognosis"
            risk_level = "moderate"
        else:
            prognosis = "Limited prognosis"
            risk_level = "high"

        # Build interpretation
        interpretation_parts = [
            f"{age}-year-old {gender}",
            f"Base life expectancy: {base_le:.1f} years (SSA actuarial tables)",
            f"Health status: {health_status.capitalize()} (multiplier: {health_multiplier:.2f})",
        ]

        if comorbidity_count > 0:
            interpretation_parts.append(
                f"Comorbidities: {comorbidity_count} conditions (-{comorbidity_reduction:.1f} years)"
            )

        interpretation_parts.append(f"Adjusted life expectancy: {final_le:.1f} years")
        interpretation_parts.append(f"Prognosis: {prognosis}")

        # Recommendations
        recommendations = [
            "Use for surgical risk assessment and treatment planning",
            "Consider in shared decision-making discussions",
            "Integrate with functional status and patient goals"
        ]

        if final_le < 5:
            recommendations.append("Consider palliative care consultation")
            recommendations.append("Reassess risks/benefits of aggressive interventions")
        elif comorbidity_count >= 3:
            recommendations.append("Optimize comorbidity management before elective procedures")

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                'age': age,
                'gender': gender,
                'health_status': health_status,
                'comorbidity_count': comorbidity_count,
                'base_life_expectancy_years': round(base_le, 1),
                'adjusted_life_expectancy_years': round(final_le, 1),
                'health_multiplier': health_multiplier,
                'comorbidity_reduction_years': comorbidity_reduction,
                'prognosis': prognosis
            },
            interpretation=". ".join(interpretation_parts),
            risk_level=risk_level,
            recommendations=recommendations,
            references=self.references
        )
