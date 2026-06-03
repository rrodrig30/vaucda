"""
Past Surgical History (PSH) Extractor

Extracts PSH from clinical notes.
Enhanced to also find surgeries mentioned in HPI/narrative text.
"""

import re
from typing import List, Set


def extract_psh(note_content: str) -> str:
    """
    Extract Past Surgical History from a clinical note.

    The PSH typically appears after "PSH:" or "Past Surgical History:" markers.
    Also extracts surgeries mentioned in HPI text (e.g., "s/p nephrectomy").

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted PSH text, or "" if not found
    """
    all_surgeries: Set[str] = set()

    # ======================================================================
    # PHASE 1: Extract from formal PSH section
    # ======================================================================

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

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove leading numbers and periods
            clean_line = re.sub(r'^\d+\.\s*', '', line)
            if clean_line:
                all_surgeries.add(clean_line)

    # ======================================================================
    # PHASE 2: Extract surgeries from HPI/narrative text
    # Look for "s/p [procedure]", "[procedure] completed [date]", etc.
    # ======================================================================

    narrative_surgeries = extract_narrative_surgeries(note_content)
    all_surgeries.update(narrative_surgeries)

    # Return raw surgeries (agent will number them)
    if all_surgeries:
        return '\n'.join(sorted(all_surgeries))
    return ""


