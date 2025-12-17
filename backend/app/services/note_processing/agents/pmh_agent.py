"""
PMH (Past Medical History) Agent

Returns PMH from ALL PROBLEMS LIST. No synthesis needed - just formatting.
"""

from typing import List, Dict


def synthesize_pmh(document_pmh: str, gu_notes: List[Dict[str, str]], non_gu_notes: List[Dict[str, str]]) -> str:
    """
    Return PMH from ALL PROBLEMS LIST.

    Per instructions: PMH comes from the ALL PROBLEMS LIST format,
    not from note extractions. This agent just formats the document-level PMH.

    Args:
        document_pmh: PMH extracted from ALL PROBLEMS LIST (document-level)
        gu_notes: GU note dictionaries (not used)
        non_gu_notes: Non-GU note dictionaries (not used)

    Returns:
        Formatted, enumerated PMH list
    """
    if not document_pmh:
        return ""

    # Split into lines and enumerate
    diagnoses = [d.strip() for d in document_pmh.split('\n') if d.strip()]

    # Format as numbered list
    formatted_pmh = '\n'.join([f"{i}. {diagnosis}" for i, diagnosis in enumerate(diagnoses, 1)])

    return formatted_pmh
