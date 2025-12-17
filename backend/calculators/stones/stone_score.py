from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class StoneScoreCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "S.T.O.N.E. Score for Nephrolithotomy"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.STONES

    @property
    def description(self) -> str:
        return "Predict outcomes in percutaneous nephrolithotomy based on stone and patient factors"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def references(self) -> List[str]:
        return ["Okhunov Z, et al. S.T.O.N.E. nephrolithotomy scoring system. J Urol. 2013;190(4):1411-1417"]

    @property
    def required_inputs(self) -> List[str]:
        return ["size", "tract_length", "obstruction", "number", "eversion"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for S.T.O.N.E. Score calculator inputs."""
        return [
            InputMetadata(
                field_name="size",
                display_name="S: Stone Size (points)",
                input_type=InputType.NUMERIC,
                required=True,
                description="Points assigned for stone maximum dimension",
                unit="points",
                min_value=0,
                max_value=3,
                example="2",
                help_text="1 pt: <10 mm. 2 pts: 10-20 mm. 3 pts: >20 mm. Larger stones require more time and morbidity."
            ),
            InputMetadata(
                field_name="tract_length",
                display_name="T: Tract Length (points)",
                input_type=InputType.NUMERIC,
                required=True,
                description="Points for skin-to-stone distance",
                unit="points",
                min_value=0,
                max_value=2,
                example="1",
                help_text="0 pts: <10 cm. 1 pt: 10-15 cm. 2 pts: >15 cm. Longer tracts increase complications."
            ),
            InputMetadata(
                field_name="obstruction",
                display_name="O: Obstruction (points)",
                input_type=InputType.NUMERIC,
                required=True,
                description="Points for obstruction and pyonephrosis presence",
                unit="points",
                min_value=0,
                max_value=2,
                example="0",
                help_text="0 pts: None. 1 pt: Present without infection. 2 pts: Pyonephrosis. Infection increases morbidity risk."
            ),
            InputMetadata(
                field_name="number",
                display_name="N: Number of Stones (points)",
                input_type=InputType.NUMERIC,
                required=True,
                description="Points for number of calculi",
                unit="points",
                min_value=0,
                max_value=2,
                example="1",
                help_text="0 pts: Single. 1 pt: 2-3 stones. 2 pts: >3 or branching stones. Multiple stones increase procedure time."
            ),
            InputMetadata(
                field_name="eversion",
                display_name="E: Essence-Ectasia (points)",
                input_type=InputType.NUMERIC,
                required=True,
                description="Points for calyceal dilation/ectasia",
                unit="points",
                min_value=0,
                max_value=2,
                example="0",
                help_text="0 pts: Mild/normal. 1 pt: Moderate. 2 pts: Severe ectasia. Ectasia suggests chronic obstruction."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        # Accept both parameter formats
        has_format1 = "size" in inputs and "tract_length" in inputs
        has_format2 = "stone_size" in inputs and "thir" in inputs

        if not (has_format1 or has_format2):
            return False, "Missing required inputs"

        try:
            if has_format1:
                for key in ["size", "tract_length", "obstruction", "number", "eversion"]:
                    int(inputs.get(key, 0))
            else:
                float(inputs.get("stone_size", 0))
                int(inputs.get("number_of_stones", 0))
        except (ValueError, TypeError):
            return False, "Invalid numeric inputs"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        # S.T.O.N.E. Score: Stone size, Tract length, Obstruction, Number, Essence (ectasia)
        # Support both parameter naming formats
        if "size" in inputs:
            # Format 1: size, tract_length, obstruction, number, eversion (already scored)
            score = int(inputs.get("size", 0))
            score += int(inputs.get("tract_length", 0))
            score += int(inputs.get("obstruction", 0))
            score += int(inputs.get("number", 0))
            score += int(inputs.get("eversion", 0))
        else:
            # Format 2: stone_size, thir, obstruction, number_of_stones, ectasia (need to score)
            stone_size = float(inputs.get("stone_size", 0))
            thir = inputs.get("thir", "no").lower()
            obstruction = inputs.get("obstruction", "no").lower()
            number_stones = int(inputs.get("number_of_stones", 1))
            ectasia = inputs.get("ectasia", "no").lower()

            # Calculate S.T.O.N.E. score (0-13)
            score = 0

            # Stone size (0-3)
            if stone_size < 1:
                score += 1
            elif stone_size < 2:
                score += 2
            else:
                score += 3

            # Tract length / THR (0-2)
            if thir == "yes":
                score += 2
            else:
                score += 0

            # Obstruction (0-2)
            if obstruction == "yes":
                score += 2
            else:
                score += 0

            # Number of stones (0-2)
            if number_stones <= 1:
                score += 0
            elif number_stones <= 2:
                score += 1
            else:
                score += 2

            # Essence / ectasia (0-2)
            if ectasia == "yes":
                score += 2
            else:
                score += 0

        # Determine risk based on score
        if score <= 3:
            risk_category = "Low risk"
            prognosis = "Good prognosis for stone-free outcome"
            risk_level = "low"
        elif score <= 7:
            risk_category = "Moderate risk"
            prognosis = "Moderate prognosis for stone-free outcome"
            risk_level = "moderate"
        else:
            risk_category = "High risk"
            prognosis = "Lower prognosis for stone-free outcome"
            risk_level = "high"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                'score': score,
                'category': risk_category,
                'prognosis': prognosis
            },
            interpretation=f"S.T.O.N.E. Score {score}: {risk_category} - {prognosis}",
            risk_level=risk_level,
            references=self.references
        )
