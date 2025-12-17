"""
Sexual History Extractor

Extracts sexual history from clinical notes.
"""

import re


def extract_sexual(note_content: str) -> str:
    """
    Extract Sexual History from a clinical note.

    Common markers: "Sexual History:", "SEXUAL:", "Sexual Hx:"

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted sexual history text, or "" if not found
    """
    # Pattern: "Sexual History:" or "SEXUAL:" followed by content
    # Until next major section
    pattern = r'(?:Sexual History|SEXUAL|Sexual Hx):\s*(.*?)(?=\n\s*(?:PAST MEDICAL HISTORY|PMH:|ROS:|PE:|PHYSICAL|EXAM:|ASSESSMENT:|PLAN:|Review of Systems|Physical Exam|MEDICATIONS:|ALLERGIES:|FAMILY HISTORY|SOCIAL HISTORY|------|$))'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL)
    if match:
        sexual_text = match.group(1).strip()
        # Clean up whitespace
        sexual_text = re.sub(r' +', ' ', sexual_text)
        sexual_text = re.sub(r'\n{3,}', '\n\n', sexual_text)
        return sexual_text

    return ""
