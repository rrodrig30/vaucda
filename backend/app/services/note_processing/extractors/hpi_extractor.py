"""
History of Present Illness (HPI) Extractor

Extracts the HPI section from a clinical note.
"""

import re


def extract_hpi(note_content: str) -> str:
    """
    Extract History of Present Illness from a clinical note.

    The HPI typically appears after "HPI:" marker and continues until
    the next major section (PMH, PSH, ROS, etc.).

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted HPI text, or "" if not found
    """
    # Pattern: "HPI:" followed by content until next major section
    # Common next sections: IPSS table (+---), PMH, PSH, ROS, PE, PHYSICAL, EXAM, ASSESSMENT, etc.
    # CRITICAL: Stop at IPSS table boundary (lines starting with +)
    # Note: Removed problematic ^\s*[A-Z][A-Z\s]+:(?!\w) pattern that was matching mid-line words

    pattern = r'HPI:\s*(.*?)(?=\n\s*(?:\+---|\+====|IPSS:|PMH:|PSH:|ROS:|PE:|PHYSICAL EXAM:|EXAM:|ASSESSMENT:|PLAN:|DIETARY HISTORY:|SOCIAL HISTORY:|FAMILY HISTORY:|SEXUAL HISTORY:|Past Medical History|Past Surgical History|Review of Systems|Physical Exam|MEDICATIONS:|ALLERGIES:|Social History|======))'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL)
    if match:
        hpi_text = match.group(1).strip()

        # Clean up: normalize whitespace but preserve paragraph breaks
        # Replace multiple spaces with single space
        hpi_text = re.sub(r' +', ' ', hpi_text)
        # Replace 3+ newlines with 2 (preserve paragraph breaks)
        hpi_text = re.sub(r'\n{3,}', '\n\n', hpi_text)

        return hpi_text

    # Not found
    return ""
