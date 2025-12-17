"""
Chief Complaint (CC) Extractor

Extracts the Chief Complaint from a clinical note.
"""

import re


def extract_cc(note_content: str) -> str:
    """
    Extract Chief Complaint from a clinical note.

    The CC typically appears after "CC:" or "Chief Complaint:" markers.
    It's usually a single line or short paragraph.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted CC text, or "" if not found
    """
    # Pattern 1: "CC:" followed by content until next section
    # Common next sections: HPI, History, Reason for Visit, etc.
    pattern1 = r'CC:\s*([^\n]+(?:\n(?!HPI:|History|Reason for Visit|HISTORY|RFV:)[^\n]+)*)'

    # Pattern 2: "Chief Complaint:" followed by content
    pattern2 = r'Chief Complaint:\s*([^\n]+(?:\n(?!HPI:|History|Reason for Visit|HISTORY)[^\n]+)*)'

    # Try pattern 1 first (more common in VA notes)
    match = re.search(pattern1, note_content, re.IGNORECASE | re.MULTILINE)
    if match:
        cc_text = match.group(1).strip()
        # Clean up: remove excessive whitespace
        cc_text = re.sub(r'\s+', ' ', cc_text)
        return cc_text

    # Try pattern 2
    match = re.search(pattern2, note_content, re.IGNORECASE | re.MULTILINE)
    if match:
        cc_text = match.group(1).strip()
        cc_text = re.sub(r'\s+', ' ', cc_text)
        return cc_text

    # Not found
    return ""
