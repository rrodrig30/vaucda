"""
Testosterone Extractor

Extracts testosterone levels from lab results.
"""

import re


def extract_testosterone(note_content: str) -> str:
    """
    Extract testosterone levels from clinical notes or lab sections.

    Looks for:
    - Total Testosterone
    - Free Testosterone
    - % Free Testosterone

    Args:
        note_content: Full text of a clinical note or lab section

    Returns:
        Extracted testosterone data, or "" if not found
    """
    testosterone_entries = []

    # Pattern: Testosterone type + value + date
    # Examples:
    # "Total Testosterone: 350 ng/dL (01/15/2024)"
    # "Free Testosterone 8.5 pg/mL"

    patterns = [
        r'(Total\s+Testosterone)[:\s]+(\d+\.?\d*)\s*(?:ng/dL|ng/dl)?\s*(?:\()?([A-Za-z]{3}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})?',
        r'(Free\s+Testosterone)[:\s]+(\d+\.?\d*)\s*(?:pg/mL|pg/ml)?\s*(?:\()?([A-Za-z]{3}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})?',
        r'(%\s*Free\s+Testosterone)[:\s]+(\d+\.?\d*)\s*%?\s*(?:\()?([A-Za-z]{3}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})?',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, note_content, re.IGNORECASE):
            test_type = match.group(1).strip()
            value = match.group(2).strip()
            date = match.group(3).strip() if match.group(3) else ""

            if date:
                testosterone_entries.append(f"{date}: {test_type} = {value}")
            else:
                testosterone_entries.append(f"{test_type} = {value}")

    if not testosterone_entries:
        return ""

    return '\n'.join(testosterone_entries)
