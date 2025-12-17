"""
Assessment Extractor

Extracts assessment section from clinical notes.
"""

import re


def extract_assessment(note_content: str) -> str:
    """
    Extract Assessment from a clinical note.

    Common markers: "ASSESSMENT:", "Assessment:", "A/P:", "Assessment and Plan:"

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted assessment text, or "" if not found
    """
    # Pattern: "ASSESSMENT:" followed by content until PLAN or next major section
    # Handle combined "Assessment and Plan:" vs separate "Assessment:" "Plan:"
    pattern = r'(?:ASSESSMENT(?:\s+and\s+Plan)?|A/P|Impression):\s*(.*?)(?=\n\s*(?:PLAN:|Plan:|RECOMMENDATIONS:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        assessment_text = match.group(1).strip()

        # If this is "Assessment and Plan" combined, try to split
        # Look for "Plan:" within the matched text
        plan_split = re.search(r'(.*?)(?:\n\s*PLAN:)(.*)', assessment_text, re.IGNORECASE | re.DOTALL)
        if plan_split:
            # Return only assessment part
            assessment_text = plan_split.group(1).strip()

        # Filter out VA administrative metadata
        va_metadata_patterns = [
            r'Signed:.*',
            r'Facility:.*',
            r'URGENCY:.*',
            r'AUTHOR:.*',
            r'LOCAL TITLE:.*',
            r'STANDARD TITLE:.*',
            r'Dragon Speak Clarification:.*',
            r'Cosigned:.*',
            r'Report Status:.*',
            r'Expected Cosigner:.*',
            r'Date Signed:.*',
            r'Submitted by:.*',
            r'As of:.*',
            r'ID:.*'
        ]

        for pattern_str in va_metadata_patterns:
            assessment_text = re.sub(pattern_str, '', assessment_text, flags=re.IGNORECASE | re.MULTILINE)

        # Clean up whitespace
        assessment_text = re.sub(r' +', ' ', assessment_text)
        assessment_text = re.sub(r'\n{3,}', '\n\n', assessment_text)
        assessment_text = assessment_text.strip()

        return assessment_text if len(assessment_text) > 10 else ""

    return ""
