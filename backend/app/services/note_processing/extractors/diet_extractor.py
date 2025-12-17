"""
Dietary History (DHx) Extractor

Extracts dietary history from clinical notes.
"""

import re


def extract_diet(note_content: str) -> str:
    """
    Extract Dietary History from a clinical note.

    Common markers: "DHx:", "Diet:", "Dietary History:"

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted dietary history text, or "" if not found
    """
    # Pattern: "DHx:" or "Diet:" or "Dietary History:" followed by content
    pattern = r'(?:DHx|Diet(?:ary)?\s+History|Diet):\s*(.*?)(?=\n\s*(?:PMH:|PSH:|Social|Family|ROS:|PE:|PHYSICAL|EXAM:|ASSESSMENT:|PLAN:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        diet_text = match.group(1).strip()
        # Clean up whitespace
        diet_text = re.sub(r' +', ' ', diet_text)
        diet_text = re.sub(r'\n{3,}', '\n\n', diet_text)
        return diet_text

    return ""
