"""
BOOI/BCI Urodynamic Indices Calculator.

Calculates Bladder Outlet Obstruction Index (BOOI) and Bladder
Contractility Index (BCI) from pressure-flow study results.
"""

from typing import Any, Dict, List, Optional, Tuple
from calculators.base import (
    ClinicalCalculator,
    CalculatorCategory,
    CalculatorResult,
    InputMetadata,
    InputType,
)


class BOOIBCICalculator(ClinicalCalculator):
    """
    BOOI/BCI Urodynamic Indices Calculator.

    Calculates:
    1. BOOI = PdetQmax - 2 × Qmax
    2. BCI = PdetQmax + 5 × Qmax
    3. Obstruction vs contractility assessment
    """

    @property
    def name(self) -> str:
        return "BOOI/BCI Urodynamic Indices"

    @property
    def category(self) -> CalculatorCategory:
        return CalculatorCategory.MALE_VOIDING

    @property
    def description(self) -> str:
        return "Calculate bladder obstruction and contractility indices from pressure-flow study"

    @property
    def references(self) -> List[str]:
        return [
            "Abrams P. Urodynamics. 3rd ed. London: Springer-Verlag; 2006",
            "Griffiths D. Clinical aspects of detrusor hyperreflexia and detrusor instability. Urology. 1998;51:3-7",
        ]

    @property
    def required_inputs(self) -> List[str]:
        return ["pdet_at_qmax", "qmax"]

    def get_input_schema(self) -> List[InputMetadata]:
        """Get input schema for BOOI/BCI calculator."""
        return [
            InputMetadata("pdet_at_qmax", "Detrusor Pressure at Qmax", InputType.NUMERIC, True, "Pressure during max flow", unit="cmH2O", min_value=-20, max_value=150, example="25", help_text="Measured on urodynamics. Normal ~20-30. High pressure = obstruction or detrusor hyperactivity."),
            InputMetadata("qmax", "Maximum Flow Rate", InputType.NUMERIC, True, "Peak urinary flow rate", unit="mL/s", min_value=1, max_value=50, example="15", help_text="Normal >15 mL/s (men) or >20 mL/s (women). <10 suggests obstruction or weakness."),
        ]

    def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate urodynamic inputs."""

        is_valid, msg = self._validate_required(inputs, ["pdet_at_qmax", "qmax"])
        if not is_valid:
            return False, msg

        # Validate ranges
        is_valid, msg = self._validate_range(
            inputs["pdet_at_qmax"],
            min_val=0,
            max_val=200,
            param_name="pdet_at_qmax"
        )
        if not is_valid:
            return False, msg

        is_valid, msg = self._validate_range(
            inputs["qmax"],
            min_val=1,
            max_val=50,
            param_name="qmax"
        )
        if not is_valid:
            return False, msg

        return True, None

    def calculate(self, inputs: Dict[str, Any]) -> CalculatorResult:
        """Calculate BOOI and BCI."""

        # Accept both parameter names
        pdet_qmax = float(inputs.get("pdet_at_qmax") or inputs.get("pdet_qmax", 0))
        qmax = float(inputs.get("qmax") or inputs.get("flow_rate", 0))

        # Calculate BOOI
        booi = pdet_qmax - (2 * qmax)

        # Calculate BCI
        bci = pdet_qmax + (5 * qmax)

        # Interpret BOOI
        if booi < 20:
            booi_status = "No obstruction"
            booi_category = "Unobstructed"
        elif booi <= 40:
            booi_status = "Equivocal obstruction"
            booi_category = "Equivocal"
        else:
            booi_status = "Obstructed"
            booi_category = "Obstructed"

        # Interpret BCI
        if bci < 100:
            bci_status = "Weak detrusor contractility"
            contractility_category = "Weak"
        elif bci <= 150:
            bci_status = "Normal contractility"
            contractility_category = "Normal"
        else:
            bci_status = "Strong detrusor contractility"
            contractility_category = "Strong"

        # Build interpretation
        interpretation_parts = [
            f"Detrusor Pressure at Qmax: {pdet_qmax:.0f} cm H2O",
            f"Maximum Flow Rate: {qmax:.1f} mL/s",
            f"BOOI: {booi:.0f} - {booi_status}",
            f"BCI: {bci:.0f} - {bci_status}",
        ]

        # Combined interpretation
        combined_interpretation = ""
        if booi_category == "Obstructed" and contractility_category == "Normal":
            combined_interpretation = "Classic BPH pattern: obstruction with preserved contractility"
            treatment_rec = "Surgical deobstruction (TURP, laser) likely beneficial"
        elif booi_category == "Obstructed" and contractility_category == "Weak":
            combined_interpretation = "Obstruction with borderline contractility - higher surgical risk"
            treatment_rec = "Careful patient selection for surgery; consider less invasive options"
        elif booi_category == "Unobstructed" and contractility_category == "Weak":
            combined_interpretation = "Underactive bladder without obstruction"
            treatment_rec = "Conservative management or intermittent catheterization; avoid surgery"
        elif booi_category == "Unobstructed" and contractility_category == "Normal":
            combined_interpretation = "Neither obstruction nor contractility impairment"
            treatment_rec = "Consider functional voiding disorder; behavioral therapy appropriate"
        else:
            combined_interpretation = "Equivocal findings require clinical correlation"
            treatment_rec = "Recommend repeat study or additional testing"

        interpretation_parts.append(f"Pattern: {combined_interpretation}")
        interpretation_parts.append(f"Treatment consideration: {treatment_rec}")

        result = {
            "pdet_qmax_cm_h2o": round(pdet_qmax, 1),
            "qmax_mL_s": round(qmax, 1),
            "booi": round(booi, 1),
            "booi_category": booi_category,
            "bci": round(bci, 1),
            "contractility_category": contractility_category,
            "combined_pattern": combined_interpretation,
        }

        recommendations = [
            treatment_rec,
            "Consider symptoms, imaging, and clinical findings in decision-making",
        ]

        if booi_category == "Obstructed":
            recommendations.append("Medical therapy (alpha-blockers) if not already trialed")
        if contractility_category == "Weak":
            recommendations.append("Avoid anticholinergics due to weak contractility")

        interpretation = ". ".join(interpretation_parts) + "."

        # Determine risk_level based on obstruction status
        if booi_category == "Obstructed":
            risk_level = "Abnormal"
        elif booi_category == "Equivocal":
            risk_level = "Borderline"
        else:
            risk_level = "Normal"

        return CalculatorResult(
            calculator_id=self.calculator_id,
            calculator_name=self.name,
            result=result,
            interpretation=interpretation,
            risk_level=risk_level,
            recommendations=recommendations,
            references=self.references,
        )
