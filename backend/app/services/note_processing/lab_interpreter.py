"""
Structured Lab Interpreter

ROOT CAUSE #3 FIX: Lab values were passed as free text to the LLM without
structured interpretation. The LLM would misinterpret reference ranges,
claiming values were "elevated" when they were actually normal (e.g.,
testosterone of 203 ng/dL in reference range 175-781 ng/dL).

This module provides:
1. Parsing of lab values with reference ranges
2. Computation of whether values are NORMAL, HIGH, or LOW
3. Clear interpretation text that prevents LLM hallucinations
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class LabStatus(Enum):
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    LOW = "LOW"
    CRITICAL_HIGH = "CRITICAL_HIGH"
    CRITICAL_LOW = "CRITICAL_LOW"
    UNKNOWN = "UNKNOWN"


@dataclass
class LabResult:
    """Structured lab result with interpretation."""
    name: str
    value: float
    unit: str
    ref_low: Optional[float]
    ref_high: Optional[float]
    status: LabStatus
    date: Optional[str] = None
    raw_text: Optional[str] = None

    def get_interpretation(self) -> str:
        """Get human-readable interpretation."""
        if self.status == LabStatus.NORMAL:
            return f"{self.name}: {self.value} {self.unit} - NORMAL (ref: {self.ref_low}-{self.ref_high})"
        elif self.status == LabStatus.HIGH:
            return f"{self.name}: {self.value} {self.unit} - ELEVATED (ref: {self.ref_low}-{self.ref_high})"
        elif self.status == LabStatus.LOW:
            return f"{self.name}: {self.value} {self.unit} - LOW (ref: {self.ref_low}-{self.ref_high})"
        elif self.status == LabStatus.CRITICAL_HIGH:
            return f"{self.name}: {self.value} {self.unit} - CRITICALLY ELEVATED (ref: {self.ref_low}-{self.ref_high})"
        elif self.status == LabStatus.CRITICAL_LOW:
            return f"{self.name}: {self.value} {self.unit} - CRITICALLY LOW (ref: {self.ref_low}-{self.ref_high})"
        else:
            return f"{self.name}: {self.value} {self.unit} - UNABLE TO INTERPRET"


# Standard reference ranges for common urologic labs
# These are typical adult male reference ranges
STANDARD_REFERENCE_RANGES = {
    # Testosterone
    'testosterone': (175, 781, 'ng/dL'),
    'total testosterone': (175, 781, 'ng/dL'),
    'testosterone, serum total': (175, 781, 'ng/dL'),
    'testosterone,serum total': (175, 781, 'ng/dL'),
    'free testosterone': (5.0, 21.0, 'pg/mL'),

    # PSA
    'psa': (0.0, 4.0, 'ng/mL'),
    'psa total': (0.0, 4.0, 'ng/mL'),

    # Renal function
    'creatinine': (0.7, 1.3, 'mg/dL'),
    'bun': (7, 20, 'mg/dL'),
    'egfr': (90, 120, 'mL/min/1.73m2'),
    'gfr': (90, 120, 'mL/min/1.73m2'),

    # Urinalysis
    'wbc': (0, 5, '/HPF'),
    'rbc': (0, 3, '/HPF'),

    # Metabolic panel
    'sodium': (136, 145, 'mEq/L'),
    'potassium': (3.5, 5.0, 'mEq/L'),
    'chloride': (98, 106, 'mEq/L'),
    'co2': (23, 29, 'mEq/L'),
    'bicarbonate': (23, 29, 'mEq/L'),
    'glucose': (70, 100, 'mg/dL'),
    'calcium': (8.5, 10.5, 'mg/dL'),

    # Liver function
    'ast': (10, 40, 'U/L'),
    'alt': (7, 56, 'U/L'),
    'alkaline phosphatase': (44, 147, 'U/L'),
    'alk phos': (44, 147, 'U/L'),
    'total bilirubin': (0.1, 1.2, 'mg/dL'),
    'albumin': (3.5, 5.0, 'g/dL'),

    # Complete blood count
    'wbc count': (4.5, 11.0, 'K/uL'),
    'hemoglobin': (13.5, 17.5, 'g/dL'),
    'hematocrit': (38.3, 48.6, '%'),
    'platelets': (150, 400, 'K/uL'),

    # Endocrine
    'a1c': (4.0, 5.6, '%'),
    'hemoglobin a1c': (4.0, 5.6, '%'),
    'hba1c': (4.0, 5.6, '%'),
    'tsh': (0.4, 4.0, 'mIU/L'),
    'lh': (1.5, 9.3, 'mIU/mL'),
    'fsh': (1.5, 12.4, 'mIU/mL'),
    'prolactin': (2.0, 18.0, 'ng/mL'),
    'vitamin d': (30, 100, 'ng/mL'),
    '25-hydroxy vitamin d': (30, 100, 'ng/mL'),

    # Stone evaluation
    '24h urine calcium': (100, 300, 'mg/24hr'),
    '24h urine oxalate': (0, 40, 'mg/24hr'),
    '24h urine uric acid': (250, 750, 'mg/24hr'),
    '24h urine citrate': (320, 1240, 'mg/24hr'),
    'urine ph': (4.5, 8.0, ''),

    # Tumor markers
    'afp': (0, 8.3, 'ng/mL'),
    'alpha fetoprotein': (0, 8.3, 'ng/mL'),
    'hcg': (0, 5, 'mIU/mL'),
    'ldh': (140, 280, 'U/L'),
    'lactate dehydrogenase': (140, 280, 'U/L'),
}


def parse_lab_value(text: str) -> Optional[LabResult]:
    """
    Parse a lab result string into a structured LabResult.

    Handles various formats:
    - "Testosterone 203 ng/dL (175-781)"
    - "PSA: 5.2 ng/mL (H)"
    - "Testosterone,Serum Total     203 L   ng/dL   175 - 781"
    - "TESTOSTERONE: 203.49 ng/dL (ref: 175-781) - Nov 6, 2025"

    Args:
        text: Raw lab result text

    Returns:
        LabResult if parseable, None otherwise
    """
    if not text:
        return None

    # Try various parsing patterns
    result = None

    # Pattern 1: VA format with whitespace and H/L flag
    # "Testosterone,Serum Total     203 L   ng/dL   175 - 781"
    va_pattern = r'([A-Za-z][A-Za-z0-9\s,]+?)\s+(\d+\.?\d*)\s*([HL])?\s+(ng/dL|ng/mL|mg/dL|pg/mL|%|U/L|mIU/mL|K/uL|g/dL|mEq/L|IU/L)?\s*(?:(\d+\.?\d*)\s*-\s*(\d+\.?\d*))?'
    va_match = re.search(va_pattern, text, re.IGNORECASE)

    if va_match:
        name = va_match.group(1).strip().lower()
        value = float(va_match.group(2))
        hl_flag = va_match.group(3)
        unit = va_match.group(4) or ""
        ref_low = float(va_match.group(5)) if va_match.group(5) else None
        ref_high = float(va_match.group(6)) if va_match.group(6) else None

        # Look up standard reference if not provided
        if ref_low is None or ref_high is None:
            std_ref = STANDARD_REFERENCE_RANGES.get(name)
            if std_ref:
                ref_low, ref_high, std_unit = std_ref
                if not unit:
                    unit = std_unit

        # Determine status
        status = _determine_status(value, ref_low, ref_high, hl_flag)

        result = LabResult(
            name=va_match.group(1).strip(),
            value=value,
            unit=unit,
            ref_low=ref_low,
            ref_high=ref_high,
            status=status,
            raw_text=text
        )

    # Pattern 2: Simple format with reference in parentheses
    # "Testosterone: 203 ng/dL (175-781)"
    simple_pattern = r'([A-Za-z][A-Za-z0-9\s]+?):\s*(\d+\.?\d*)\s*(ng/dL|ng/mL|mg/dL|pg/mL|%|U/L|mIU/mL|K/uL|g/dL|mEq/L|IU/L)?\s*\((?:ref:?\s*)?(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\)'
    simple_match = re.search(simple_pattern, text, re.IGNORECASE)

    if simple_match and not result:
        name = simple_match.group(1).strip()
        value = float(simple_match.group(2))
        unit = simple_match.group(3) or ""
        ref_low = float(simple_match.group(4))
        ref_high = float(simple_match.group(5))

        status = _determine_status(value, ref_low, ref_high)

        result = LabResult(
            name=name,
            value=value,
            unit=unit,
            ref_low=ref_low,
            ref_high=ref_high,
            status=status,
            raw_text=text
        )

    return result


def _determine_status(
    value: float,
    ref_low: Optional[float],
    ref_high: Optional[float],
    hl_flag: Optional[str] = None
) -> LabStatus:
    """
    Determine lab status based on value and reference range.

    Args:
        value: Lab value
        ref_low: Reference range lower bound
        ref_high: Reference range upper bound
        hl_flag: Optional H/L flag from lab result

    Returns:
        LabStatus enum value
    """
    # If we have H/L flag, use it as hint but verify with reference range
    if hl_flag:
        if hl_flag.upper() == 'H' and ref_high and value > ref_high:
            return LabStatus.HIGH
        elif hl_flag.upper() == 'L' and ref_low and value < ref_low:
            return LabStatus.LOW

    # Use reference range if available
    if ref_low is not None and ref_high is not None:
        if value < ref_low:
            # Check for critically low (< 50% of lower bound)
            if value < ref_low * 0.5:
                return LabStatus.CRITICAL_LOW
            return LabStatus.LOW
        elif value > ref_high:
            # Check for critically high (> 200% of upper bound)
            if value > ref_high * 2:
                return LabStatus.CRITICAL_HIGH
            return LabStatus.HIGH
        else:
            return LabStatus.NORMAL

    return LabStatus.UNKNOWN


def interpret_labs_from_note(note_text: str) -> Dict[str, LabResult]:
    """
    Extract and interpret all lab values from a clinical note.

    Args:
        note_text: Clinical note text

    Returns:
        Dictionary mapping lab name to LabResult
    """
    results = {}

    # Look for ENDOCRINE LABS section
    endocrine_match = re.search(
        r'ENDOCRINE LABS:?\s*\n(.*?)(?=\n\n|\nLABS:|\nIMAGING:|$)',
        note_text,
        re.IGNORECASE | re.DOTALL
    )

    if endocrine_match:
        section = endocrine_match.group(1)
        for line in section.split('\n'):
            line = line.strip()
            if not line:
                continue

            lab_result = parse_lab_value(line)
            if lab_result:
                results[lab_result.name.lower()] = lab_result

    # Look for LABS section
    labs_match = re.search(
        r'(?:^|\n)LABS:?\s*\n(.*?)(?=\n\n|\nIMAGING:|\nROS:|$)',
        note_text,
        re.IGNORECASE | re.DOTALL
    )

    if labs_match:
        section = labs_match.group(1)
        for line in section.split('\n'):
            line = line.strip()
            if not line:
                continue

            lab_result = parse_lab_value(line)
            if lab_result:
                key = lab_result.name.lower()
                if key not in results:  # Don't overwrite existing results
                    results[key] = lab_result

    return results


def get_structured_lab_interpretation(note_text: str) -> str:
    """
    Generate structured lab interpretation text for LLM consumption.

    This is the main entry point for ROOT CAUSE #3 fix. It provides
    clear, unambiguous lab interpretations to prevent LLM hallucinations.

    Args:
        note_text: Clinical note text

    Returns:
        Structured interpretation text
    """
    results = interpret_labs_from_note(note_text)

    if not results:
        return ""

    interpretations = []
    interpretations.append("=== STRUCTURED LAB INTERPRETATION ===")
    interpretations.append("(Values compared against standard reference ranges)")
    interpretations.append("")

    # Categorize by status
    normal_labs = []
    abnormal_labs = []
    unknown_labs = []

    for name, result in results.items():
        if result.status == LabStatus.NORMAL:
            normal_labs.append(result)
        elif result.status in [LabStatus.HIGH, LabStatus.LOW, LabStatus.CRITICAL_HIGH, LabStatus.CRITICAL_LOW]:
            abnormal_labs.append(result)
        else:
            unknown_labs.append(result)

    if abnormal_labs:
        interpretations.append("ABNORMAL VALUES:")
        for lab in abnormal_labs:
            interpretations.append(f"  - {lab.get_interpretation()}")
        interpretations.append("")

    if normal_labs:
        interpretations.append("NORMAL VALUES:")
        for lab in normal_labs:
            interpretations.append(f"  - {lab.get_interpretation()}")
        interpretations.append("")

    if unknown_labs:
        interpretations.append("VALUES WITHOUT REFERENCE (verify manually):")
        for lab in unknown_labs:
            interpretations.append(f"  - {lab.name}: {lab.value} {lab.unit}")
        interpretations.append("")

    interpretations.append("=== END LAB INTERPRETATION ===")

    return '\n'.join(interpretations)


def interpret_testosterone(value: float, unit: str = 'ng/dL') -> str:
    """
    Specifically interpret testosterone values with clear status.

    This is called to prevent the specific "Elevated Testosterone" hallucination
    that occurred in ROOT CAUSE #3.

    Args:
        value: Testosterone value
        unit: Unit of measurement

    Returns:
        Clear interpretation string
    """
    # Standard male testosterone reference range
    ref_low = 175
    ref_high = 781

    if unit.lower() in ['ng/dl', 'ng/dL']:
        if value < ref_low:
            return f"Testosterone {value} ng/dL: LOW (below {ref_low} ng/dL reference minimum)"
        elif value > ref_high:
            return f"Testosterone {value} ng/dL: ELEVATED (above {ref_high} ng/dL reference maximum)"
        else:
            return f"Testosterone {value} ng/dL: NORMAL (within {ref_low}-{ref_high} ng/dL reference range)"
    else:
        return f"Testosterone {value} {unit}: Unable to interpret - non-standard units"


def interpret_psa(value: float) -> str:
    """
    Specifically interpret PSA values with clinical context.

    Args:
        value: PSA value in ng/mL

    Returns:
        Clear interpretation string
    """
    if value <= 4.0:
        return f"PSA {value} ng/mL: NORMAL (below 4.0 ng/mL threshold)"
    elif value <= 10.0:
        return f"PSA {value} ng/mL: ELEVATED (above 4.0 ng/mL; further evaluation recommended)"
    elif value <= 20.0:
        return f"PSA {value} ng/mL: SIGNIFICANTLY ELEVATED (prostate biopsy indicated)"
    else:
        return f"PSA {value} ng/mL: HIGHLY ELEVATED (high concern for prostate cancer)"
