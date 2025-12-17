"""
Chief Complaint (CC) Agent

Combines CCs from all notes, focusing on urologic concerns.
"""

from typing import List, Dict
from ..llm_helper import combine_sections_with_llm
from .history_cleaners import clean_llm_commentary


def synthesize_cc(gu_notes: List[Dict[str, str]], non_gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize Chief Complaint from GU notes ONLY.

    Per user requirements: Only use UROLOGY notes. Do not include non-urologic content.

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: Not used - kept for compatibility

    Returns:
        Synthesized CC text focused on urologic concerns
    """
    # Collect CCs from GU notes ONLY
    all_ccs = []

    for note in gu_notes:
        if note.get("CC"):
            all_ccs.append(note["CC"])

    if not all_ccs:
        return ""

    # If only one CC, return it with terminology correction
    if len(all_ccs) == 1:
        cc_text = all_ccs[0]
        # Replace "Consult for" with "Followup for" or "Follow-up for" (case-insensitive)
        import re
        cc_text = re.sub(r'\bConsult\s+for\b', 'Follow-up for', cc_text, flags=re.IGNORECASE)
        cc_text = re.sub(r'\bconsult\b', 'follow-up', cc_text, flags=re.IGNORECASE)

        # Remove "New patient" prefix (followup visits are not new patients)
        cc_text = re.sub(r'^\s*New\s+patient\s+', '', cc_text, flags=re.IGNORECASE)
        return cc_text

    # Use LLM to combine CCs, focusing on urologic concerns
    instructions = """
Focus on urologically relevant complaints only. Include:
- Genitourinary symptoms (erectile dysfunction, BPH, urinary symptoms, etc.)
- Prostate issues (elevated PSA, prostate cancer, etc.)
- Kidney/bladder issues
- Sexual health concerns
- Male fertility concerns

EXCLUDE non-urologic complaints (shoulder pain, general wellness visits, etc.) unless they have urologic implications.
Keep the final CC concise (1-2 lines).

IMPORTANT TERMINOLOGY:
- Replace "Consult for" with "Followup for" (this is a followup visit, not a new consult)
- Replace "consult" with "followup" in all contexts

CRITICAL: Provide ONLY the concise chief complaint. NO meta-commentary, NO explanations, NO preamble like "Here is" or "Based on". Just the chief complaint itself.
"""

    synthesized_cc = combine_sections_with_llm(
        section_name="Chief Complaint",
        section_instances=all_ccs,
        instructions=instructions
    )

    return clean_llm_commentary(synthesized_cc)
