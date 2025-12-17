"""
Dietary History Agent

Combines dietary histories from all notes.
"""

from typing import List, Dict
from ..llm_helper import combine_sections_with_llm


def synthesize_diet(gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize dietary history from GU notes.

    Per instructions: Only combine DHx from GU notes.

    Args:
        gu_notes: List of GU note dictionaries

    Returns:
        Combined dietary history
    """
    all_diet = []

    for note in gu_notes:
        if note.get("DHx"):
            all_diet.append(note["DHx"])

    if not all_diet:
        return ""

    if len(all_diet) == 1:
        return all_diet[0]

    instructions = "Combine these dietary history entries into a single, current summary. Remove duplicates. Focus on urologically relevant diet information (fluid intake, sodium, calcium, oxalate, etc.)."

    return combine_sections_with_llm("Dietary History", all_diet, instructions)
