"""
PSA Curve Agent

Combines PSA values from all notes into a cohesive curve.
Uses deterministic parsing to ensure ALL PSA values are preserved.
"""

from typing import List, Dict, Set, Tuple, Optional
from datetime import datetime
import re
import logging

logger = logging.getLogger(__name__)

# Common OCR/typo corrections for month abbreviations
MONTH_CORRECTIONS = {
    'Noc': 'Nov', 'NOC': 'Nov',  # Common OCR error
    'Jab': 'Jan', 'JAB': 'Jan',
    'Fab': 'Feb', 'FAB': 'Feb',
    'Nar': 'Mar', 'NAR': 'Mar',
    'Aor': 'Apr', 'AOR': 'Apr',
    'Nay': 'May', 'NAY': 'May',
    'Jun': 'Jun', 'JUN': 'Jun',
    'Jul': 'Jul', 'JUL': 'Jul',
    'Aub': 'Aug', 'AUB': 'Aug',
    'Sep': 'Sep', 'SEP': 'Sep',
    'Oct': 'Oct', 'OCT': 'Oct',
    'Nov': 'Nov', 'NOV': 'Nov',
    'Dec': 'Dec', 'DEC': 'Dec',
}


def _correct_month_typo(date_str: str) -> str:
    """Correct common OCR/typo errors in month abbreviations."""
    for typo, correct in MONTH_CORRECTIONS.items():
        if date_str.startswith(typo):
            return correct + date_str[3:]
    return date_str


def _safe_parse_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """Safely parse datetime with error handling for typos."""
    # Try to correct month typo
    corrected_date = _correct_month_typo(date_str)

    try:
        return datetime.strptime(f"{corrected_date} {time_str}", "%b %d, %Y %H:%M")
    except ValueError:
        # Log the issue but don't crash
        logger.warning(f"Could not parse PSA date: '{date_str} {time_str}'")
        return None