def extract_narrative_surgeries(text: str) -> List[str]:
    """
    Extract surgeries mentioned in narrative/HPI text.

    Finds patterns like:
    - "s/p [procedure] on [date]"
    - "[procedure] completed [date]"
    - "underwent [procedure]"
    - "history of [procedure]"

    Args:
        text: Clinical note text

    Returns:
        List of surgery strings with dates where available
    """
    surgeries = []

    # Common urologic and surgical procedures to look for
    procedure_patterns = [
        # Kidney surgeries
        r'(?:left|right|bilateral)?\s*(?:partial|radical)?\s*(?:robotic|laparoscopic|open)?\s*nephrectomy',
        r'heminephrectomy',
        r'renal\s+(?:mass\s+)?(?:resection|ablation)',

        # Prostate surgeries
        r'(?:radical|simple)?\s*prostatectomy',
        r'TURP',
        r'transurethral\s+resection\s+of\s+(?:the\s+)?prostate',
        r'prostate\s+(?:biopsy|resection)',
        r'TULP',
        r'HoLEP',
        r'GreenLight\s+(?:laser)?(?:\s+therapy)?',

        # Bladder surgeries
        r'(?:radical|partial)?\s*cystectomy',
        r'TURBT',
        r'transurethral\s+resection\s+of\s+bladder\s+tumor',
        r'bladder\s+(?:resection|biopsy)',
        r'ileal\s+conduit',
        r'neobladder',

        # Other GU surgeries
        r'orchiectomy',
        r'hydrocelectomy',
        r'varicocelectomy',
        r'vasectomy',
        r'circumcision',
        r'urethroplasty',
        r'ureteroscopy',
        r'lithotripsy',
        r'ESWL',
        r'PCNL',
        r'percutaneous\s+nephrolithotomy',

        # General surgeries (relevant to urology)
        r'appendectomy',
        r'cholecystectomy',
        r'hernia\s+repair',
        r'inguinal\s+hernia',
        r'colectomy',
        r'bowel\s+resection',
    ]

    # Build combined pattern
    procedure_group = '(' + '|'.join(procedure_patterns) + ')'

    # Pattern 1: "s/p [procedure] on [date]" or "s/p [procedure] ([date])"
    sp_pattern = re.compile(
        r's/p\s+' + procedure_group + r'(?:\s+(?:on|dated?)?\s*)?(?:\(?(\d{1,2}/\d{1,2}/\d{2,4})\)?)?',
        re.IGNORECASE
    )
    for match in sp_pattern.finditer(text):
        procedure = match.group(1).strip()
        date = match.group(2) if match.lastindex >= 2 else None
        surgery_str = _format_surgery(procedure, date)
        if surgery_str and surgery_str not in surgeries:
            surgeries.append(surgery_str)

    # Pattern 2: "[procedure] completed [date]" or "[procedure] performed [date]"
    completed_pattern = re.compile(
        procedure_group + r'\s+(?:completed|performed|done)\s+(?:on\s+)?(\d{1,2}/\d{1,2}/\d{2,4})',
        re.IGNORECASE
    )
    for match in completed_pattern.finditer(text):
        procedure = match.group(1).strip()
        date = match.group(2)
        surgery_str = _format_surgery(procedure, date)
        if surgery_str and surgery_str not in surgeries:
            surgeries.append(surgery_str)

    # Pattern 3: "This was completed [date]" following a procedure mention
    # Look for procedure in preceding context
    this_completed_pattern = re.compile(
        r'(' + procedure_group + r')[^.]*?\.\s*This\s+was\s+completed\s+(\d{1,2}/\d{1,2}/\d{2,4})',
        re.IGNORECASE | re.DOTALL
    )
    for match in this_completed_pattern.finditer(text):
        procedure = match.group(1).strip()
        date = match.group(3) if match.lastindex >= 3 else None
        surgery_str = _format_surgery(procedure, date)
        if surgery_str and surgery_str not in surgeries:
            surgeries.append(surgery_str)

    # Pattern 4: "underwent [procedure]" or "had [procedure]"
    underwent_pattern = re.compile(
        r'(?:underwent|had\s+a?)\s+(?:a\s+)?' + procedure_group + r'(?:\s+(?:on|in)\s+(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}))?',
        re.IGNORECASE
    )
    for match in underwent_pattern.finditer(text):
        procedure = match.group(1).strip()
        date = match.group(2) if match.lastindex >= 2 else None
        surgery_str = _format_surgery(procedure, date)
        if surgery_str and surgery_str not in surgeries:
            surgeries.append(surgery_str)

    # Pattern 5: "is s/p [procedure] on [date]" - common in assessments
    is_sp_pattern = re.compile(
        r'is\s+s/p\s+' + procedure_group + r'(?:\s+(?:on|dated?)?\s*)?(?:\(?(\d{1,2}/\d{1,2}/\d{2,4})\)?)?',
        re.IGNORECASE
    )
    for match in is_sp_pattern.finditer(text):
        procedure = match.group(1).strip()
        date = match.group(2) if match.lastindex >= 2 else None
        surgery_str = _format_surgery(procedure, date)
        if surgery_str and surgery_str not in surgeries:
            surgeries.append(surgery_str)

    # Pattern 6: Look for "Pt opted for [procedure]... completed [date]" across sentences
    opted_pattern = re.compile(
        r'(?:opted\s+for|scheduled\s+for|underwent)\s+(?:a\s+)?' + procedure_group +
        r'[^.]*?(?:in\s+the\s+community|at\s+[A-Za-z]+|externally)?[^.]*?\.?\s*(?:This\s+was\s+)?completed\s+(\d{1,2}/\d{1,2}/\d{2,4})',
        re.IGNORECASE | re.DOTALL
    )
    for match in opted_pattern.finditer(text):
        procedure = match.group(1).strip()
        date = match.group(2)
        surgery_str = _format_surgery(procedure, date)
        if surgery_str and surgery_str not in surgeries:
            surgeries.append(surgery_str)

    return surgeries


def _format_surgery(procedure: str, date: str = None) -> str:
    """
    Format a surgery string with optional date.

    Args:
        procedure: Name of the surgical procedure
        date: Optional date string

    Returns:
        Formatted surgery string, e.g., "Left partial nephrectomy (7/8/2025)"
    """
    if not procedure:
        return ""

    # Clean up procedure name
    procedure = procedure.strip()
    # Capitalize first letter, keep rest as-is for acronyms
    if procedure and not procedure[0].isupper():
        procedure = procedure[0].upper() + procedure[1:]

    # Clean up duplicate spaces
    procedure = re.sub(r'\s+', ' ', procedure)

    if date:
        return f"{procedure} ({date})"
    return procedure
