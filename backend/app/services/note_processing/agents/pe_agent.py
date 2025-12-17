"""
PE (Physical Exam) Agent

Returns static template for Physical Exam section.

The PE section is filled in by the provider during the actual patient visit,
so this returns a standard template structure for the provider to complete.
"""

from typing import List, Dict


def synthesize_pe(gu_notes: List[Dict[str, str]] = None, non_gu_notes: List[Dict[str, str]] = None) -> str:
    """
    Return static Physical Exam template.

    PE findings can only be documented during the actual exam, so this returns
    a template structure for the provider to fill in during the visit.

    Args:
        gu_notes: List of GU note dictionaries (not used - template is static)
        non_gu_notes: List of non-GU note dictionaries (not used - template is static)

    Returns:
        Static PE template with standard subsections
    """
    return """PHYSICAL EXAM:

GENERAL: Well-developed, well-nourished gentleman with appropriate orientation, mood, affect, demeanor, and dress.
HEENT: Normal symmetric, non-tender neck without mass/thyromegaly to palpation.
CHEST: Normal respiratory effort; no gynecomastia or masses.
ABDOMEN: Soft, non-tender, non-distended, without masses or organomegaly. No palpable hernias.
GU: No CVAT or bladder tenderness/fullness.
RECTAL: Normal anus and perineum; intact sphincter tone; no hemorrhoids or fissures. Prostate exam deferred/performed (choose one).
PROSTATE: [To be documented during exam]
CNS: Alert and oriented; normal gait; intact cranial nerves; no focal deficits."""
