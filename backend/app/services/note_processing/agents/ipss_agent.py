"""
IPSS Agent

Combines IPSS scores into ASCII table format.
"""

from typing import List, Dict
import re
from ..llm_helper import combine_sections_with_llm


def format_ipss_table(ipss_data: list, dates: list) -> str:
    """
    Format IPSS data into a clean ASCII table.

    Args:
        ipss_data: List of dicts with symptom scores per date
        dates: List of date strings for column headers

    Returns:
        Clean ASCII table string
    """
    symptoms = ['Empty', 'Frequency', 'Urgency', 'Hesitancy', 'Intermittency', 'Flow', 'Nocturia']

    # Build table with consistent column widths
    col_width = 8
    symptom_col_width = 13

    # Header separator
    header_sep = '+' + '-' * (symptom_col_width + 2)
    for _ in dates:
        header_sep += '+' + '-' * col_width
    header_sep += '+'

    # Symptom header row
    header_row = '| Symptom       '
    for date in dates:
        date_str = date[:col_width].center(col_width)
        header_row += '|' + date_str
    header_row += '|'

    lines = [header_sep, header_row, header_sep]

    # Data rows
    for symptom in symptoms:
        row = f'| {symptom:<13}'
        for i, date in enumerate(dates):
            if i < len(ipss_data) and symptom.lower() in str(ipss_data[i]).lower():
                # Extract value from data
                val = ipss_data[i].get(symptom.lower(), 'X')
                val_str = str(val).center(col_width)
            else:
                val_str = 'X'.center(col_width)
            row += '|' + val_str
        row += '|'
        lines.append(row)

    lines.append(header_sep)

    return '\n'.join(lines)


def clean_ipss_table(ipss_table: str) -> str:
    """
    Clean and normalize an IPSS table, fixing malformed formatting.

    Handles common issues:
    - Missing column separators (|) in header rows
    - Inconsistent column widths
    - Missing closing separators

    Args:
        ipss_table: Raw IPSS table string

    Returns:
        Cleaned IPSS table with proper formatting
    """
    # Parse the table to extract data, then rebuild with consistent formatting
    lines = ipss_table.strip().split('\n')

    # Standard IPSS symptoms in order
    SYMPTOMS = ['Empty', 'Frequency', 'Urgency', 'Hesitancy', 'Intermittency', 'Flow', 'Nocturia']
    TOTALS = ['Total', 'BI']

    # Extract data from the malformed table
    symptom_values = {}
    total_values = {}
    date_columns = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip separator lines
        if re.match(r'^[\+\-]+$', line):
            continue

        # Look for header row with "Symptom" - extract date columns
        # Handle malformed: "| Symptom       2/18/25" (missing |)
        # And proper: "| Symptom       | 2/18/25 |"
        if 'Symptom' in line:
            # Extract dates from the header line
            # Pattern for dates: MM/DD/YY or MM/DD or M/D/YY etc.
            dates = re.findall(r'\d{1,2}/\d{1,2}(?:/\d{2,4})?', line)
            if dates:
                date_columns = dates
            continue

        # Look for "IPSS" title row
        if re.match(r'^\|?\s*IPSS\s*\|?$', line):
            continue

        # Extract symptom rows
        # Handle: "| Empty         |  0   |" or "| Empty |  0 |"
        for symptom in SYMPTOMS:
            if symptom in line:
                # Extract the numeric value(s) after the symptom name
                # Pattern: symptom name followed by | and number
                match = re.search(rf'{symptom}\s*\|?\s*(\d+|X)\s*\|?', line, re.IGNORECASE)
                if match:
                    symptom_values[symptom] = match.group(1)
                else:
                    # Try extracting just the number after the symptom
                    match = re.search(rf'{symptom}\s+\|?\s*(\d+|X)', line, re.IGNORECASE)
                    if match:
                        symptom_values[symptom] = match.group(1)
                break

        # Extract Total and BI rows
        for total_name in TOTALS:
            if total_name in line and total_name not in total_values:
                # Pattern: "| Total | 5/35 |" or "| Total         | 5/35 |"
                match = re.search(rf'{total_name}\s*\|?\s*([\d/]+|X|N/A)\s*\|?', line, re.IGNORECASE)
                if match:
                    total_values[total_name] = match.group(1)
                break

    # If we couldn't extract meaningful data, try basic cleanup and return
    if not symptom_values and not total_values:
        return _basic_table_cleanup(ipss_table)

    # Build a properly formatted table
    return _build_formatted_ipss_table(symptom_values, total_values, date_columns)


