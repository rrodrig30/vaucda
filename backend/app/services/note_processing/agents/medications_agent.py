"""
Medications Agent

Returns medications from VA medication list. No synthesis needed - just formatting.
"""

from typing import List, Dict


def synthesize_medications(document_medications: str, gu_notes: List[Dict[str, str]]) -> str:
    """
    Return medications from VA medication list.

    Per instructions: Medications come from the VA medication list format,
    not from note extractions. This agent just formats the document-level medications.

    Args:
        document_medications: Medications extracted from VA list (document-level)
        gu_notes: GU note dictionaries (not used)

    Returns:
        Formatted, enumerated medications list
    """
    if not document_medications:
        return ""

    # Split into lines and deduplicate
    meds = [m.strip() for m in document_medications.split('\n') if m.strip()]

    # Deduplicate while preserving order
    seen = set()
    unique_meds = []
    for med in meds:
        if med not in seen:
            seen.add(med)
            unique_meds.append(med)

    # Format as numbered list
    formatted_meds = '\n'.join([f"{i}. {med}" for i, med in enumerate(unique_meds, 1)])

    return formatted_meds
