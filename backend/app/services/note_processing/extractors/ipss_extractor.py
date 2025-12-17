"""
IPSS (International Prostate Symptom Score) Extractor

Extracts IPSS scoring tables from clinical notes.
"""

import re


def extract_ipss(note_content: str) -> str:
    """
    Extract IPSS table from a clinical note.

    Per instructions: Extract from first "+" to last "+".
    IPSS tables are ASCII tables with borders made of "+" and "-" characters.

    Example:
    +------------------------+-------+-------+
    | Question               | Score | Date  |
    +------------------------+-------+-------+
    | Incomplete emptying    |   2   | 01/15 |
    +------------------------+-------+-------+

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted IPSS table text (including borders), or "" if not found
    """
    # Look for IPSS section header first
    # Common patterns: "IPSS:", "IPSS Score:", "AUA Symptom Score:", etc.
    ipss_section_match = re.search(
        r'(?:IPSS|AUA\s+Symptom\s+Score|International\s+Prostate\s+Symptom\s+Score)[:\s]*',
        note_content,
        re.IGNORECASE
    )

    if not ipss_section_match:
        # No IPSS section found
        return ""

    # Start searching from the IPSS header
    search_start = ipss_section_match.start()
    remaining_content = note_content[search_start:]

    # Find first "+" after IPSS header
    first_plus = remaining_content.find('+')
    if first_plus == -1:
        return ""

    # Find last "+" in what appears to be the table
    # Strategy: Look ahead from first "+" and find the last "+" that's part of a table row
    # (followed by "-" or other table characters on same line)

    # Extract a reasonable chunk (next 2000 chars should cover any IPSS table)
    table_chunk = remaining_content[first_plus:first_plus + 2000]

    # Find all lines that contain "+" characters (table borders)
    table_lines = []
    current_pos = 0

    for line in table_chunk.split('\n'):
        if '+' in line and ('-' in line or '|' in line):
            # This looks like a table line
            table_lines.append(line)
            current_pos += len(line) + 1  # +1 for newline
        elif table_lines and line.strip() and '|' in line:
            # Content row between borders
            table_lines.append(line)
            current_pos += len(line) + 1
        elif table_lines and not line.strip():
            # Empty line - might be end of table or just spacing
            # Check if next line is still table content
            continue
        elif table_lines:
            # Non-table line after we've started collecting table lines
            # This might be the end of the table
            break

    if not table_lines:
        return ""

    # Join the table lines
    ipss_table = '\n'.join(table_lines).strip()

    return ipss_table