def synthesize_psa(gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize PSA curve from GU notes using deterministic merging.

    This function uses Python code (not LLM) to ensure ALL PSA values
    are preserved without truncation.

    Args:
        gu_notes: List of GU note dictionaries

    Returns:
        Combined PSA curve in reverse chronological order
    """
    all_psa = []

    for note in gu_notes:
        if note.get("PSA"):
            all_psa.append(note["PSA"])

    if not all_psa:
        return ""

    # Always parse and re-format ALL PSA entries through the formatter
    # This ensures consistent [r] prefix, H suffix for >4.0, and proper time format
    # even when there is only a single PSA section
    psa_entries = _parse_all_psa_entries(all_psa)

    if not psa_entries:
        # If parsing failed, return raw text as fallback
        return all_psa[0] if len(all_psa) == 1 else '\n'.join(all_psa)

    # Remove duplicates (same date/time/value)
    unique_entries = _remove_duplicates(psa_entries)

    # Sort by date (reverse chronological - most recent first)
    sorted_entries = _sort_by_date(unique_entries)

    # Format as PSA curve
    return _format_psa_curve(sorted_entries)


def _parse_all_psa_entries(psa_sections: List[str]) -> List[Tuple[datetime, float, str, bool]]:
    """
    Parse all PSA entries from multiple sections.

    Returns:
        List of tuples: (datetime, psa_value, original_time_string, is_less_than)
    """
    entries = []

    for section in psa_sections:
        lines = section.strip().split('\n')

        for line in lines:
            # Skip empty lines and section headers
            if not line.strip() or 'PSA CURVE' in line.upper():
                continue

            # Try to parse PSA entry
            entry = _parse_psa_line(line)
            if entry:
                entries.append(entry)

    return entries


def _parse_psa_line(line: str) -> Optional[Tuple[datetime, float, str, bool]]:
    """
    Parse a single PSA line into (datetime, value, time_string, is_less_than).

    Supports formats:
    - [r] MMM DD, YYYY HH:MM    PSA_VALUE
    - [r] MMM DD, YYYY HH:MM    <0.01 L (less-than values)
    - MMM DD, YYYY HH:MM    PSA_VALUE
    - MMM DD, YYYY HH:MM: VALUE (from extractor - with colon separator)
    - MM/DD/YYYY  PSA TOTAL  VALUE  ng/mL

    Returns:
        Tuple of (datetime, float_value, time_string, is_less_than_flag)
        or None if parsing fails
    """
    # Remove [r] prefix if present
    line = re.sub(r'^\[r\]\s*', '', line.strip())

    def _parse_value(value_str: str) -> Tuple[float, bool]:
        """Parse PSA value string, handling < prefix."""
        value_str = value_str.strip()
        is_less_than = value_str.startswith('<')
        numeric_str = value_str.lstrip('<')
        try:
            return float(numeric_str), is_less_than
        except ValueError:
            return 0.0, False

    # Pattern 1: MMM DD, YYYY HH:MM: VALUE (extractor format with colon)
    # Now handles <0.01 values with optional L/H suffix
    pattern1 = r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+(\d{1,2}:\d{2}):\s*(<?\d+\.?\d*)\s*[LHlh]?'
    match = re.search(pattern1, line)
    if match:
        date_str = match.group(1)
        time_str = match.group(2)
        value, is_less_than = _parse_value(match.group(3))

        # Parse datetime safely
        dt = _safe_parse_datetime(date_str, time_str)
        if dt:
            return (dt, value, time_str, is_less_than)

    # Pattern 2: MMM DD, YYYY HH:MM    VALUE (spaces, no colon)
    # Now handles <0.01 values with optional L/H suffix
    pattern2 = r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+(\d{1,2}:\d{2})\s+(<?\d+\.?\d*)\s*[LHlh]?'
    match = re.search(pattern2, line)
    if match:
        date_str = match.group(1)
        time_str = match.group(2)
        value, is_less_than = _parse_value(match.group(3))

        # Parse datetime safely
        dt = _safe_parse_datetime(date_str, time_str)
        if dt:
            return (dt, value, time_str, is_less_than)

    # Pattern 3: MMM DD, YYYY: VALUE (date only with colon)
    pattern3 = r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4}):\s*(<?\d+\.?\d*)\s*[LHlh]?'
    match = re.search(pattern3, line)
    if match:
        date_str = match.group(1)
        value, is_less_than = _parse_value(match.group(2))

        # Parse datetime (default to midnight) - with typo correction
        corrected_date = _correct_month_typo(date_str)
        try:
            dt = datetime.strptime(corrected_date, "%b %d, %Y")
            return (dt, value, "00:00", is_less_than)
        except ValueError:
            logger.warning(f"Could not parse PSA date: '{date_str}'")

    # Pattern 4: MMM DD, YYYY    VALUE (date only, no colon)
    pattern4 = r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+(<?\d+\.?\d*)\s*[LHlh]?'
    match = re.search(pattern4, line)
    if match:
        date_str = match.group(1)
        value, is_less_than = _parse_value(match.group(2))

        # Parse datetime (default to midnight) - with typo correction
        corrected_date = _correct_month_typo(date_str)
        try:
            dt = datetime.strptime(corrected_date, "%b %d, %Y")
            return (dt, value, "00:00", is_less_than)
        except ValueError:
            logger.warning(f"Could not parse PSA date: '{date_str}'")

    # Pattern 5: MM/DD/YYYY  PSA TOTAL  VALUE  ng/mL
    pattern5 = r'(\d{1,2}/\d{1,2}/\d{4})\s+(?:PSA\s+TOTAL|PSA)\s+(<?\d+\.?\d*)\s*[LHlh]?'
    match = re.search(pattern5, line)
    if match:
        date_str = match.group(1)
        value, is_less_than = _parse_value(match.group(2))

        # Parse datetime
        try:
            dt = datetime.strptime(date_str, "%m/%d/%Y")
            return (dt, value, "00:00", is_less_than)
        except ValueError:
            logger.warning(f"Could not parse PSA date: '{date_str}'")

    return None


def _remove_duplicates(entries: List[Tuple[datetime, float, str, bool]]) -> List[Tuple[datetime, float, str, bool]]:
    """
    Remove duplicate PSA entries (same date/time).

    If multiple entries exist for same datetime, keep the first one encountered.
    """
    seen: Set[datetime] = set()
    unique = []

    for dt, value, time_str, is_less_than in entries:
        if dt not in seen:
            seen.add(dt)
            unique.append((dt, value, time_str, is_less_than))

    return unique


def _sort_by_date(entries: List[Tuple[datetime, float, str, bool]]) -> List[Tuple[datetime, float, str, bool]]:
    """
    Sort PSA entries by date in reverse chronological order (most recent first).
    """
    return sorted(entries, key=lambda x: x[0], reverse=True)


def _format_psa_curve(entries: List[Tuple[datetime, float, str, bool]]) -> str:
    """
    Format PSA entries into the standard curve format.

    Format: [r] MMM DD, YYYY HH:MM    PSA_VALUE[H if >4.0 or L if <4.0]
    For undetectable PSA: [r] MMM DD, YYYY HH:MM    <0.01 L
    """
    lines = []

    for dt, value, time_str, is_less_than in entries:
        # Format date
        date_str = dt.strftime("%b %d, %Y")

        # Format value with appropriate prefix and suffix
        # PSA < 4.0 is normal (add L for low/normal)
        # PSA > 4.0 is elevated (add H for high)
        if is_less_than:
            # Undetectable PSA - format as <VALUE L
            value_str = f"<{value} L"
        elif value > 4.0:
            # Elevated PSA
            value_str = f"{value} H"
        else:
            # Normal PSA (no suffix needed, but some systems use L)
            value_str = str(value)

        # Format time as HH:MM (with colon) for consistent downstream parsing
        # CRITICAL: Downstream regex patterns in entity_extractor.py and
        # assessment_agent.py expect HH:MM format with colon. Without the colon,
        # 4-digit time like "0808" is captured as PSA value (808), producing
        # wildly incorrect calculator inputs.
        if time_str and time_str != "00:00":
            # Ensure colon is present in time string
            if ":" not in time_str and len(time_str) == 4:
                formatted_time = f"{time_str[:2]}:{time_str[2:]}"
            else:
                formatted_time = time_str
            line = f"[r] {date_str} {formatted_time}    {value_str}"
        else:
            line = f"[r] {date_str}         {value_str}"

        lines.append(line)

    return '\n'.join(lines)
