"""POP-Q Staging System Calculator."""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class POPQCalculator(ClinicalCalculator):
    """Pelvic Organ Prolapse Quantification staging."""

    @property
    def name(self) -> str:
        return "POP-Q Staging System"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.FEMALE_UROLOGY

    @property
    def description(self) -> str:
        return "Quantify pelvic organ prolapse and assign stage"

    @property
    def references(self) -> List[str]:
        return ["Bump RC, et al. The standardization of terminology of female pelvic organ prolapse. Am J Obstet Gynecol. 1996;175:10-17"]

    @property
    def required_inputs(self) -> List[str]:
        return ["aa", "ba", "c", "d", "ap", "bp", "gh", "pb", "tvl"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for POP-Q Staging System calculator inputs."""
        return [
            InputMetadata(
                field_name="aa",
                display_name="Aa Point",
                input_type=InputType.NUMERIC,
                required=True,
                description="Anterior vaginal wall point at 3 o'clock position relative to hymen",
                unit="cm",
                min_value=-10,
                max_value=10,
                example="-2",
                help_text="Measured in cm relative to hymenal ring. Negative = above hymen, positive = below hymen."
            ),
            InputMetadata(
                field_name="ba",
                display_name="Ba Point",
                input_type=InputType.NUMERIC,
                required=True,
                description="Anterior vaginal wall point at maximum extent",
                unit="cm",
                min_value=-10,
                max_value=10,
                example="-1",
                help_text="Most distal point of anterior vaginal wall. >0 indicates anterior prolapse."
            ),
            InputMetadata(
                field_name="c",
                display_name="C Point",
                input_type=InputType.NUMERIC,
                required=True,
                description="Cervix or vaginal cuff point",
                unit="cm",
                min_value=-10,
                max_value=10,
                example="-6",
                help_text="Position of cervix (or cuff if hysterectomy). Negative values indicate apical support."
            ),
            InputMetadata(
                field_name="d",
                display_name="D Point",
                input_type=InputType.NUMERIC,
                required=True,
                description="Posterior fornix depth",
                unit="cm",
                min_value=-10,
                max_value=10,
                example="-8",
                help_text="Deepest point of posterior fornix. Only measure if cervix present. -1 if hysterectomy."
            ),
            InputMetadata(
                field_name="ap",
                display_name="Ap Point",
                input_type=InputType.NUMERIC,
                required=True,
                description="Posterior vaginal wall point at 9 o'clock position",
                unit="cm",
                min_value=-10,
                max_value=10,
                example="-3",
                help_text="Posterior vaginal wall at hymenal level. Negative indicates good support."
            ),
            InputMetadata(
                field_name="bp",
                display_name="Bp Point",
                input_type=InputType.NUMERIC,
                required=True,
                description="Posterior vaginal wall at maximum extent",
                unit="cm",
                min_value=-10,
                max_value=10,
                example="-1",
                help_text="Most distal point of posterior vaginal wall. >0 indicates posterior prolapse."
            ),
            InputMetadata(
                field_name="gh",
                display_name="Gh Distance",
                input_type=InputType.NUMERIC,
                required=True,
                description="Genital hiatus distance",
                unit="cm",
                min_value=0,
                max_value=10,
                example="2.5",
                help_text="Distance from urethral opening to posterior fourchette. Normal <3 cm. Enlarged suggests perineal descent."
            ),
            InputMetadata(
                field_name="pb",
                display_name="Pb Distance",
                input_type=InputType.NUMERIC,
                required=True,
                description="Perineal body distance",
                unit="cm",
                min_value=0,
                max_value=10,
                example="3",
                help_text="Distance from posterior fourchette to anal verge. Normal >2.5 cm. <2 suggests shortened perineal body."
            ),
            InputMetadata(
                field_name="tvl",
                display_name="Total Vaginal Length",
                input_type=InputType.NUMERIC,
                required=True,
                description="Total length of vagina",
                unit="cm",
                min_value=5,
                max_value=12,
                example="8",
                help_text="Measured from external urethral orifice to apex of vagina. Normal 7-10 cm."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        is_valid, msg = self._validate_required(inputs, self.required_inputs)
        return is_valid, msg if not is_valid else None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate POP-Q stage."""
        aa = float(inputs["aa"])
        ba = float(inputs["ba"])
        c = float(inputs["c"])
        ap = float(inputs["ap"])
        bp = float(inputs["bp"])
        gh = float(inputs["gh"])
        pb = float(inputs["pb"])
        tvl = float(inputs["tvl"])

        leading_edge = max(aa, ba, c, ap, bp)

        if leading_edge <= -(tvl - 2):
            stage = "Stage 0"
        elif leading_edge < -1:
            stage = "Stage I"
        elif leading_edge <= 1:
            stage = "Stage II"
        elif leading_edge < tvl - 2:
            stage = "Stage III"
        else:
            stage = "Stage IV"

        result = {"stage": stage, "leading_edge": round(leading_edge, 1)}
        interpretation = f"POP-Q Stage: {stage}. Leading point at {leading_edge:.1f} cm."

        recommendations = ["Discuss symptom severity and treatment options", "Consider conservative vs. surgical management"]

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            recommendations=recommendations,
            risk_level=stage,
            references=self.references,
        )
