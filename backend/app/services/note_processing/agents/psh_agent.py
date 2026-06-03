"""
PSH (Past Surgical History) Agent

Combines surgical histories from all notes, including VA surgical data.
Formats as a numbered list with surgery dates.
"""

from typing import List, Dict, Tuple
import re
from ..llm_helper import combine_sections_with_llm


def _parse_surgery_with_date(surgery_line: str) -> Tuple[str, str]:
    """
    Parse a surgery line to extract surgery name and date.

    Handles formats:
    - "Left partial nephrectomy (7/8/2025)"
    - "TURP on 3/15/2024"
    - "Appendectomy - 2020"
    - "Cholecystectomy, 01/2019"

    Returns:
        Tuple of (surgery_name, date_string) - date may be empty string
    """
    surgery_line = surgery_line.strip()

    # Pattern 1: Date in parentheses at end "(MM/DD/YYYY)" or "(MM/DD/YY)"
    match = re.match(r'^(.+?)\s*\((\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4}|\d{4})\)\s*$', surgery_line)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern 2: "on MM/DD/YYYY" or "on MM/DD/YY"
    match = re.match(r'^(.+?)\s+on\s+(\d{1,2}/\d{1,2}/\d{2,4})\s*$', surgery_line, re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern 3: Date at end with dash "- MM/DD/YYYY" or "- YYYY"
    match = re.match(r'^(.+?)\s*[-–]\s*(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4}|\d{4})\s*$', surgery_line)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern 4: Date at end with comma ", MM/DD/YYYY" or ", YYYY"
    match = re.match(r'^(.+?),\s*(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4}|\d{4})\s*$', surgery_line)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern 5: Just a date at end (MM/DD/YYYY format)
    match = re.match(r'^(.+?)\s+(\d{1,2}/\d{1,2}/\d{2,4})\s*$', surgery_line)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # No date found
    return surgery_line, ""


def _format_surgery_entry(surgery: str, date: str, number: int) -> str:
    """
    Format a surgery entry as a numbered line with date.

    Format: "N. Surgery Name (MM/DD/YYYY)"

    Args:
        surgery: Surgery name
        date: Date string (may be empty)
        number: Line number

    Returns:
        Formatted surgery line
    """
    surgery = surgery.strip()
    # Clean up surgery name - remove leading numbers/bullets if present
    surgery = re.sub(r'^[\d\.\-\*\)]+\s*', '', surgery)
    # Remove markdown formatting
    surgery = re.sub(r'\*\*([^*]+)\*\*', r'\1', surgery)
    # Capitalize first letter
    if surgery and not surgery[0].isupper():
        surgery = surgery[0].upper() + surgery[1:]

    if date:
        return f"{number}. {surgery} ({date})"
    else:
        return f"{number}. {surgery}"


def synthesize_psh(gu_notes: List[Dict[str, str]], non_gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize Past Surgical History from all notes.

    Per instructions: Combine PSH from all notes, including any surgery data
    from VA clinical documents.

    Output format: Numbered list with dates
    Example:
        1. Left partial nephrectomy (7/8/2025)
        2. TURP (3/15/2024)
        3. Appendectomy (2015)

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries

    Returns:
        Synthesized, enumerated PSH list with dates
    """
    # Collect all PSH entries
    all_psh = []

    for note in gu_notes:
        if note.get("PSH"):
            all_psh.append(note["PSH"])

    for note in non_gu_notes:
        if note.get("PSH"):
            all_psh.append(note["PSH"])

    if not all_psh:
        return ""

    # Parse all surgeries and their dates
    surgeries_with_dates = []  # List of (surgery_name, date_string)
    seen_surgeries = set()  # For deduplication (lowercase surgery name)

    for psh_block in all_psh:
        lines = psh_block.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip headers and section markers
            if any(header in line.upper() for header in ['PSH:', 'PAST SURGICAL HISTORY:', '===', '---']):
                continue

            # Parse surgery and date
            surgery_name, date_str = _parse_surgery_with_date(line)

            if surgery_name:
                # Normalize for deduplication
                normalized = surgery_name.lower().strip()
                # Remove common prefixes for comparison
                normalized = re.sub(r'^(s/p|status post|history of)\s+', '', normalized)

                if normalized not in seen_surgeries:
                    seen_surgeries.add(normalized)
                    surgeries_with_dates.append((surgery_name, date_str))

    # If we couldn't parse any surgeries locally, use LLM
    if not surgeries_with_dates and len(all_psh) > 1:
        instructions = """
Combine these surgical histories into a single, deduplicated list.
- Remove duplicate surgeries
- Preserve dates in format (MM/DD/YYYY) or (YYYY) at the end of each line
- Sort by date (most recent first) if dates are available
- Include ALL surgeries
- Format EACH surgery as: "Surgery Name (date)" - one per line
- If no date available, just list the surgery name

CRITICAL: Provide ONLY the surgical history list. NO meta-commentary, NO explanations, NO preamble.
Format example:
Left partial nephrectomy (7/8/2025)
TURP (3/15/2024)
Appendectomy (2015)
"""

        synthesized_psh = combine_sections_with_llm(
            section_name="Past Surgical History",
            section_instances=all_psh,
            instructions=instructions
        )

        if synthesized_psh:
            # Clean up LLM meta-commentary
            synthesized_psh = re.sub(r'^(Here is|Here are|I have combined|Note:).*?\n', '', synthesized_psh, flags=re.MULTILINE | re.IGNORECASE)
            synthesized_psh = re.sub(r'\n(Note:|I removed|Since there).*$', '', synthesized_psh, flags=re.DOTALL | re.IGNORECASE)

            # Re-parse the LLM output
            for line in synthesized_psh.split('\n'):
                line = line.strip()
                if line:
                    surgery_name, date_str = _parse_surgery_with_date(line)
                    if surgery_name:
                        normalized = surgery_name.lower().strip()
                        normalized = re.sub(r'^(s/p|status post|history of)\s+', '', normalized)
                        if normalized not in seen_surgeries:
                            seen_surgeries.add(normalized)
                            surgeries_with_dates.append((surgery_name, date_str))

    # Sort by date (most recent first)
    def sort_key(item):
        surgery, date = item
        if not date:
            return (0, "")  # No date = sort to end

        # Try to parse various date formats
        import re
        # MM/DD/YYYY
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date)
        if match:
            month, day, year = match.groups()
            return (1, f"{year}{int(month):02d}{int(day):02d}")

        # MM/DD/YY
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2})', date)
        if match:
            month, day, year = match.groups()
            full_year = f"20{year}" if int(year) < 50 else f"19{year}"
            return (1, f"{full_year}{int(month):02d}{int(day):02d}")

        # MM/YYYY
        match = re.match(r'(\d{1,2})/(\d{4})', date)
        if match:
            month, year = match.groups()
            return (1, f"{year}{int(month):02d}00")

        # YYYY only
        match = re.match(r'(\d{4})', date)
        if match:
            return (1, f"{match.group(1)}0000")

        return (0, date)

    surgeries_with_dates.sort(key=sort_key, reverse=True)

    # Format as numbered list
    formatted_lines = []
    for i, (surgery, date) in enumerate(surgeries_with_dates, 1):
        formatted_lines.append(_format_surgery_entry(surgery, date, i))

    return '\n'.join(formatted_lines)
