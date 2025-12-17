"""
PSA (Prostate-Specific Antigen) Curve Extractor

Extracts PSA values and dates from clinical notes.
"""

import re


def extract_psa(note_content: str) -> str:
    """
    Extract PSA curve data from a clinical note.

    PSA data can appear in various formats:
    - "PSA:" section with date/value pairs
    - "PSA Curve:" section
    - Tabular format with dates and values
    - Narrative format: "PSA was 4.2 on 01/15/2024"

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted PSA data, or "" if not found
    """
    psa_entries = []

    # Pattern 1: Look for "PSA:" or "PSA Curve:" section
    # Use non-capturing group and better section boundary detection
    section_pattern = r'(?:PSA(?:\s+Curve)?|Prostate-Specific Antigen):\s*\n((?:.*\n)*?)(?=\n{2,}|\n(?:MEDICATIONS|ALLERGIES|PATHOLOGY|Testosterone|Imaging|PHYSICAL|ASSESSMENT):|$)'

    match = re.search(section_pattern, note_content, re.IGNORECASE | re.MULTILINE)
    if match:
        psa_section = match.group(1).strip()

        # Extract date/value pairs from the section
        # Common formats:
        # "01/15/2024: 4.2"
        # "Jan 15, 2024    4.2"
        # "[r] Jan 15, 2024 14:30    4.2"

        # Pattern: date followed by optional time (4-digit or HH:MM format) followed by PSA value
        # Format examples:
        # [r] Sep 04, 2025 0858    7.46H
        # [r] Sep 04, 2025 08:58    7.46H
        # Sep 04, 2025    7.46
        date_value_pattern = r'(?:\[r\])?\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+(?:(\d{4}|\d{1,2}:\d{2})\s+)?(\d+\.?\d*)(?:H|h)?'

        for match in re.finditer(date_value_pattern, psa_section, re.IGNORECASE):
            date = match.group(1).strip()
            time = match.group(2).strip() if match.group(2) else None
            value = match.group(3).strip()

            # Include time if present
            if time:
                # Convert 4-digit format (0858) to HH:MM (08:58)
                if len(time) == 4 and ':' not in time:
                    time = f"{time[:2]}:{time[2:]}"
                psa_entries.append(f"{date} {time}: {value}")
            else:
                psa_entries.append(f"{date}: {value}")

    # Pattern 2: VA Lab Result Format
    # "Specimen Collection Date: Apr 11, 2025@12:17"
    # "PSA TOTAL                      1.70     ng/mL"
    # Find all PSA TOTAL lab results with preceding specimen collection date
    # Use negative lookahead to prevent matching across specimen boundaries
    va_lab_pattern = r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})@(\d{1,2}:\d{2})(?:(?!Specimen Collection Date|={10,})[\s\S])*?PSA\s+TOTAL\s+(\d+\.?\d*)\s+n[gG]/mL'
    for match in re.finditer(va_lab_pattern, note_content, re.IGNORECASE):
        date = match.group(1).strip()
        time = match.group(2).strip()
        value = match.group(3).strip()
        psa_entries.append(f"{date} {time}: {value}")

    # Pattern 3: Narrative mentions
    # "PSA was 4.2 on 01/15/2024"
    if not psa_entries:
        narrative_pattern = r'PSA\s+(?:was|is|of|=|:)?\s*(\d+\.?\d*)\s+(?:on|dated)?\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})'
        for match in re.finditer(narrative_pattern, note_content, re.IGNORECASE):
            value = match.group(1).strip()
            date = match.group(2).strip()
            psa_entries.append(f"{date}: {value}")

    if not psa_entries:
        return ""

    return '\n'.join(psa_entries)
