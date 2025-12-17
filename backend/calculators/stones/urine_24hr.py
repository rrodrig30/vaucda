from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class Urine24HrCalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "24-Hour Urine Analysis"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.STONES

    @property
    def description(self) -> str:
        return "Assess stone recurrence risk factors from 24-hour urine collection"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def references(self) -> List[str]:
        return ["Pearle MS, et al. Urolithiasis: 2014 AUA Guidelines. J Urol. 2015;193(1):54-61",
                "Borghi L, et al. Nephrolithiasis: Urology 2007. Eur Urol. 2007;52(1):144-151"]

    @property
    def required_inputs(self) -> List[str]:
        return ["calcium_mg", "oxalate_mg", "citrate_mg", "uric_acid_mg", "volume_ml", "gender"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for 24-Hour Urine Analysis calculator inputs."""
        return [
            InputMetadata(
                field_name="calcium_mg",
                display_name="24-Hour Urine Calcium",
                input_type=InputType.NUMERIC,
                required=True,
                description="Total calcium excretion in 24-hour urine collection",
                unit="mg",
                min_value=0,
                max_value=500,
                example="250",
                help_text="Normal <200-250 mg/day. Hypercalciuria >250 (men) or >200 (women) increases calcium stone risk."
            ),
            InputMetadata(
                field_name="oxalate_mg",
                display_name="24-Hour Urine Oxalate",
                input_type=InputType.NUMERIC,
                required=True,
                description="Total oxalate excretion in 24-hour urine collection",
                unit="mg",
                min_value=0,
                max_value=150,
                example="35",
                help_text="Normal <40-45 mg/day. Hyperoxaluria >45 mg/day increases calcium oxalate stone risk."
            ),
            InputMetadata(
                field_name="citrate_mg",
                display_name="24-Hour Urine Citrate",
                input_type=InputType.NUMERIC,
                required=True,
                description="Total citrate excretion in 24-hour urine collection",
                unit="mg",
                min_value=0,
                max_value=1500,
                example="450",
                help_text="Normal >300-600 mg/day. Hypocitraturia <300 mg/day (major risk factor). Citrate chelates calcium, preventing stones."
            ),
            InputMetadata(
                field_name="uric_acid_mg",
                display_name="24-Hour Urine Uric Acid",
                input_type=InputType.NUMERIC,
                required=True,
                description="Total uric acid excretion in 24-hour urine collection",
                unit="mg",
                min_value=0,
                max_value=1500,
                example="600",
                help_text="Normal 400-800 mg/day. Hyperuricuria >800 mg/day increases uric acid and calcium stone risk."
            ),
            InputMetadata(
                field_name="volume_ml",
                display_name="24-Hour Urine Volume",
                input_type=InputType.NUMERIC,
                required=True,
                description="Total volume of 24-hour urine collection",
                unit="mL",
                min_value=500,
                max_value=5000,
                example="2000",
                help_text="Goal >2000-2500 mL/day. Low volume increases stone-forming substance concentration. Main modifiable factor."
            ),
            InputMetadata(
                field_name="gender",
                display_name="Patient Gender",
                input_type=InputType.ENUM,
                required=True,
                description="Biological sex (affects calcium threshold)",
                allowed_values=["male", "female"],
                example="male",
                help_text="Male: Hypercalciuria threshold >250 mg/day. Female: >200 mg/day. Women have lower thresholds for abnormality."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = ["calcium_mg", "oxalate_mg", "citrate_mg", "uric_acid_mg", "volume_ml", "gender"]
        for key in required:
            if key not in inputs:
                return False, f"Missing required input: {key}"

        try:
            for key in ["calcium_mg", "oxalate_mg", "citrate_mg", "uric_acid_mg", "volume_ml"]:
                val = float(inputs.get(key, 0))
                if val < 0 or val > 10000:
                    return False, f"{key} out of range"
        except (ValueError, TypeError):
            return False, "Invalid numeric inputs"

        if inputs.get("gender", "").lower() not in ["male", "female"]:
            return False, "Gender must be 'male' or 'female'"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        calcium = float(inputs.get("calcium_mg", 0))
        oxalate = float(inputs.get("oxalate_mg", 0))
        citrate = float(inputs.get("citrate_mg", 0))
        uric_acid = float(inputs.get("uric_acid_mg", 0))
        volume = float(inputs.get("volume_ml", 0))
        gender = inputs.get("gender", "").lower()

        # Determine calcium threshold based on gender
        calcium_threshold = 250 if gender == "male" else 200

        # Identify risk factors
        findings = []

        if volume < 2000:
            findings.append(f"Low urine volume ({volume:.0f} mL)")

        if calcium > calcium_threshold:
            findings.append(f"Hypercalciuria ({calcium:.0f} mg)")

        if oxalate > 45:
            findings.append(f"Hyperoxaluria ({oxalate:.0f} mg)")

        if citrate < 300:
            findings.append(f"Hypocitraturia ({citrate:.0f} mg)")

        if uric_acid > 800:
            findings.append(f"Hyperuricuria ({uric_acid:.0f} mg)")

        # Determine overall risk
        risk_factors_text = "; ".join(findings) if findings else "Normal parameters"

        if len(findings) >= 3:
            risk_level = "high"
            risk_category = "High risk"
        elif len(findings) >= 1:
            risk_level = "moderate"
            risk_category = "Moderate risk"
        else:
            risk_level = "low"
            risk_category = "Low risk"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                'calcium_mg': calcium,
                'oxalate_mg': oxalate,
                'citrate_mg': citrate,
                'uric_acid_mg': uric_acid,
                'volume_ml': volume,
                'risk_factors': risk_factors_text,
                'risk_category': risk_category
            },
            interpretation=f"24-hour urine analysis: {risk_category} for stone recurrence. {risk_factors_text}",
            risk_level=risk_level,
            recommendations=[
                "Increase hydration to maintain urine volume >2000 mL/day",
                "Dietary modifications as indicated by specific abnormalities",
                "Consider pharmacotherapy if indicated by findings"
            ],
            references=self.references
        )
