"""
ROS (Review of Systems) Agent

Returns static template for Review of Systems section.

The ROS is completed by the provider during the actual patient visit,
so this returns a standard template structure for the provider to fill in.
"""

from typing import List, Dict


def synthesize_ros(gu_notes: List[Dict[str, str]] = None, non_gu_notes: List[Dict[str, str]] = None) -> str:
    """
    Return static Review of Systems template.

    ROS findings are documented during the patient interview/visit, so this
    returns a template structure for the provider to complete during the visit.

    Args:
        gu_notes: List of GU note dictionaries (not used - template is static)
        non_gu_notes: List of non-GU note dictionaries (not used - template is static)

    Returns:
        Static ROS template with standard organ systems
    """
    return """GENERAL ROS:
Gen: Independent ADL's, No fever, chills, weight loss
EENT: No recent visual changes, no stiff neck or limited range of motion
Derm: No abnormal or changing skin lesions
CV: No chest pain at rest; No palpitations, No syncope, No claudication, No PND; No easy bleeding or bruising
RESP: No report of dyspnea or SOB at rest
GI: No diarrhea, nausea, vomiting
GU: See HPI
MSK: No myalgias or new bone pain
Neuro: No headache, syncope, dizziness
CNS: [To be documented during exam]"""
