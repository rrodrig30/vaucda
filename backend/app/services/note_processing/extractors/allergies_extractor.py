"""
Allergies Extractor

Extracts allergy information from clinical notes.
"""

import re


def extract_allergies(note_content: str) -> str:
    """
    Extract allergies from a clinical note.

    Common markers: "ALLERGIES:", "Allergies:", "Adverse Reactions:"

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted allergies text, or "" if not found
    """
    # Pattern: "ALLERGIES:" or "Adverse Reactions:" followed by content
    pattern = r'(?:ALLERGIES|Allergies|Adverse Reactions|ADRs?):\s*(.*?)(?=\n\s*(?:MEDICATIONS:|ASSESSMENT:|PLAN:|ROS:|PE:|PHYSICAL|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        allergies_text = match.group(1).strip()

        # Common "no allergies" patterns
        if re.search(r'(no\s+known|nkda|none\s+known|no\s+allergies)', allergies_text, re.IGNORECASE):
            return "No known drug allergies (NKDA)"

        # Clean up whitespace
        allergies_text = re.sub(r' +', ' ', allergies_text)
        allergies_text = re.sub(r'\n{3,}', '\n', allergies_text)

        return allergies_text

    return ""
