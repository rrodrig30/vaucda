"""
PE (Physical Exam) Agent

Returns gender-appropriate template for Physical Exam section.

The PE section is filled in by the provider during the actual patient visit,
so this returns a standard template structure for the provider to complete.

Gender-specific considerations:
- Male patients: Include RECTAL and PROSTATE exam sections
- Female patients: Exclude PROSTATE section, include PELVIC exam placeholder
"""

from typing import List, Dict, Optional


def synthesize_pe(
    gu_notes: List[Dict[str, str]] = None,
    non_gu_notes: List[Dict[str, str]] = None,
    patient_sex: Optional[str] = None
) -> str:
    """
    Return gender-appropriate Physical Exam template.

    PE findings can only be documented during the actual exam, so this returns
    a template structure for the provider to fill in during the visit.

    Args:
        gu_notes: List of GU note dictionaries (not used - template is static)
        non_gu_notes: List of non-GU note dictionaries (not used - template is static)
        patient_sex: Patient sex - "MALE", "FEMALE", or None/unknown

    Returns:
        Gender-appropriate PE template with standard subsections
    """
    # Normalize sex to uppercase for comparison
    sex = (patient_sex or "").upper().strip()
    is_female = sex in ("FEMALE", "F")
    is_male = sex in ("MALE", "M")

    # Gender-appropriate terminology
    if is_female:
        gender_term = "female"
    elif is_male:
        gender_term = "gentleman"
    else:
        gender_term = "patient"  # Gender-neutral fallback

    # Build common sections
    common_sections = f"""PHYSICAL EXAM:

GENERAL: Well-developed, well-nourished {gender_term} with appropriate orientation, mood, affect, demeanor, and dress.
HEENT: Normal symmetric, non-tender neck without mass/thyromegaly to palpation.
CHEST: Normal respiratory effort; no gynecomastia or masses.
ABDOMEN: Soft, non-tender, non-distended, without masses or organomegaly. No palpable hernias.
GU: No CVAT or bladder tenderness/fullness."""

    # Gender-specific GU exam sections
    if is_female:
        # Female patients: No prostate exam, include pelvic exam placeholder
        gender_specific = """
PELVIC:
CNS: Alert and oriented x3; steady gait; no focal neurological deficits."""
    else:
        # Male patients (or unknown): Include rectal and prostate exam
        gender_specific = """
RECTAL: Normal anus and perineum; intact sphincter tone; no hemorrhoids or rectal masses.
PROSTATE:
CNS: Alert and oriented x3; steady gait; no focal neurological deficits."""

    return common_sections + gender_specific
