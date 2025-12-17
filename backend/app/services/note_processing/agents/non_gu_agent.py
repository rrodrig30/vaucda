"""
Non-GU Agent

Processes all non-urology notes and extracts structured data into non_gu_note dictionaries.
"""

from typing import List, Dict
from ..extractors import (
    extract_cc,
    extract_hpi,
    extract_diet,
    extract_pmh_from_note,
    extract_psh,
    extract_social,
    extract_family,
    extract_assessment,
    extract_plan,
)


def process_non_gu_notes(non_gu_notes: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Process all non-GU notes and extract structured data.

    Non-GU notes contain fewer fields than GU notes. We extract only
    the clinically relevant sections that might have urologic impact.

    Args:
        non_gu_notes: List of non-GU note dictionaries from identify_notes()
                      Each dict has: {"title": "...", "date": "...", "content": "..."}

    Returns:
        List of non_gu_note dictionaries, one per input note:
        [
            {
                "CC": "...",
                "HPI": "...",
                "DHx": "...",
                "PMH": "...",
                "PSH": "...",
                "Social": "...",
                "Family": "...",
                "Assessment": "...",
                "Plan": ""
            },
            ...
        ]
    """
    non_gu_note_list = []

    for note in non_gu_notes:
        note_content = note["content"]

        # Extract clinically relevant sections
        non_gu_note = {
            "CC": extract_cc(note_content),
            "HPI": extract_hpi(note_content),
            "DHx": extract_diet(note_content),
            "PMH": extract_pmh_from_note(note_content),
            "PSH": extract_psh(note_content),
            "Social": extract_social(note_content),
            "Family": extract_family(note_content),
            "Assessment": extract_assessment(note_content),
            "Plan": extract_plan(note_content)
        }

        non_gu_note_list.append(non_gu_note)

    return non_gu_note_list
