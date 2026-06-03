"""
PSA (Prostate-Specific Antigen) Curve Extractor

Extracts PSA values and dates from clinical notes.
"""

import re


# Plausible PSA Total value range (ng/mL). Anything outside this band
# is almost certainly a parsing error — picking up Free PSA, % Free
# PSA, glucose, alkaline phosphatase, or some other lab that
# accidentally landed near a date in the document.
_PSA_MIN_NG_PER_ML = 0.001  # below detection in modern assays
_PSA_MAX_NG_PER_ML = 2000.0  # advanced metastatic; >2000 is essentially always parser error

# Tokens on the same line as a candidate value that indicate the
# value is NOT PSA Total (Free PSA, % Free, density, ratio, etc.).
_NON_PSA_TOTAL_MARKERS = (
    "free", "%", "ratio", "density", "doubling", "velocity",
    "volume", "free/total", "f/t",
)


def _is_plausible_psa_value(value_str: str) -> bool:
    """Numeric range guard: reject values that cannot be PSA Total."""
    try:
        v = float(value_str.lstrip("<"))
    except ValueError:
        return False
    if not (_PSA_MIN_NG_PER_ML <= v <= _PSA_MAX_NG_PER_ML):
        return False
    # Defense in depth: VA often writes timestamps as bare 4-digit
    # integers (1243 = 12:43). If the value has no decimal point AND
    # is in [600, 2400] AND parses as a valid 24-h HH:MM, it is far
    # more likely a time than a PSA. Real PSA Total values in this
    # numeric range almost always have a decimal (e.g. 12.5, 247.0).
    raw = value_str.lstrip("<").strip()
    if "." not in raw and raw.isdigit() and 3 <= len(raw) <= 4:
        try:
            n = int(raw)
            # 0000-2359 are valid 24-hour times. PSA values rarely fall
            # in this range as integers without a decimal point.
            hh = n // 100
            mm = n % 100
            if 0 <= hh <= 23 and 0 <= mm <= 59 and n >= 600:
                # Looks like a time-shaped value. Reject.
                return False
        except ValueError:
            pass
    return True


def _line_is_non_psa_total(line_text: str) -> bool:
    """True if the line text indicates a non-Total PSA component."""
    lower = line_text.lower()
    if "psa" not in lower and "prostate" not in lower:
        # Could be a non-PSA lab — let other heuristics decide
        return False
    return any(marker in lower for marker in _NON_PSA_TOTAL_MARKERS)


def _is_multi_column_row(text_after_match: str) -> bool:
    """
    Check if there are multiple additional numeric values after the matched value,
    indicating a multi-column lab table row (e.g., CHEM I PROFILE, URINE TESTS).

    PSA table rows have at most one value: "4.66 H"
    CHEM I rows have many: "108 H   30 H  1.5 H         140    3.9    106"

    Returns True if the line has >1 additional numeric values (multi-column table).
    """
    if not text_after_match:
        return False
    # Get the rest of the current line only
    line_remainder = text_after_match.split('\n')[0]
    # Count additional numeric values (integers or decimals) on the same line
    additional_values = re.findall(r'\d+\.?\d*', line_remainder)
    return len(additional_values) > 1


