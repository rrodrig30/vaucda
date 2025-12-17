"""Urethral Stricture Complexity Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class StrictureComplexityCalculator(ClinicalCalculator):
    """Urethral stricture complexity scoring."""

    @property
    def name(self) -> str:
        return "Urethral Stricture Complexity Assessment"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.RECONSTRUCTIVE

    @property
    def description(self) -> str:
        return "Assess urethral stricture complexity for surgical planning and outcome prediction"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def references(self) -> List[str]:
        return ["Santucci RA, et al. Urethral trauma. J Urol. 2007;178(6):2262-2269",
                "Erickson BA, et al. Surgical margin stratification for urethral stricture disease. J Urol. 2011;185:2261-2266"]

    @property
    def required_inputs(self) -> List[str]:
        return ["length_cm", "location", "prior_repair", "history_trauma"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for Urethral Stricture Complexity Assessment calculator inputs."""
        return [
            InputMetadata(
                field_name="length_cm",
                display_name="Stricture Length",
                input_type=InputType.NUMERIC,
                required=True,
                description="Length of urethral stricture segment",
                unit="cm",
                min_value=0,
                max_value=25,
                example="2.5",
                help_text="Short: <1 cm (simple). Moderate: 1-4 cm. Long: >4 cm (complex). Longer strictures require more complex reconstruction."
            ),
            InputMetadata(
                field_name="location",
                display_name="Stricture Location",
                input_type=InputType.ENUM,
                required=True,
                description="Anatomic location of stricture in urethra",
                allowed_values=["anterior", "bulbar", "membranous", "prostatic"],
                example="bulbar",
                help_text="Anterior/Bulbar: Easiest reconstruction. Membranous: More complex, near sphincter. Prostatic: Rare, most complex."
            ),
            InputMetadata(
                field_name="prior_repair",
                display_name="Prior Urethral Repair or Dilation",
                input_type=InputType.BOOLEAN,
                required=True,
                description="History of previous treatment (urethroplasty, dilation, stent)",
                example="false",
                help_text="Prior interventions increase complexity due to scar tissue formation, narrowing surgical options."
            ),
            InputMetadata(
                field_name="history_trauma",
                display_name="Traumatic Etiology",
                input_type=InputType.BOOLEAN,
                required=True,
                description="Stricture caused by pelvic trauma, pelvic fracture, or instrumentation injury",
                example="false",
                help_text="Traumatic strictures often have extensive scar involvement, increasing surgical difficulty."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = ["length_cm", "location", "prior_repair", "history_trauma"]
        for key in required:
            if key not in inputs:
                return False, f"Missing required input: {key}"

        try:
            val = float(inputs.get("length_cm", 0))
            if val < 0 or val > 25:
                return False, "length_cm must be between 0 and 25"
        except (ValueError, TypeError):
            return False, "Invalid length_cm value"

        if inputs.get("location", "").lower() not in ["anterior", "bulbar", "membranous", "prostatic"]:
            return False, "Invalid location"

        if not isinstance(inputs.get("prior_repair"), bool):
            return False, "prior_repair must be boolean"

        if not isinstance(inputs.get("history_trauma"), bool):
            return False, "history_trauma must be boolean"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate stricture complexity."""
        length = float(inputs.get("length_cm", 0))
        location = inputs.get("location", "").lower()
        prior_repair = inputs.get("prior_repair", False)
        history_trauma = inputs.get("history_trauma", False)

        # Score based on complexity factors
        score = 0

        # Length scoring
        if length < 1:
            score += 1
        elif length < 2:
            score += 2
        elif length < 4:
            score += 3
        else:
            score += 4

        # Location scoring
        if location in ["anterior", "bulbar"]:
            score += 1
        elif location == "membranous":
            score += 2
        else:  # prostatic
            score += 3

        # Prior repair adds points
        if prior_repair:
            score += 2

        # Trauma history adds points
        if history_trauma:
            score += 1

        # Determine complexity category
        if score <= 5:
            complexity = "Simple"
            recommendation = "Primary anastomotic repair likely feasible"
            risk_level = "low"
        elif score <= 9:
            complexity = "Moderate"
            recommendation = "Substitution urethroplasty likely indicated"
            risk_level = "moderate"
        else:
            complexity = "Complex"
            recommendation = "Staged repair or complex reconstruction may be needed"
            risk_level = "high"

        result = {
            'score': score,
            'complexity': complexity,
            'location': location
        }
        interpretation = f"Stricture Complexity: {complexity}. Recommendation: {recommendation}"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=[recommendation],
            references=self.references,
        )