def _basic_table_cleanup(ipss_table: str) -> str:
    """
    Basic cleanup for tables that couldn't be parsed.
    Fixes common formatting issues without full reconstruction.
    """
    lines = ipss_table.split('\n')
    cleaned_lines = []

    for line in lines:
        if not line.strip():
            continue

        # Remove duplicate X columns
        line = re.sub(r'\|\s*X\s*\|\s*X\s*\|', '|   X   |', line)

        # Fix malformed separator lines
        if re.match(r'^\+[-+]+$', line) and not line.endswith('+'):
            line = line + '+'

        # Fix header row missing column separator
        # Pattern: "| Symptom       2/18/25" -> "| Symptom       | 2/18/25 |"
        if 'Symptom' in line and not line.endswith('|'):
            date_match = re.search(r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s*$', line)
            if date_match:
                date = date_match.group(1)
                line = re.sub(rf'\s*{re.escape(date)}\s*$', f' | {date} |', line)

        # Ensure consistent column separators
        line = re.sub(r'\s{2,}\|', ' |', line)

        cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


def _calculate_table_width(symptom_col: int, value_col: int, num_date_cols: int) -> int:
    """
    Calculate total width of IPSS table.

    Width formula: 1 + (symptom_col + 2) + 1 + (value_col * num_cols) + num_cols
    Example: 1 + 15 + 1 + (8 * 3) + 3 = 44 chars for 3 date columns
    """
    return 1 + (symptom_col + 2) + 1 + (value_col * num_date_cols) + num_date_cols


def _max_dates_for_width(max_width: int, symptom_col: int, value_col: int) -> int:
    """
    Calculate maximum number of date columns that fit within max_width.

    Solving: 1 + (symptom_col + 2) + 1 + (value_col * n) + n <= max_width
    => n * (value_col + 1) <= max_width - (symptom_col + 4)
    => n <= (max_width - symptom_col - 4) / (value_col + 1)
    """
    available = max_width - symptom_col - 4
    return max(1, available // (value_col + 1))


def _parse_column_date_for_sort(date_str: str):
    """
    Convert an IPSS column-header date (e.g. '2/18/25', '02/18/2025', '2/18')
    into a sortable ``datetime``. Unparseable headers sort to the epoch so
    they end up at the left and are visually distinguishable as outliers.

    Python's ``%y`` pivots at 1969 per POSIX, which is correct for clinical
    dates (anything from a 2-digit year like '99' lands in 1999, '24' in
    2024). Year-less headers like '2/18' are pinned to the current year
    because most VA dumps that produce them refer to the active visit
    cycle; this is rare in practice.
    """
    from datetime import datetime
    s = (date_str or "").strip()
    if not s:
        return datetime.min
    for fmt in ('%m/%d/%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # Year-less fallback
    try:
        dt = datetime.strptime(s, '%m/%d')
        return dt.replace(year=datetime.now().year)
    except ValueError:
        return datetime.min


def _column_has_real_data(
    col,
    symptom_values: dict,
    total_values: dict,
    symptoms: list,
    totals: list,
) -> bool:
    """
    Return True if this date column has at least one non-placeholder value
    across any symptom or total row. ``X``, ``N/A`` and empty strings are
    treated as placeholders (no real data).
    """
    placeholders = {'X', 'N/A', '', '-', '--'}
    for s in symptoms:
        sv = symptom_values.get(s)
        if isinstance(sv, dict):
            v = sv.get(col)
            if v is not None and str(v).strip().upper() not in placeholders:
                return True
    for t in totals:
        tv = total_values.get(t)
        if isinstance(tv, dict):
            v = tv.get(col)
            if v is not None and str(v).strip().upper() not in placeholders:
                return True
    return False


def _format_visit_date_for_column(visit_date: str) -> str:
    """
    Format a visit date string into a short MM/DD/YY column header.

    Handles input formats: YYYY-MM-DD, MM/DD/YYYY, MM/DD/YY
    """
    from datetime import datetime
    for fmt_in, fmt_out in [
        ('%Y-%m-%d', '%m/%d/%y'),
        ('%m/%d/%Y', '%m/%d/%y'),
        ('%m/%d/%y', '%m/%d/%y'),
    ]:
        try:
            dt = datetime.strptime(visit_date.strip(), fmt_in)
            return dt.strftime(fmt_out).lstrip('0').replace('/0', '/')
        except ValueError:
            continue
    # If parsing fails, return as-is truncated
    return visit_date[:8]


def _build_formatted_ipss_table(
    symptom_values: dict,
    total_values: dict,
    date_columns: list,
    max_width: int = 45,
    visit_date: str = ""
) -> str:
    """
    Build a properly formatted IPSS ASCII table from extracted data.

    Enforces 45-character max width constraint. If data has more date columns
    than can fit, creates multiple tables.

    Args:
        symptom_values: Dict of symptom name -> score value (or dict of dicts for multi-date)
        total_values: Dict of 'Total' and 'BI' -> their values (or dict of dicts)
        date_columns: List of date strings for column headers
        max_width: Maximum table width (default 45 characters)

    Returns:
        Properly formatted ASCII table(s)
    """
    SYMPTOMS = ['Empty', 'Frequency', 'Urgency', 'Hesitancy', 'Intermittency', 'Flow', 'Nocturia']
    TOTALS = ['Total', 'BI']

    # Column widths
    symptom_col = 13  # Width for symptom names
    value_col = 8     # Width for value columns (accommodates dates like 01/15/25)

    # Calculate max dates that fit in width constraint
    max_dates = _max_dates_for_width(max_width, symptom_col, value_col)

    # Detect multi-date structured data (per-symptom dict-of-date->value).
    # The flat-value path (single value per symptom, used by clean_ipss_table
    # fallback) has nothing to filter or sort.
    has_per_date_data = any(
        isinstance(symptom_values.get(s), dict) for s in SYMPTOMS
    ) or any(
        isinstance(total_values.get(t), dict) for t in TOTALS
    )

    if has_per_date_data:
        # Drop columns with no real data — providers don't want phantom
        # 'X X X X' columns when an older visit's IPSS wasn't recorded.
        date_columns = [
            c for c in date_columns
            if _column_has_real_data(c, symptom_values, total_values, SYMPTOMS, TOTALS)
        ]
        # Order columns oldest -> newest so the most-recent historical visit
        # sits immediately to the left of the appended DOS (current-visit)
        # column, matching how providers read trends L->R.
        date_columns = sorted(date_columns, key=_parse_column_date_for_sort)

    # If no date columns or single date, build simple table.
    # Only fall back to a 'Score' placeholder column when caller passed in
    # flat (non-dated) data — the multi-date path with empty columns is
    # handled below by rendering a DOS-only table.
    if not date_columns and not has_per_date_data:
        date_columns = ['Score']

    # Split into multiple tables if needed. Only the LAST table
    # (chronologically most recent in the natural left-to-right read
    # order) carries the current-visit Date-Of-Service column. Earlier
    # tables, which show purely historical IPSS scores, do not need
    # an empty DOS column repeated.
    tables = []
    if date_columns:
        batches = [
            date_columns[i:i + max_dates]
            for i in range(0, len(date_columns), max_dates)
        ]
    else:
        # All historical columns were filtered out. Render exactly one
        # DOS-only table so the provider still has a column to fill in.
        batches = [[]]

    last_idx = len(batches) - 1
    for idx, batch_dates in enumerate(batches):
        table = _build_single_ipss_table(
            SYMPTOMS, symptom_values, total_values,
            batch_dates, symptom_col, value_col,
            include_dos_column=(idx == last_idx),
            visit_date=visit_date,
        )
        tables.append(table)

    return '\n\n'.join(tables)


def _build_single_ipss_table(
    symptoms: list,
    symptom_values: dict,
    total_values: dict,
    date_columns: list,
    symptom_col: int,
    value_col: int,
    include_dos_column: bool = True,
    visit_date: str = ""
) -> str:
    """
    Build a single IPSS table for a batch of date columns.

    Args:
        symptoms: List of symptom names
        symptom_values: Dict of symptom values
        total_values: Dict of total values
        date_columns: List of date column headers
        symptom_col: Width of symptom column
        value_col: Width of value columns
        include_dos_column: Whether to add a DOS column for current visit
        visit_date: Visit date string to use as DOS column header (falls back to 'Date')

    Returns:
        Formatted ASCII table string
    """
    # Add DOS column for current visit if requested
    all_columns = list(date_columns)
    if include_dos_column:
        # Use actual visit date if available, otherwise generic label
        dos_label = _format_visit_date_for_column(visit_date) if visit_date else 'Date'
        all_columns.append(dos_label)

    num_cols = len(all_columns)

    # Build separator line for data rows
    sep = '+' + '-' * (symptom_col + 2)
    for _ in range(num_cols):
        sep += '+' + '-' * value_col
    sep += '+'

    # Title row spans entire width
    inner_width = len(sep) - 2
    title_sep = '+' + '-' * inner_width + '+'
    title_row = '|' + 'IPSS'.center(inner_width) + '|'

    # Build header row with dates + DATE column
    header = '| ' + 'Symptom'.ljust(symptom_col) + ' |'
    for col in all_columns:
        col_str = str(col)[:value_col].center(value_col)
        header += col_str + '|'

    # Identify the DOS (current visit) column — it's the one we appended
    dos_col = all_columns[-1] if include_dos_column else None

    # Build symptom rows
    symptom_rows = []
    for symptom in symptoms:
        row = '| ' + symptom.ljust(symptom_col) + ' |'
        for col in all_columns:
            if col == dos_col and col not in date_columns:
                # Empty for DOS entry (current visit — provider fills in)
                value_str = ' ' * value_col
            elif isinstance(symptom_values.get(symptom), dict):
                value = symptom_values.get(symptom, {}).get(col, 'X')
                value_str = str(value).center(value_col)
            else:
                value = symptom_values.get(symptom, 'X')
                value_str = str(value).center(value_col)
            row += value_str + '|'
        symptom_rows.append(row)

    # Build total rows
    total_rows = []
    for total_name in ['Total', 'BI']:
        row = '| ' + total_name.ljust(symptom_col) + ' |'
        for col in all_columns:
            if col == dos_col and col not in date_columns:
                # For Total row, show "/35" template; for BI, empty
                if total_name == 'Total':
                    value_str = '  /35 '.center(value_col)[:value_col]
                else:
                    value_str = ' ' * value_col
            elif isinstance(total_values.get(total_name), dict):
                value = total_values.get(total_name, {}).get(col, 'N/A')
                value_str = str(value).center(value_col)
            else:
                value = total_values.get(total_name, 'N/A')
                value_str = str(value).center(value_col)
            row += value_str + '|'
        total_rows.append(row)

    # Assemble the table
    table_lines = [
        title_sep,
        title_row,
        sep,
        header,
        sep
    ]
    table_lines.extend(symptom_rows)
    table_lines.append(sep)
    table_lines.extend(total_rows)
    table_lines.append(sep)

    return '\n'.join(table_lines)


def get_empty_ipss_template(visit_date: str = "") -> str:
    """
    Return an empty IPSS template table for current visit documentation.

    Single-column form: when no historical IPSS data exists, do NOT emit
    a phantom "Prior" column with `--` placeholders — that wastes space
    and confuses providers. Render only the current-visit column for
    them to fill in.

    Args:
        visit_date: Visit date string for column header (falls back to 'Date')

    Returns:
        Empty IPSS template in ASCII table format with one column
    """
    col_label = _format_visit_date_for_column(visit_date) if visit_date else "Date"
    # Pad/truncate to 7 chars to fit column width
    col_header = col_label[:7].center(7)
    return f"""+-----------------------+
|         IPSS          |
+---------------+-------+
| Symptom       |{col_header}|
+---------------+-------+
| Empty         |       |
| Frequency     |       |
| Urgency       |       |
| Hesitancy     |       |
| Intermittency |       |
| Flow          |       |
| Nocturia      |       |
+---------------+-------+
| Total         |   /35 |
| BI            |       |
+---------------+-------+"""


def _parse_ipss_table_multi_date(ipss_table: str) -> tuple:
    """
    Parse an IPSS table to extract multi-date data.

    Returns:
        Tuple of (symptom_values, total_values, date_columns)
        where symptom_values = {symptom: {date: value, ...}, ...}
    """
    SYMPTOMS = ['Empty', 'Frequency', 'Urgency', 'Hesitancy', 'Intermittency', 'Flow', 'Nocturia']
    TOTALS = ['Total', 'BI']

    lines = ipss_table.strip().split('\n')
    date_columns = []
    symptom_values = {s: {} for s in SYMPTOMS}
    total_values = {t: {} for t in TOTALS}

    for line in lines:
        line = line.strip()
        if not line or re.match(r'^[\+\-]+$', line):
            continue

        # Extract dates from header row
        if 'Symptom' in line:
            dates = re.findall(r'\d{1,2}/\d{1,2}(?:/\d{2,4})?', line)
            if dates:
                date_columns = dates
            continue

        # Skip title row
        if re.match(r'^\|?\s*IPSS\s*\|?$', line):
            continue

        # Parse symptom rows - extract all values
        for symptom in SYMPTOMS:
            if symptom in line:
                # Split by | and extract numeric values
                parts = re.split(r'\|', line)
                values = []
                for part in parts:
                    part = part.strip()
                    if part and part not in ['', symptom]:
                        # Check if it's a number or X
                        if re.match(r'^\d+$', part) or part == 'X':
                            values.append(part)
                # Map values to dates
                for i, date in enumerate(date_columns):
                    if i < len(values):
                        symptom_values[symptom][date] = values[i]
                break

        # Parse total rows
        for total_name in TOTALS:
            if total_name in line:
                parts = re.split(r'\|', line)
                values = []
                for part in parts:
                    part = part.strip()
                    if part and part not in ['', total_name]:
                        if re.match(r'^[\d/]+$', part) or part in ['X', 'N/A']:
                            values.append(part)
                for i, date in enumerate(date_columns):
                    if i < len(values):
                        total_values[total_name][date] = values[i]
                break

    return symptom_values, total_values, date_columns


def synthesize_ipss(gu_notes: List[Dict[str, str]], max_width: int = 45, visit_date: str = "") -> str:
    """
    Synthesize IPSS scores from GU notes into ASCII table.

    Per instructions: Combine all IPSS results into ASCII table (max 45 chars wide).
    If too much data, creates additional tables to stay within width constraint.
    If no IPSS data exists, returns an empty template for the provider to fill in.

    Args:
        gu_notes: List of GU note dictionaries
        max_width: Maximum table width (default 45 characters)

    Returns:
        Combined IPSS table(s) in ASCII format, split if needed for width
    """
    all_ipss = []

    for note in gu_notes:
        if note.get("IPSS"):
            all_ipss.append(note["IPSS"])

    if not all_ipss:
        # Return empty template for providers to fill in during visit
        return get_empty_ipss_template(visit_date=visit_date)

    if len(all_ipss) == 1:
        # Parse the table to get structured data
        symptom_values, total_values, date_columns = _parse_ipss_table_multi_date(all_ipss[0])
        if date_columns or visit_date:
            # Always rebuild to ensure visit date column is included.
            # When the parser found no real prior dates we pass an
            # empty list so no phantom "Prior" column is emitted —
            # _build_formatted_ipss_table will render only the
            # current-visit DOS column.
            return _build_formatted_ipss_table(
                symptom_values, total_values, date_columns or [], max_width,
                visit_date=visit_date
            )
        # Fallback: clean the raw table if no structured data extracted
        cleaned = clean_ipss_table(all_ipss[0])
        return cleaned

    # Multiple tables - combine data then rebuild with width constraint
    SYMPTOMS = ['Empty', 'Frequency', 'Urgency', 'Hesitancy', 'Intermittency', 'Flow', 'Nocturia']
    TOTALS = ['Total', 'BI']

    combined_symptoms = {s: {} for s in SYMPTOMS}
    combined_totals = {t: {} for t in TOTALS}
    all_dates = []

    for ipss_table in all_ipss:
        symptom_values, total_values, date_columns = _parse_ipss_table_multi_date(ipss_table)

        # Merge dates (avoid duplicates)
        for date in date_columns:
            if date not in all_dates:
                all_dates.append(date)

        # Merge symptom values
        for symptom in SYMPTOMS:
            for date, value in symptom_values[symptom].items():
                if date not in combined_symptoms[symptom]:
                    combined_symptoms[symptom][date] = value

        # Merge total values
        for total_name in TOTALS:
            for date, value in total_values[total_name].items():
                if date not in combined_totals[total_name]:
                    combined_totals[total_name][date] = value

    # If no structured data could be extracted, fall back to LLM
    if not all_dates:
        instructions = """Combine these IPSS tables into ONE single ASCII table.
- Include all dates/columns from all tables in a single table
- Do NOT create multiple separate tables - combine everything into ONE table
- Preserve the ASCII table format with + and - characters
- Ensure alignment is maintained
- Use MM/DD/YY format with 2-digit year for dates
- Do NOT add placeholder 'X' columns - only include actual data columns
- Each date should appear ONLY ONCE as a column header

CRITICAL: Return ONLY ONE table with all data combined. Do NOT create duplicate columns or split tables."""

        result = combine_sections_with_llm("IPSS Table", all_ipss, instructions)

        # Remove LLM meta-commentary
        if result:
            result = re.sub(r'\n\n?Note:.*$', '', result, flags=re.DOTALL | re.IGNORECASE)
            result = re.sub(r'\n\n?Also,.*$', '', result, flags=re.DOTALL | re.IGNORECASE)
            result = re.sub(r'\n\n?Please.*$', '', result, flags=re.DOTALL | re.IGNORECASE)
            result = re.sub(r'\n\n?I have.*$', '', result, flags=re.DOTALL | re.IGNORECASE)
            result = result.strip()

        if result:
            result = clean_ipss_table(result)

        return result

    # Build table(s) with width constraint - splits automatically if needed
    return _build_formatted_ipss_table(
        combined_symptoms, combined_totals, all_dates, max_width,
        visit_date=visit_date
    )


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
