from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)

class PFUICalculator(ClinicalCalculator):
    @property
    def name(self) -> str:
        return "Pelvic Fracture Urethral Injury (PFUI) Classification"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.RECONSTRUCTIVE

    @property
    def description(self) -> str:
        return "Classify pelvic fracture urethral injury based on clinical presentation and imaging"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def references(self) -> List[str]:
        return ["Goldman HB, et al. Classification of pelvic fracture urethral injury. BJU Int. 1997;79:245-250",
                "Koraitim MM. Pelvic fracture urethral injuries. J Trauma. 2003;54:423-430"]

    @property
    def required_inputs(self) -> List[str]:
        return ["fracture_type", "void_status", "imaging"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get detailed metadata for PFUI Classification calculator inputs."""
        return [
            InputMetadata(
                field_name="fracture_type",
                display_name="Pelvic Fracture Type",
                input_type=InputType.ENUM,
                required=True,
                description="Severity and pattern of pelvic fracture",
                allowed_values=["simple", "incomplete", "complex", "complete"],
                example="complete",
                help_text="Simple: Isolated fracture, lower energy. Incomplete: Partial disruption. Complex: Multiple fractures. Complete: Full disruption of pelvic ring."
            ),
            InputMetadata(
                field_name="void_status",
                display_name="Voiding Ability",
                input_type=InputType.ENUM,
                required=True,
                description="Patient ability to void urine after injury",
                allowed_values=["able", "difficulty", "unable"],
                example="unable",
                help_text="Able: Normal voiding. Difficulty: Able but with symptoms (hesitancy, weak stream). Unable: Complete retention, indicates urethral disruption."
            ),
            InputMetadata(
                field_name="imaging",
                display_name="Diagnostic Imaging Performed",
                input_type=InputType.ENUM,
                required=True,
                description="Type of imaging study used to evaluate injury",
                allowed_values=["vcug", "urethrography", "endoscopy", "ultrasound"],
                example="vcug",
                help_text="VCUG (Voiding Cystourethrography): Gold standard for diagnosis. Urethrography: Detailed imaging. Endoscopy: Direct visualization. Ultrasound: Limited role."
            )
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        required = ["fracture_type", "void_status", "imaging"]
        for key in required:
            if key not in inputs:
                return False, f"Missing required input: {key}"

        valid_fractures = ["complete", "incomplete", "simple", "complex"]
        if inputs.get("fracture_type", "").lower() not in valid_fractures:
            return False, f"fracture_type must be one of {valid_fractures}"

        valid_void = ["able", "unable", "difficulty"]
        if inputs.get("void_status", "").lower() not in valid_void:
            return False, f"void_status must be one of {valid_void}"

        valid_imaging = ["vcug", "urethrography", "endoscopy", "ultrasound"]
        if inputs.get("imaging", "").lower() not in valid_imaging:
            return False, f"imaging must be one of {valid_imaging}"

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        fracture_type = inputs.get("fracture_type", "").lower()
        void_status = inputs.get("void_status", "").lower()
        imaging = inputs.get("imaging", "").lower()

        # Determine injury classification based on presentation
        if fracture_type == "complete" and void_status == "unable":
            pfui_type = "Type III-IV"
            description = "Complete disruption or severe partial tear"
            risk_level = "high"
        elif fracture_type == "complete" and void_status == "difficulty":
            pfui_type = "Type II-III"
            description = "Partial tear with some disruption"
            risk_level = "high"
        elif fracture_type in ["incomplete", "simple"] and void_status == "ability":
            pfui_type = "Type I"
            description = "Contusion or incomplete tear"
            risk_level = "low"
        else:
            pfui_type = "Type II"
            description = "Partial tear"
            risk_level = "moderate"

        interpretation = f"PFUI Classification: {pfui_type} - {description}"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result={
                'classification': pfui_type,
                'description': description,
                'fracture_type': fracture_type,
                'void_status': void_status,
                'imaging': imaging
            },
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=["Imaging studies (VCUG) recommended", "Surgical reconstruction planning based on injury type"],
            references=self.references
        )