def extract_psa(note_content: str) -> str:
    """
    Extract PSA curve data from a clinical note.

    PSA data can appear in various formats:
    - "PSA:" section with date/value pairs
    - "PSA Curve:" section
    - "PSA trends:" section
    - Tabular format with dates and values
    - Narrative format: "PSA was 4.2 on 01/15/2024"

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted PSA data, or "" if not found
    """
    psa_entries = []

    # Normalize: ensure content ends with newline for consistent pattern matching.
    # Without this, Pattern 1's content capture ((?:.*\n)*?) fails when the PSA
    # section is at EOF with no trailing newline, because .*\n requires a newline.
    if note_content and not note_content.endswith('\n'):
        note_content += '\n'

    # Pattern 1: Look for "PSA:" or "PSA Curve:" or "PSA trends:" section
    #
    # CRITICAL FIX: Previous pattern used \n{2,} as blank-line boundary, which fails
    # on VA notes where "blank" lines contain whitespace (spaces/tabs). This caused
    # the section to capture 158KB+ of the document, including CHEM I PROFILE,
    # URINE TESTS, and other lab tables. Non-PSA values (Glucose, Creatinine, etc.)
    # were then extracted as PSA values.
    #
    # Fixes applied:
    # 1. Require PSA header at/near start of line (prevents "Messages for PSA:" match)
    # 2. Allow one optional blank line after header (for "PSA trends:" format)
    # 3. Use \n\s*\n for blank-line boundary (handles whitespace-only blank lines)
    # 4. Add separator lines (===, ---) and STANDARD TITLE as boundaries
    # 5. Cap section size at 5000 chars as safety net
    # 6. Use finditer to capture ALL PSA sections, not just the first
    section_pattern = (
        r'(?:^|\n)\s*'  # Start of string/line, optional indent
        r'(?:PSA(?:\s+(?:Curve|trends?))?|Prostate-Specific Antigen):\s*\n'  # Header
        r'(?:\s*\n)?'  # Allow one optional blank line after header
        r'((?:.*\n)*?)'  # Non-greedy content capture
        r'(?='  # Lookahead for section boundary
        r'\n\s*\n'  # Blank line (handles whitespace-only lines)
        r'|\n\s*(?:MEDICATIONS|ALLERGIES|PATHOLOGY|Testosterone|Imaging|PHYSICAL'
        r'|ASSESSMENT|ROS|Physical Exam|Plan|STANDARD TITLE):'  # Section headers
        r'|\n\s*={5,}'  # Separator: =====...
        r'|\n\s*-{5,}'  # Separator: -----...
        r'|$'  # End of string
        r')'
    )

    # Date/value pattern for PSA entries within a section.
    # Accepts [r], [c] prefixes or no bracket prefix.
    #
    # CRITICAL FIX (2026-05-08): VA notes commonly write the time as a
    # bare 4-digit number followed by a comma:
    #   "[r] May 01, 2025 1243, 2.83"
    # The previous pattern's `(?:(\d{4}|\d{1,2}:\d{2})\s+)?` required
    # whitespace AFTER the time, so when separated by `, ` instead of
    # ` `, the time group failed and "1243" was captured as the PSA
    # value (1243.0 ng/mL — a phantom "very high PSA"). Allowing
    # `[,\s]+` after the time fixes the parse.
    date_value_pattern = (
        r'(?:\[r\]|\[c\])?\s*'                       # [r]/[c] prefix or none
        r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})'          # Date: MMM DD, YYYY
        r'[\s@]+'                                    # date/time separator
        r'(?:(\d{4}|\d{1,2}:\d{2})[,\s]+)?'           # Optional time (HHMM or HH:MM), allow ',' after
        r'(<?\d+\.?\d*)'                             # PSA value (optional < prefix)
        r'(?:\s*[LHlh])?'                            # Optional L/H flag
    )

    for section_match in re.finditer(section_pattern, note_content, re.IGNORECASE | re.MULTILINE):
        psa_section = section_match.group(1).strip()

        # Safety: reject over-large sections as false positives
        # A PSA section with 50+ entries would be ~3000 chars max
        if len(psa_section) > 5000:
            continue

        for m in re.finditer(date_value_pattern, psa_section, re.IGNORECASE):
            date = m.group(1).strip()
            time = m.group(2).strip() if m.group(2) else None
            value = m.group(3).strip()

            # Reject multi-column table rows (CHEM I, URINE TESTS, CBC, etc.)
            # PSA rows have a single value; lab table rows have multiple values
            rest_of_section = psa_section[m.end():]
            if _is_multi_column_row(rest_of_section):
                continue

            # NEW (2026-05-08): reject impossible PSA values. Real-world
            # PSA Total ranges from <0.01 to ~2000 ng/mL. Outside that
            # band the value is almost certainly a different lab that
            # got matched by accident (Free PSA, %Free, glucose, etc).
            if not _is_plausible_psa_value(value):
                continue

            # NEW: also reject if the line containing the match is
            # explicitly a non-Total PSA component (Free PSA, % Free,
            # density, velocity). The user reported "alternating high
            # and low" PSA values which is the classic signature of
            # Free + Total getting concatenated as separate entries.
            line_start = psa_section.rfind('\n', 0, m.start()) + 1
            line_end = psa_section.find('\n', m.end())
            if line_end == -1:
                line_end = len(psa_section)
            line_text = psa_section[line_start:line_end]
            if _line_is_non_psa_total(line_text):
                continue

            # Include time if present
            if time:
                # Convert 4-digit format (0858) to HH:MM (08:58)
                if len(time) == 4 and ':' not in time:
                    time = f"{time[:2]}:{time[2:]}"
                psa_entries.append(f"{date} {time}: {value}")
            else:
                psa_entries.append(f"{date}: {value}")

    # Pattern 2: VA Lab Result Format - Structured lab report blocks
    # Each lab block has:
    #   Specimen Collection Date: Oct 28, 2025@10:49
    #   (header lines, eval lines)
    #   PSA TOTAL                      5.66 H   ng/mL
    #
    # Strategy: Find all lab blocks that contain PSA TOTAL
    # Use a more permissive pattern that allows up to 500 chars between date and PSA TOTAL

    # Pattern 2a: Standard VA lab block - allows more content between date and PSA
    # Handles both regular values (5.66) and less-than values (<0.01)
    va_lab_pattern = r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})@(\d{1,2}:\d{2})(?:(?!Specimen Collection Date).){0,500}?PSA\s+TOTAL\s+(<?\d+\.?\d*)\s*[LHlh]?\s*n[gG]/mL'
    for match in re.finditer(va_lab_pattern, note_content, re.IGNORECASE | re.DOTALL):
        date = match.group(1).strip()
        time = match.group(2).strip()
        value = match.group(3).strip()
        if not _is_plausible_psa_value(value):
            continue
        entry = f"{date} {time}: {value}"
        if entry not in psa_entries:
            psa_entries.append(entry)

    # Pattern 2b: Direct PSA TOTAL line extraction with date context
    # Look for PSA TOTAL lines and find the nearest preceding specimen date
    # Handles both regular values (5.66) and less-than values (<0.01 L)
    psa_line_pattern = r'PSA\s+TOTAL\s+(<?\d+\.?\d*)\s*[LHlh]?\s*n[gG]/mL'
    for psa_match in re.finditer(psa_line_pattern, note_content, re.IGNORECASE):
        psa_value = psa_match.group(1).strip()
        if not _is_plausible_psa_value(psa_value):
            continue

        # Look backwards for the nearest specimen collection date
        text_before = note_content[:psa_match.start()]
        date_pattern = r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})@(\d{1,2}:\d{2})'
        date_matches = list(re.finditer(date_pattern, text_before, re.IGNORECASE))
        if date_matches:
            last_date_match = date_matches[-1]
            date = last_date_match.group(1).strip()
            time = last_date_match.group(2).strip()
            entry = f"{date} {time}: {psa_value}"
            if entry not in psa_entries:
                psa_entries.append(entry)

    # Pattern 2c: Inline lab result format from letters/summaries
    # PSA TOTAL     5.66 H            ng/mL          0.2 - 4.0
    # PSA TOTAL     <0.01 L           ng/mL          0.2 - 4.0
    inline_psa_pattern = r'PSA\s+TOTAL\s+(<?\d+\.?\d*)\s*[LHlh]?\s+ng/mL'
    for match in re.finditer(inline_psa_pattern, note_content, re.IGNORECASE):
        psa_value = match.group(1).strip()
        if not _is_plausible_psa_value(psa_value):
            continue

        # Find date context from surrounding text (look for "your MMM DD YYYY test results")
        context_start = max(0, match.start() - 500)
        context = note_content[context_start:match.start()]

        # Try to find date in format "your Oct 28 2025 test results"
        date_in_context = re.search(r'your\s+([A-Za-z]{3}\s+\d{1,2}\s+\d{4})\s+test', context, re.IGNORECASE)
        if date_in_context:
            date = date_in_context.group(1).strip()
            entry = f"{date}: {psa_value}"
            if entry not in psa_entries:
                psa_entries.append(entry)

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

    # Deduplicate PSA entries by date + value (ignore time differences)
    # e.g., "Jun 17, 2025 09:43: 2.09" and "Jun 17 2025: 2.09" are duplicates
    unique_entries = []
    seen_date_values = set()

    for entry in psa_entries:
        # Extract just the date (MMM DD YYYY or MMM DD, YYYY) and value
        # Remove time component for comparison
        normalized = re.sub(r'\s+\d{1,2}:\d{2}', '', entry)  # Remove HH:MM time
        normalized = re.sub(r',\s*', ' ', normalized)  # Normalize comma in date
        normalized = re.sub(r'\s+', ' ', normalized).strip()  # Collapse whitespace

        if normalized not in seen_date_values:
            seen_date_values.add(normalized)
            unique_entries.append(entry)

    # Sort entries by date (most recent first). The PSA curve is much
    # easier to read when chronological. The user reported values
    # "alternating high/low" — that signature is consistent with
    # entries appearing in input order rather than time order.
    def _entry_sort_key(entry: str):
        from datetime import datetime
        # Pull out the leading date "MMM DD, YYYY" or "MMM DD YYYY"
        m = re.match(r'^([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})', entry)
        if not m:
            return datetime.min
        for fmt in ('%b %d, %Y', '%b %d %Y', '%B %d, %Y', '%B %d %Y'):
            try:
                return datetime.strptime(m.group(1), fmt)
            except ValueError:
                continue
        return datetime.min

    unique_entries.sort(key=_entry_sort_key, reverse=True)

    return '\n'.join(unique_entries)
