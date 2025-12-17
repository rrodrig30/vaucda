"""
Plan Extractor

Extracts plan section from clinical notes.
"""

import re


def extract_plan(note_content: str) -> str:
    """
    Extract Plan from a clinical note.

    Common markers: "PLAN:", "Plan:", "Recommendations:"

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted plan text, or "" if not found
    """
    # Pattern: "PLAN:" or "Recommendations:" followed by content
    pattern = r'(?:PLAN|Plan|RECOMMENDATIONS|Recommendations):\s*(.*?)(?=\n\s*(?:------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        plan_text = match.group(1).strip()

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
            r'ID:.*',
            r'Time of Start:.*',
            r'Time End:.*',
            r'Total Time Spent:.*',
            r'Exm Date:.*'
        ]

        for pattern_str in va_metadata_patterns:
            plan_text = re.sub(pattern_str, '', plan_text, flags=re.IGNORECASE | re.MULTILINE)

        # Clean up whitespace
        plan_text = re.sub(r' +', ' ', plan_text)
        plan_text = re.sub(r'\n{3,}', '\n\n', plan_text)
        plan_text = plan_text.strip()

        return plan_text if len(plan_text) > 10 else ""

    return ""
