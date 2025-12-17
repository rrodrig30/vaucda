"""
Family History Agent

Combines family histories from all notes.
"""

from typing import List, Dict
from ..llm_helper import combine_sections_with_llm
from .history_cleaners import clean_llm_commentary


def synthesize_family(gu_notes: List[Dict[str, str]], non_gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize family history from all notes.

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries

    Returns:
        Combined family history
    """
    all_family = []

    for note in gu_notes:
        if note.get("Family"):
            all_family.append(note["Family"])

    for note in non_gu_notes:
        if note.get("Family"):
            all_family.append(note["Family"])

    if not all_family:
        return ""

    if len(all_family) == 1:
        return all_family[0]

    instructions = """Combine these family history entries into a single summary. Remove duplicates.
Include ALL family history details - both urologic and non-urologic conditions.
Maintain the complete family medical history as documented.

CRITICAL: Provide ONLY the factual summary. NO meta-commentary, NO explanations, NO statements like "No information was provided" or parenthetical notes. Just state the facts directly."""

    result = combine_sections_with_llm("Family History", all_family, instructions)
    return clean_llm_commentary(result)
