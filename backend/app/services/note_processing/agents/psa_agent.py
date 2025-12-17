"""
PSA Curve Agent

Combines PSA values from all notes into a cohesive curve.
Uses deterministic parsing to ensure ALL PSA values are preserved.
"""

from typing import List, Dict, Set, Tuple
from datetime import datetime
import re


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

    if len(all_psa) == 1:
        return all_psa[0]

    # Parse all PSA entries deterministically
    psa_entries = _parse_all_psa_entries(all_psa)

    # Remove duplicates (same date/time/value)
    unique_entries = _remove_duplicates(psa_entries)

    # Sort by date (reverse chronological - most recent first)
    sorted_entries = _sort_by_date(unique_entries)

    # Format as PSA curve
    return _format_psa_curve(sorted_entries)


def _parse_all_psa_entries(psa_sections: List[str]) -> List[Tuple[datetime, float, str]]:
    """
    Parse all PSA entries from multiple sections.

    Returns:
        List of tuples: (datetime, psa_value, original_time_string)
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


def _parse_psa_line(line: str) -> Tuple[datetime, float, str]:
    """
    Parse a single PSA line into (datetime, value, time_string).

    Supports formats:
    - [r] MMM DD, YYYY HH:MM    PSA_VALUE
    - MMM DD, YYYY HH:MM    PSA_VALUE
    - MMM DD, YYYY HH:MM: VALUE (from extractor - with colon separator)
    - MM/DD/YYYY  PSA TOTAL  VALUE  ng/mL
    """
    # Remove [r] prefix if present
    line = re.sub(r'^\[r\]\s*', '', line.strip())

    # Pattern 1: MMM DD, YYYY HH:MM: VALUE (extractor format with colon)
    pattern1 = r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+(\d{1,2}:\d{2}):\s*(\d+\.?\d*)'
    match = re.search(pattern1, line)
    if match:
        date_str = match.group(1)
        time_str = match.group(2)
        value = float(match.group(3))

        # Parse datetime
        dt = datetime.strptime(f"{date_str} {time_str}", "%b %d, %Y %H:%M")
        return (dt, value, time_str)

    # Pattern 2: MMM DD, YYYY HH:MM    VALUE (spaces, no colon)
    pattern2 = r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+(\d{1,2}:\d{2})\s+(\d+\.?\d*)'
    match = re.search(pattern2, line)
    if match:
        date_str = match.group(1)
        time_str = match.group(2)
        value = float(match.group(3))

        # Parse datetime
        dt = datetime.strptime(f"{date_str} {time_str}", "%b %d, %Y %H:%M")
        return (dt, value, time_str)

    # Pattern 3: MMM DD, YYYY: VALUE (date only with colon)
    pattern3 = r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4}):\s*(\d+\.?\d*)'
    match = re.search(pattern3, line)
    if match:
        date_str = match.group(1)
        value = float(match.group(2))

        # Parse datetime (default to midnight)
        dt = datetime.strptime(date_str, "%b %d, %Y")
        return (dt, value, "00:00")

    # Pattern 4: MMM DD, YYYY    VALUE (date only, no colon)
    pattern4 = r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+(\d+\.?\d*)'
    match = re.search(pattern4, line)
    if match:
        date_str = match.group(1)
        value = float(match.group(2))

        # Parse datetime (default to midnight)
        dt = datetime.strptime(date_str, "%b %d, %Y")
        return (dt, value, "00:00")

    # Pattern 5: MM/DD/YYYY  PSA TOTAL  VALUE  ng/mL
    pattern5 = r'(\d{1,2}/\d{1,2}/\d{4})\s+(?:PSA\s+TOTAL|PSA)\s+(\d+\.?\d*)'
    match = re.search(pattern5, line)
    if match:
        date_str = match.group(1)
        value = float(match.group(2))

        # Parse datetime
        dt = datetime.strptime(date_str, "%m/%d/%Y")
        return (dt, value, "00:00")

    return None


def _remove_duplicates(entries: List[Tuple[datetime, float, str]]) -> List[Tuple[datetime, float, str]]:
    """
    Remove duplicate PSA entries (same date/time).

    If multiple entries exist for same datetime, keep the first one encountered.
    """
    seen: Set[datetime] = set()
    unique = []

    for dt, value, time_str in entries:
        if dt not in seen:
            seen.add(dt)
            unique.append((dt, value, time_str))

    return unique


def _sort_by_date(entries: List[Tuple[datetime, float, str]]) -> List[Tuple[datetime, float, str]]:
    """
    Sort PSA entries by date in reverse chronological order (most recent first).
    """
    return sorted(entries, key=lambda x: x[0], reverse=True)


def _format_psa_curve(entries: List[Tuple[datetime, float, str]]) -> str:
    """
    Format PSA entries into the standard curve format.

    Format: [r] MMM DD, YYYY HH:MM    PSA_VALUE[H if >4.0]
    """
    lines = []

    for dt, value, time_str in entries:
        # Format date
        date_str = dt.strftime("%b %d, %Y")

        # Add H marker if PSA > 4.0
        value_str = str(value)
        if value > 4.0:
            value_str += "H"

        # Format line
        if time_str and time_str != "00:00":
            line = f"[r] {date_str} {time_str}    {value_str}"
        else:
            line = f"[r] {date_str}    {value_str}"

        lines.append(line)

    return '\n'.join(lines)
