"""Charlson Comorbidity Index (CCI) Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class CCICalculator(ClinicalCalculator):
    """Charlson Comorbidity Index for mortality prediction."""

    @property
    def name(self) -> str:
        return "Charlson Comorbidity Index"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.SURGICAL_PLANNING

    @property
    def description(self) -> str:
        return "Predicts 10-year mortality based on comorbid conditions"

    @property
    def references(self) -> List[str]:
        return [
            "Charlson ME, et al. A new method of classifying prognostic comorbidity in longitudinal studies. J Chronic Dis. 1987;40(5):373-383"
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["age", "comorbidities"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Charlson Comorbidity Index inputs."""
        return [
            InputMetadata(
                field_name="age",
                display_name="Patient Age",
                input_type=InputType.NUMERIC,
                required=True,
                description="Age in years",
                unit="years",
                min_value=18,
                max_value=120,
                example="65",
                help_text="Age-adjusted mortality predictor. Score increases with age. One point per decade >40 years."
            ),
            InputMetadata(
                field_name="comorbidities",
                display_name="Comorbid Conditions",
                input_type=InputType.TEXT,
                required=True,
                description="List of relevant comorbid conditions (JSON array of condition codes)",
                example='["MI", "CHF", "diabetes"]',
                help_text="Provide as JSON array. Select from: MI (myocardial infarction), CHF (congestive heart failure), PVD (peripheral vascular disease), CVA (cerebrovascular accident), dementia, COPD, CTD (connective tissue disease), PUD (peptic ulcer disease), diabetes, CKD (chronic kidney disease), hemiplegia, cancer, liver_mild, liver_severe, metastatic_cancer, AIDS. Each worth 1-6 points."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if "age" not in inputs:
            return False, "Age is required"
        if not isinstance(inputs["age"], (int, float)) or inputs["age"] < 0:
            return False, "Age must be a positive number"
        if "comorbidities" not in inputs:
            return False, "Comorbidities list is required"
        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        age = inputs["age"]
        comorbidities = inputs.get("comorbidities", [])

        # Age score
        if age < 50:
            score = 0
        elif age < 60:
            score = 1
        elif age < 70:
            score = 2
        elif age < 80:
            score = 3
        else:
            score = 4

        # Comorbidity scores
        comorbidity_scores = {
            "MI": 1, "CHF": 1, "PVD": 1, "CVA": 1, "dementia": 1,
            "COPD": 1, "CTD": 1, "PUD": 1, "liver_mild": 1, "diabetes": 1,
            "hemiplegia": 2, "CKD": 2, "diabetes_complications": 2,
            "cancer": 2, "liver_severe": 3, "metastatic_cancer": 6, "AIDS": 6
        }

        for condition in comorbidities:
            score += comorbidity_scores.get(condition, 0)

        # 10-year survival estimates
        if score == 0:
            survival = 99
        elif score == 1:
            survival = 96
        elif score == 2:
            survival = 90
        elif score == 3:
            survival = 77
        elif score == 4:
            survival = 53
        elif score == 5:
            survival = 21
        else:
            survival = 2

        interpretation = f"CCI Score: {score}. Estimated 10-year survival: {survival}%"

        # Determine risk level based on score
        if score <= 1:
            risk_level = "Low"
        elif score <= 3:
            risk_level = "Moderate"
        else:
            risk_level = "High"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={"cci_score": score, "ten_year_survival": survival},
            interpretation=interpretation,
            risk_level=risk_level,
            references=self.references
        )
