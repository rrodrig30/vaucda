"""
IPSS Agent

Combines IPSS scores into ASCII table format.
"""

from typing import List, Dict
import re
from ..llm_helper import combine_sections_with_llm


def add_placeholder_column_to_ipss(ipss_table: str) -> str:
    """
    Add a placeholder column with 'X' values to IPSS table data rows.

    This placeholder allows providers to fill in current visit data during the appointment.
    Only data rows (Empty, Frequency, etc.) get the X placeholder - header rows are left unchanged.
    """
    lines = ipss_table.split('\n')
    modified_lines = []

    for line in lines:
        if not line.strip():
            modified_lines.append(line)
            continue

        # Header separator line: +---------------+------+
        if re.match(r'^\+[-+]+\+$', line):
            # Add column separator for placeholder column
            modified_lines.append(line[:-1] + '------+')
        # Header rows (IPSS title and Symptom row)
        elif '| Symptom' in line or '|        IPSS' in line:
            # Fix malformed Symptom header row - ADD pipe separator before date if missing
            # Pattern: "| Symptom        9/22/25" should be "| Symptom       | 9/22/25"
            if '| Symptom' in line:
                # Check if pipe separator is missing between "Symptom" and date
                symptom_fix_match = re.match(r'^(\|\s*Symptom\s+)(\d{1,2}/\d{1,2}/\d{2,4})', line)
                if symptom_fix_match:
                    # Add the missing pipe separator
                    line = symptom_fix_match.group(1) + '| ' + symptom_fix_match.group(2)
            modified_lines.append(line)
        # Data rows (Empty, Frequency, Urgency, etc.) and Total/BI rows
        elif '|' in line and not re.match(r'^\+', line):
            # Add "X" placeholder for current visit data
            modified_lines.append(line[:-1] + '  X  |')
        else:
            modified_lines.append(line)

    return '\n'.join(modified_lines)


def synthesize_ipss(gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize IPSS scores from GU notes into ASCII table.

    Per instructions: Combine all IPSS results into ASCII table (max 45 chars wide).
    If too much data, create a second table.

    Args:
        gu_notes: List of GU note dictionaries

    Returns:
        Combined IPSS table(s) in ASCII format with placeholder column for current visit
    """
    all_ipss = []

    for note in gu_notes:
        if note.get("IPSS"):
            all_ipss.append(note["IPSS"])

    if not all_ipss:
        return ""

    if len(all_ipss) == 1:
        # Add placeholder column to single table
        return add_placeholder_column_to_ipss(all_ipss[0])

    instructions = """Combine these IPSS tables into ONE single ASCII table.
- Include all dates/columns from all tables in a single table
- Do NOT create multiple separate tables - combine everything into ONE table
- Preserve the ASCII table format with + and - characters
- Ensure alignment is maintained
- Use MM/DD/YY format with 2-digit year for dates (e.g., 9/22/25 for September 22, 2025, 12/15/25 for December 15, 2025)
- The table can be wide if needed to fit all columns

CRITICAL: Return ONLY ONE table with all data combined. Do NOT create duplicate or split tables."""

    result = combine_sections_with_llm("IPSS Table", all_ipss, instructions)

    # Remove LLM meta-commentary
    if result:
        # Remove notes and explanations
        result = re.sub(r'\n\n?Note:.*$', '', result, flags=re.DOTALL | re.IGNORECASE)
        result = re.sub(r'\n\n?Also,.*$', '', result, flags=re.DOTALL | re.IGNORECASE)
        result = re.sub(r'\n\n?Please.*$', '', result, flags=re.DOTALL | re.IGNORECASE)
        result = re.sub(r'\n\n?I have.*$', '', result, flags=re.DOTALL | re.IGNORECASE)
        result = result.strip()

    # Add placeholder column for current visit
    if result:
        result = add_placeholder_column_to_ipss(result)

    return result


def extract_ipss_at_visit(gu_notes: List[Dict[str, str]]) -> str:
    """
    Extract IPSS score from the most recent visit only.

    This provides a focused view of the current visit's IPSS for quick reference.

    Args:
        gu_notes: List of GU note dictionaries

    Returns:
        IPSS table for the most recent visit, or "" if not found
    """
    # Get the first (most recent) note's IPSS
    for note in gu_notes:
        if note.get("IPSS"):
            ipss_table = note["IPSS"]

            # Extract just the date column from the table for the most recent visit
            # The IPSS table has format:
            # +---------------+------+
            # | Symptom       | DATE |
            # +---------------+------+

            # Find the date in the header row
            date_match = re.search(r'\|\s*Symptom\s+\|\s*(\d{1,2}/\d{1,2})\s*\|', ipss_table)
            if date_match:
                visit_date = date_match.group(1)
                return ipss_table
            else:
                # Fallback: return the full table if we can't parse the date
                return ipss_table

    return ""
