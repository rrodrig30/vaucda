"""
Past Surgical History (PSH) Extractor

Extracts PSH from clinical notes.
"""

import re


def extract_psh(note_content: str) -> str:
    """
    Extract Past Surgical History from a clinical note.

    The PSH typically appears after "PSH:" or "Past Surgical History:" markers.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted PSH text, or "" if not found
    """
    # Pattern: "PSH:" or "PSH" or "Past Surgical History:" followed by content
    # Until we hit a blank line followed by uppercase section header or next section
    # Format 1: PSH:\n procedure1\n procedure2
    # Format 2: PSH\n procedure1\n procedure2 (VA consult request format)

    # Try Format 1 first (with colon)
    pattern1 = r'(?:PSH|PAST SURGICAL HISTORY):\s*\n((?:.*\n)*?)(?=\n[A-Z\s]+(?:CURVE|RESULTS|HISTORY|:|$))'
    match = re.search(pattern1, note_content, re.IGNORECASE | re.MULTILINE)

    # Try Format 2 if Format 1 fails (no colon, indented lines)
    if not match:
        # Match PSH followed by indented lines (VA consult format)
        # Captures all indented lines, then post-process to remove non-PSH content
        pattern2 = r'PSH\s*\n((?:\s+[^\n]+\n)+)'
        match = re.search(pattern2, note_content, re.IGNORECASE | re.MULTILINE)

    if match:
        raw_psh = match.group(1)

        # Post-process: stop at MEDICATIONS, FAMILY HISTORY, or blank line
        lines = raw_psh.split('\n')
        psh_lines = []
        for line in lines:
            # Stop if we hit a section header or blank line
            if any(header in line.upper() for header in ['MEDICATIONS:', 'FAMILY HISTORY:', 'ALL NO KNOWN']):
                break
            if not line.strip():  # Blank line
                break
            if line.strip():
                psh_lines.append(line.strip())

        psh_text = '\n'.join(psh_lines)

        # Parse numbered list format
        # Example: "1. Surgery\n2. Another surgery"
        lines = psh_text.split('\n')
        surgeries = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove leading numbers and periods
            clean_line = re.sub(r'^\d+\.\s*', '', line)
            if clean_line:
                surgeries.append(clean_line)

        # Return raw surgeries (agent will number them)
        return '\n'.join(surgeries) if surgeries else psh_text

    return ""
