"""
Sexual History Agent

Combines sexual histories from all notes.
"""

from typing import List, Dict
from ..llm_helper import combine_sections_with_llm
from .history_cleaners import clean_llm_commentary


def synthesize_sexual(gu_notes: List[Dict[str, str]], non_gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize sexual history from all notes.

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries

    Returns:
        Combined sexual history
    """
    all_sexual = []

    for note in gu_notes:
        if note.get("Sexual"):
            all_sexual.append(note["Sexual"])

    for note in non_gu_notes:
        if note.get("Sexual"):
            all_sexual.append(note["Sexual"])

    if not all_sexual:
        return ""

    if len(all_sexual) == 1:
        return all_sexual[0]

    instructions = "Combine these sexual history entries into a single, current summary. Remove duplicates. Include sexual activity, erectile function, fertility concerns, etc."

    result = combine_sections_with_llm("Sexual History", all_sexual, instructions)
    return clean_llm_commentary(result)
