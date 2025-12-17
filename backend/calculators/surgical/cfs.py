from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator, CalculatorCategory, CalculatorResult,
    InputMetadata, InputType,
)

class CFSCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Clinical Frailty Scale"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.SURGICAL_PLANNING

    @property
    def description(self) -> str:
        return "Assess frailty and surgical risk in elderly patients"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def references(self) -> List[str]:
        return ["Rockwood K, et al. A global clinical measure of fitness and frailty in elderly people. CMAJ. 2005;173(5):489-495"]

    @property
    def required_inputs(self) -> List[str]:
        return ["activity_level", "independence", "cognition", "functional_status"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get input schema for Clinical Frailty Scale."""
        return [
            InputMetadata("activity_level", "Activity Level", InputType.ENUM, True, "Physical activity", allowed_values=["sedentary", "light_activity", "moderate_exercise", "vigorous_exercise"], example="moderate_exercise", help_text="Sedentary to vigorous. Higher activity = better prognosis."),
            InputMetadata("independence", "Functional Independence", InputType.ENUM, True, "ADL independence", allowed_values=["dependent", "needs_assistance", "independent", "fully_independent"], example="independent", help_text="Dependent to fully independent. Important surgical risk factor."),
            InputMetadata("cognition", "Cognitive Status", InputType.ENUM, True, "Mental status", allowed_values=["impaired", "mildly_impaired", "intact"], example="intact", help_text="Impaired cognition increases perioperative risk."),
            InputMetadata("functional_status", "Frailty Status", InputType.ENUM, True, "Functional capacity", allowed_values=["frail", "vulnerable", "robust"], example="robust", help_text="Frail = high risk. Robust = low risk. Primary outcome measure."),
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = ["activity_level", "independence", "cognition", "functional_status"]
        for key in required:
            if key not in inputs:
                return False, f"Missing required input: {key}"

        valid_activity = ["sedentary", "light_activity", "moderate_exercise", "vigorous_exercise"]
        if inputs.get("activity_level", "").lower() not in valid_activity:
            return False, f"activity_level must be one of {valid_activity}"

        valid_independence = ["dependent", "needs_assistance", "independent", "fully_independent"]
        if inputs.get("independence", "").lower() not in valid_independence:
            return False, f"independence must be one of {valid_independence}"

        valid_cognition = ["impaired", "mildly_impaired", "intact"]
        if inputs.get("cognition", "").lower() not in valid_cognition:
            return False, f"cognition must be one of {valid_cognition}"

        valid_functional = ["frail", "vulnerable", "robust"]
        if inputs.get("functional_status", "").lower() not in valid_functional:
            return False, f"functional_status must be one of {valid_functional}"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        activity = inputs.get("activity_level", "").lower()
        independence = inputs.get("independence", "").lower()
        cognition = inputs.get("cognition", "").lower()
        functional = inputs.get("functional_status", "").lower()

        # Score based on characteristics
        score = 0

        # Activity scoring
        if activity == "vigorous_exercise":
            score = 1
        elif activity == "moderate_exercise":
            score = 2
        elif activity == "light_activity":
            score = 3
        else:
            score = 4

        # Independence scoring
        if independence == "fully_independent":
            independence_score = 1
        elif independence == "independent":
            independence_score = 2
        elif independence == "needs_assistance":
            independence_score = 3
        else:
            independence_score = 4

        # Cognition scoring
        if cognition == "intact":
            cognition_score = 1
        elif cognition == "mildly_impaired":
            cognition_score = 2
        else:
            cognition_score = 3

        # Functional status scoring
        if functional == "robust":
            functional_score = 1
        elif functional == "vulnerable":
            functional_score = 2
        else:
            functional_score = 3

        # Determine frailty level
        avg_score = (score + independence_score + cognition_score + functional_score) / 4

        if avg_score <= 1.5:
            cfs_level = 1
            description = "Very Fit"
            risk_level = "low"
        elif avg_score <= 2.5:
            cfs_level = 2
            description = "Fit"
            risk_level = "low"
        elif avg_score <= 3.5:
            cfs_level = 3
            description = "Managing Well"
            risk_level = "moderate"
        elif avg_score <= 4.5:
            cfs_level = 4
            description = "Very Mild Frailty"
            risk_level = "moderate"
        elif avg_score <= 5.5:
            cfs_level = 5
            description = "Mild Frailty"
            risk_level = "moderate"
        elif avg_score <= 6.5:
            cfs_level = 6
            description = "Moderate Frailty"
            risk_level = "high"
        elif avg_score <= 7.5:
            cfs_level = 7
            description = "Severe Frailty"
            risk_level = "high"
        elif avg_score <= 8.5:
            cfs_level = 8
            description = "Very Severe Frailty"
            risk_level = "very_high"
        else:
            cfs_level = 9
            description = "Terminally Ill"
            risk_level = "very_high"

        # Determine surgical recommendation
        if cfs_level <= 3:
            recommendation = "Standard surgical candidate with appropriate preoperative optimization"
        elif cfs_level <= 5:
            recommendation = "Consider modified surgical approach; additional preoperative evaluation recommended"
        elif cfs_level <= 7:
            recommendation = "High risk; strongly consider conservative alternatives or less invasive options"
        else:
            recommendation = "Usually not a surgical candidate; conservative management strongly recommended"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                'cfs_level': cfs_level,
                'description': description,
                'recommendation': recommendation
            },
            interpretation=f"Clinical Frailty Scale: Level {cfs_level} - {description}",
            risk_level=risk_level,
            recommendations=[recommendation],
            references=self.references
        )
