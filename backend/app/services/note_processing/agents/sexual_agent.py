"""
Sexual History Agent

Combines sexual histories from all notes.
"""

from typing import List, Dict
from ..llm_helper import combine_sections_with_llm
from .history_cleaners import clean_llm_commentary


def synthesize_sexual(
    gu_notes: List[Dict[str, str]],
    non_gu_notes: List[Dict[str, str]],
    document_sexual: str = "",
) -> str:
    """
    Synthesize sexual history from all notes.

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries
        document_sexual: Document-level Sexual History extracted by
            ``extract_sexual(clinical_document)``. Used as a fallback when
            the note-splitter doesn't carve out a note containing the
            section (e.g. SEXUAL HISTORY sits in a header block that
            wasn't tagged GU or non-GU). Mirrors the
            ``document_pathology`` / ``document_imaging`` /
            ``document_medications`` / ``document_allergies`` fallbacks
            already used by sister agents.

    Returns:
        Combined sexual history, or "" if none found anywhere.
    """
    all_sexual = []

    for note in gu_notes:
        if note.get("Sexual"):
            all_sexual.append(note["Sexual"])

    for note in non_gu_notes:
        if note.get("Sexual"):
            all_sexual.append(note["Sexual"])

    # Document-level fallback. Append only if it isn't already represented
    # by one of the per-note extractions (loose substring check — the
    # document text often contains a per-note extraction verbatim).
    if document_sexual:
        doc_sx = document_sexual.strip()
        if doc_sx and not any(doc_sx in s or s.strip() in doc_sx for s in all_sexual):
            all_sexual.append(doc_sx)

    if not all_sexual:
        return ""

    if len(all_sexual) == 1:
        return all_sexual[0]

    instructions = "Combine these sexual history entries into a single, current summary. Remove duplicates. Include sexual activity, erectile function, fertility concerns, etc."

    result = combine_sections_with_llm("Sexual History", all_sexual, instructions)
    return clean_llm_commentary(result)
