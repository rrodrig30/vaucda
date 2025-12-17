"""
International Prostate Symptom Score (IPSS) Calculator.

Comprehensive assessment of lower urinary tract symptoms with seven questions
scored 0-5, plus quality of life assessment.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class IPSSCalculator(ClinicalCalculator):
    """
    IPSS (International Prostate Symptom Score) Calculator.

    Calculates:
    1. Total IPSS score (0-35)
    2. Storage vs Voiding subscores
    3. Severity classification
    4. Quality of Life assessment
    """

    @property
    def name(self) -> str:
        return "International Prostate Symptom Score (IPSS)"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_VOIDING

    @property
    def description(self) -> str:
        return "Assess lower urinary tract symptoms in men with BPH"

    @property
    def references(self) -> List[str]:
        return [
            "Barry MJ, et al. The American Urological Association symptom index for benign prostatic hyperplasia. J Urol. 1992;148:1549-1557",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return [
            "incomplete_emptying",
            "frequency",
            "intermittency",
            "urgency",
            "weak_stream",
            "straining",
            "nocturia",
            "qol",
        ]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get input schema for IPSS calculator."""
        return [
            InputMetadata("incomplete_emptying", "Incomplete Emptying", InputType.NUMERIC, True, "Symptom score 0-5", unit="points", min_value=0, max_value=5, example="2", help_text="0: Never, 5: Almost always. Indicates post-void residual urine."),
            InputMetadata("frequency", "Urinary Frequency", InputType.NUMERIC, True, "Daytime voids 0-5", unit="points", min_value=0, max_value=5, example="3", help_text="0: <7x/day, 5: >13x/day. Measures daytime frequency burden."),
            InputMetadata("intermittency", "Intermittency", InputType.NUMERIC, True, "Stream intermittency 0-5", unit="points", min_value=0, max_value=5, example="1", help_text="0: Never, 5: Almost always. Indicates intermittent weak stream."),
            InputMetadata("urgency", "Urgency", InputType.NUMERIC, True, "Urinary urgency 0-5", unit="points", min_value=0, max_value=5, example="2", help_text="0: Never, 5: Almost always. Overactive bladder symptom."),
            InputMetadata("weak_stream", "Weak Stream", InputType.NUMERIC, True, "Stream strength 0-5", unit="points", min_value=0, max_value=5, example="2", help_text="0: Not present, 5: Almost always. Indicates obstruction."),
            InputMetadata("straining", "Straining", InputType.NUMERIC, True, "Effort to void 0-5", unit="points", min_value=0, max_value=5, example="1", help_text="0: Never, 5: Almost always. Need abdominal pressure to void."),
            InputMetadata("nocturia", "Nocturia", InputType.NUMERIC, True, "Nighttime voids 0-5", unit="points", min_value=0, max_value=5, example="2", help_text="0: None, 5: ≥5x/night. Major quality of life impact."),
            InputMetadata("qol", "Quality of Life Impact", InputType.NUMERIC, True, "QoL score 0-6", unit="points", min_value=0, max_value=6, example="3", help_text="0: Delighted, 6: Terrible. Overall impact on daily life."),
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate IPSS inputs."""

        is_valid, msg = self._validate_required(
            inputs,
            [
                "incomplete_emptying",
                "frequency",
                "intermittency",
                "urgency",
                "weak_stream",
                "straining",
                "nocturia",
                "qol",
            ]
        )
        if not is_valid:
            return False, msg

        # Validate each score is 0-5
        for question in [
            "incomplete_emptying",
            "frequency",
            "intermittency",
            "urgency",
            "weak_stream",
            "straining",
        ]:
            try:
                score = int(inputs[question])
                if score < 0 or score > 5:
                    return False, f"{question} must be 0-5"
            except (ValueError, TypeError):
                return False, f"{question} must be an integer 0-5"

        # Validate nocturia is 0-5
        try:
            nocturia = int(inputs["nocturia"])
            if nocturia < 0 or nocturia > 5:
                return False, "Nocturia must be 0-5"
        except (ValueError, TypeError):
            return False, "Nocturia must be an integer"

        # Validate QoL is 0-6
        try:
            qol = int(inputs["qol"])
            if qol < 0 or qol > 6:
                return False, "QoL must be 0-6"
        except (ValueError, TypeError):
            return False, "QoL must be an integer"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate IPSS score."""

        # Get all scores
        scores = {
            "incomplete_emptying": int(inputs["incomplete_emptying"]),
            "frequency": int(inputs["frequency"]),
            "intermittency": int(inputs["intermittency"]),
            "urgency": int(inputs["urgency"]),
            "weak_stream": int(inputs["weak_stream"]),
            "straining": int(inputs["straining"]),
            "nocturia": int(inputs["nocturia"]),
        }

        qol = int(inputs["qol"])

        # Calculate total IPSS
        total_ipss = sum(scores.values())

        # Calculate subscores
        # Storage symptoms: Frequency (Q2) + Urgency (Q4) + Nocturia (Q7)
        storage_subscore = scores["frequency"] + scores["urgency"] + scores["nocturia"]

        # Voiding symptoms: Incomplete emptying (Q1) + Intermittency (Q3) + Weak stream (Q5) + Straining (Q6)
        voiding_subscore = (
            scores["incomplete_emptying"]
            + scores["intermittency"]
            + scores["weak_stream"]
            + scores["straining"]
        )

        # Severity classification
        if total_ipss <= 7:
            severity = "Mild"
            treatment_consideration = "Watchful waiting/conservative management"
        elif total_ipss <= 19:
            severity = "Moderate"
            treatment_consideration = "Medical therapy consideration"
        else:
            severity = "Severe"
            treatment_consideration = "Medical or surgical therapy consideration"

        # QoL interpretation
        qol_descriptions = {
            0: "Delighted",
            1: "Pleased",
            2: "Mostly satisfied",
            3: "Mixed",
            4: "Mostly dissatisfied",
            5: "Unhappy",
            6: "Terrible",
        }
        qol_desc = qol_descriptions.get(qol, "Unknown")

        # Build interpretation
        interpretation_parts = [
            f"Total IPSS Score: {total_ipss}/35",
            f"Severity: {severity}",
            f"Treatment Consideration: {treatment_consideration}",
            f"Storage Symptom Subscore: {storage_subscore}/15",
            f"Voiding Symptom Subscore: {voiding_subscore}/20",
            f"Quality of Life: {qol_desc} ({qol}/6)",
        ]

        # Clinical pattern analysis
        if storage_subscore > voiding_subscore:
            pattern = "Storage-predominant symptoms (OAB pattern)"
        elif voiding_subscore > storage_subscore:
            pattern = "Voiding-predominant symptoms (BPH/obstruction pattern)"
        else:
            pattern = "Mixed storage and voiding symptoms"

        interpretation_parts.append(f"Symptom Pattern: {pattern}")

        result = {
            "total_ipss": total_ipss,
            "severity": severity,
            "storage_subscore": storage_subscore,
            "voiding_subscore": voiding_subscore,
            "qol_score": qol,
            "symptom_pattern": pattern,
            "individual_scores": scores,
        }

        recommendations = []
        if total_ipss <= 7:
            recommendations.append("Watchful waiting with lifestyle modifications")
            recommendations.append("Avoid caffeine, alcohol, large fluid intake")
            recommendations.append("Regular follow-up reassessment")
        elif total_ipss <= 19:
            if storage_subscore > voiding_subscore:
                recommendations.append("Consider anticholinergic medication for OAB")
                recommendations.append("Behavioral modification: bladder retraining")
            else:
                recommendations.append("Alpha-blocker therapy recommended")
                recommendations.append("Consider 5-ARI if prostate enlarged")
        else:
            recommendations.append("Discuss medical vs. surgical options")
            recommendations.append("Urodynamic testing if considering surgery")
            if voiding_subscore > storage_subscore:
                recommendations.append("Consider TURP or laser prostatectomy")

        interpretation = ". ".join(interpretation_parts) + "."

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            category=severity,
            risk_level=severity,
            recommendations=recommendations,
            references=self.references,
        )
