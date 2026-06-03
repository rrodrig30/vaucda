"""
Endocrine Labs Extractor

Extracts endocrine-related lab results (testosterone, estrogens, LH, FSH, A1C, etc.)
from clinical documents, with support for VA tabular formats and temporal trend tables.
"""

import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime


# ============================================================================
# COMPREHENSIVE ENDOCRINE LAB PATTERNS
# ============================================================================
# These patterns cover ALL VA lab format variations for testosterone, estrogen,
# LH, FSH, and other endocrine labs.

TESTOSTERONE_PATTERNS = [
    # Total testosterone - all VA naming conventions
    r'TESTOSTERONE,?\s*(?:SERUM\s*)?TOTAL',          # TESTOSTERONE,SERUM TOTAL or TESTOSTERONE TOTAL
    r'TESTOSTERONE,?\s*TOTAL,?\s*(?:LC/?MS/?MS)?',   # TESTOSTERONE,TOTAL,LC/MS/MS
    r'TOTAL\s+TESTOSTERONE',                          # Total Testosterone
    r'TESTOSTERONE\s+SERUM\s+TOTAL',                  # TESTOSTERONE SERUM TOTAL
    r'TESTOSTERONE,?\s*SERUM(?!\s*FREE)',            # TESTOSTERONE,SERUM (but not FREE)
    r'TESTOSTERONE\s+LEVEL',                          # Testosterone Level
    r'TESTOSTERONE(?!\s*(?:,?\s*FREE|%|FREE|BINDING))',  # Plain TESTOSTERONE (not free/binding)
]

FREE_TESTOSTERONE_PATTERNS = [
    r'TESTOSTERONE,?\s*FREE',                         # TESTOSTERONE,FREE or TESTOSTERONE FREE
    r'FREE\s+TESTOSTERONE',                           # Free Testosterone
    r'TESTOSTERONE\s+FREE\s+SERUM',                   # Testosterone Free Serum
    r'FREE\s+TESTOSTERONE,?\s*SERUM',                 # Free Testosterone, Serum
]

PCT_FREE_TESTOSTERONE_PATTERNS = [
    r'%\s*FREE\s+TESTOSTERONE',                       # % Free Testosterone
    r'TESTOSTERONE,?\s*%\s*FREE',                     # Testosterone % Free
    r'FREE\s+TESTOSTERONE\s*%',                       # Free Testosterone %
    r'PERCENT\s+FREE\s+TESTOSTERONE',                 # Percent Free Testosterone
]

ESTROGEN_PATTERNS = [
    r'ESTROGENS?,?\s*TOTAL',                          # ESTROGENS,TOTAL or ESTROGEN,TOTAL
    r'TOTAL\s+ESTROGENS?',                            # Total Estrogens
    r'ESTROGENS?,?\s*SERUM',                          # ESTROGEN,SERUM
    r'ESTRADIOL',                                     # Estradiol (E2)
    r'E2\s*(?:LEVEL|SERUM)?',                         # E2 or E2 Level
    r'ESTRONE',                                       # Estrone (E1)
]

LH_PATTERNS = [
    r'LH\s*\(LUTEINIZING\s+HORMONE\)',                # LH (LUTEINIZING HORMONE)
    r'LUTEINIZING\s+HORMONE\s*\(LH\)',                # LUTEINIZING HORMONE (LH)
    r'LUTEINIZING\s+HORMONE',                         # LUTEINIZING HORMONE
    r'LH\s+SERUM',                                    # LH Serum
    r'\bLH\b(?!\s*PANEL)',                           # LH (word boundary, not part of "LH PANEL")
]

FSH_PATTERNS = [
    r'FSH\s*\(FOLLICLE[- ]?STIMULATING[- ]?HORMONE\)',   # FSH (FOLLICLE STIMULATING HORMONE)
    r'FOLLICLE[- ]?STIMULATING[- ]?HORMONE\s*\(FSH\)',   # FOLLICLE STIMULATING HORMONE (FSH)
    r'FOLLICLE[- ]?STIMULATING[- ]?HORMONE',             # FOLLICLE STIMULATING HORMONE
    r'FSH\s+SERUM',                                       # FSH Serum
    r'\bFSH\b(?!\s*PANEL)',                              # FSH (word boundary)
]

LH_FSH_PANEL_PATTERN = r'LH/?FSH\s+PANEL'  # LH/FSH PANEL or LH FSH PANEL

# Other endocrine labs
OTHER_ENDOCRINE_PATTERNS = {
    'A1C': [r'(?:A1[Cc]|HbA1[Cc]|HEMOGLOBIN\s+A1[Cc]|GLYCOHEMOGLOBIN)'],
    'TSH': [r'TSH(?:\s+SERUM)?', r'THYROID\s+STIMULATING\s+HORMONE'],
    'Prolactin': [r'PROLACTIN(?:\s+SERUM)?'],
    'Cortisol': [r'CORTISOL(?:\s+(?:AM|PM|SERUM))?'],
    'DHEA-S': [r'DHEA[- ]?S(?:ULFATE)?', r'DEHYDROEPIANDROSTERONE\s+SULFATE'],
    'SHBG': [r'SHBG', r'SEX\s+HORMONE[- ]?BINDING\s+GLOBULIN'],
    'Vitamin D': [r'VITAMIN\s+D,?\s*(?:25-?OH|25\s*HYDROXY)?', r'25-?HYDROXYVITAMIN\s+D'],
    'B12': [r'VITAMIN\s+B[- ]?12', r'B12', r'CYANOCOBALAMIN'],
    'AFP': [r'AFP', r'ALPHA[- ]?FETOPROTEIN'],
    'HCG': [r'HCG', r'BETA[- ]?HCG', r'HUMAN\s+CHORIONIC\s+GONADOTROPIN'],
    'LDH': [r'LDH', r'LACTATE\s+DEHYDROGENASE'],
}

# Reference ranges for male endocrine labs
MALE_REFERENCE_RANGES = {
    'Total Testosterone': (175, 781, 'ng/dL'),
    'Free Testosterone': (5.0, 21.0, 'pg/mL'),
    '% Free Testosterone': (1.5, 4.2, '%'),
    'LH': (1.5, 9.3, 'mIU/mL'),
    'FSH': (1.5, 12.4, 'mIU/mL'),
    'Estradiol': (10, 40, 'pg/mL'),
    'Total Estrogens': (40, 115, 'pg/mL'),
    'Prolactin': (2.0, 18.0, 'ng/mL'),
    'A1C': (4.0, 5.6, '%'),
}


def extract_endocrine_labs(clinical_document: str) -> str:
    """
    Extract endocrine lab results from clinical documents with collection dates.

    Supports:
    - VA tabular format (TEST_NAME  VALUE  UNIT  REF_RANGE)
    - VA reverse format (TEST: value units - DATE)
    - Human-readable format (TEST value units (DATE))
    - Date-prefixed format (DATE: TEST value)

    Target labs:
    - Total Testosterone, Free Testosterone, % Free Testosterone
    - Total Estrogens, Estradiol
    - LH (Luteinizing Hormone), FSH (Follicle-Stimulating Hormone)
    - A1C, TSH, Prolactin, Cortisol, DHEA-S, SHBG
    - Vitamin D, B12, AFP, HCG, LDH

    Args:
        clinical_document: Full clinical document

    Returns:
        Extracted endocrine lab results with dates (table format if multiple values)
    """
    # Collect all endocrine results as structured data
    endocrine_data: List[Dict] = []

    # Strategy 1: Extract from VA tabular format (most reliable for VA documents)
    endocrine_data.extend(_extract_va_tabular_format(clinical_document))

    # Strategy 2: Extract from ENDOCRINE LABS section
    endocrine_data.extend(_extract_from_endocrine_section(clinical_document))

    # Strategy 3: Extract from general LABS section
    endocrine_data.extend(_extract_from_labs_section(clinical_document))

    # Strategy 4: Extract using collection date context
    endocrine_data.extend(_extract_with_collection_date(clinical_document))

    # Deduplicate results
    endocrine_data = _deduplicate_results(endocrine_data)

    if not endocrine_data:
        return ""

    # Format output - use table if we have multiple values for testosterone/LH/FSH
    return _format_endocrine_output(endocrine_data)


def _extract_va_tabular_format(clinical_document: str) -> List[Dict]:
    """
    Extract endocrine labs from VA tabular format.

    VA format example:
    Specimen Collection Date: Aug 19, 2025@10:30
      Test name                         Result    units      Ref.   range   Site Code
    ---------------------------------------------------------------------------------
    TESTOSTERONE,SERUM TOTAL            343 L     ng/dL      175 - 781      [671]
    TESTOSTERONE,FREE                    8.5      pg/mL      5.0 - 21.0     [671]
    LH                                   5.2      mIU/mL     1.5 - 9.3      [671]
    FSH                                  4.8      mIU/mL     1.5 - 12.4     [671]
    ESTROGENS,TOTAL                      42       pg/mL      40 - 115       [671]

    Returns:
        List of dicts with test_name, value, unit, flag, date, ref_range
    """
    results = []
    current_collection_date = None

    # Build combined patterns
    all_test_patterns = (
        TESTOSTERONE_PATTERNS +
        FREE_TESTOSTERONE_PATTERNS +
        PCT_FREE_TESTOSTERONE_PATTERNS +
        ESTROGEN_PATTERNS +
        LH_PATTERNS +
        FSH_PATTERNS +
        [LH_FSH_PANEL_PATTERN]
    )
    for patterns in OTHER_ENDOCRINE_PATTERNS.values():
        all_test_patterns.extend(patterns)

    combined_pattern = '|'.join(f'(?:{p})' for p in all_test_patterns)

    for line in clinical_document.split('\n'):
        # Check for collection date — multiple formats:
        #   "Specimen Collection Date: Aug 19, 2025"
        #   "Specimen Collection Date: Aug 19, 2025@10:30"
        #   "Collection date: 8/19/2025"
        date_match = re.search(
            r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
            line
        )
        if date_match:
            current_collection_date = date_match.group(1)
            continue

        # Also check for alternate date formats
        alt_date_match = re.search(
            r'Collection date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
            line
        )
        if alt_date_match:
            current_collection_date = alt_date_match.group(1)
            continue

        # Numeric date format: "Specimen Collection Date: 8/19/2025"
        numeric_date_match = re.search(
            r'(?:Specimen )?Collection [Dd]ate:\s*(\d{1,2}/\d{1,2}/\d{2,4})',
            line
        )
        if numeric_date_match:
            current_collection_date = numeric_date_match.group(1)
            continue

        # Skip header and separator lines
        if re.match(r'^\s*(Test name|Result|units|Ref\.|[-=]+)\s*$', line, re.IGNORECASE):
            continue

        # Try to match VA tabular format:
        # TEST_NAME      VALUE [H/L]  UNIT   REF_RANGE   [SITE]
        tabular_match = re.match(
            rf'^\s*({combined_pattern})\s+(<?\d+\.?\d*)\s*([HL])?\s+'
            rf'(ng/dL|pg/mL|mIU/mL|%|IU/L|ng/mL|mcg/dL|U/L|pg/ml|ng/dl)?\s*'
            rf'(?:(\d+\.?\d*\s*-\s*\d+\.?\d*))?\s*(?:\[\d+\])?',
            line,
            re.IGNORECASE
        )

        if tabular_match:
            test_name = tabular_match.group(1).strip()
            value = tabular_match.group(2).strip()
            flag = tabular_match.group(3) if tabular_match.group(3) else ''
            unit = tabular_match.group(4) if tabular_match.group(4) else ''
            ref_range = tabular_match.group(5) if tabular_match.group(5) else ''

            # Normalize test name
            normalized_name = _normalize_test_name(test_name)

            # Check for inline date in parentheses at end of line
            # e.g., "TESTOSTERONE 345 ng/dL [671] (Oct 27, 2025)"
            inline_date = ''
            inline_date_match = re.search(
                r'\(([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\)\s*$', line
            )
            if not inline_date_match:
                # Try numeric: (10/27/2025)
                inline_date_match = re.search(
                    r'\((\d{1,2}/\d{1,2}/\d{2,4})\)\s*$', line
                )
            if inline_date_match:
                inline_date = inline_date_match.group(1)

            results.append({
                'test_name': normalized_name,
                'value': value,
                'unit': unit,
                'flag': flag,
                'date': inline_date or current_collection_date or '',
                'ref_range': ref_range
            })

    return results


def _extract_from_endocrine_section(clinical_document: str) -> List[Dict]:
    """
    Extract from explicit ENDOCRINE LABS section.
    """
    results = []

    section_match = re.search(
        r'={5,}\s*ENDOCRINE\s+LABS\s*={5,}\s*\n(.*?)(?=\n\s*={5,}|$)',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    if not section_match:
        return results

    section_content = section_match.group(1)

    for line in section_content.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Try VA reverse format: "Test: value units (ref: range) - Date"
        reverse_match = re.match(
            r'^([A-Za-z][A-Za-z0-9\s/\(\),\-%]+?):\s*'
            r'(<?\d+\.?\d*)\s*'
            r'([A-Za-z/%]+)?\s*'
            r'(?:\(ref:\s*[\d.\-\s]+\))?\s*'
            r'(?:\(([HL])\))?\s*'
            r'(?:-\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4}))?$',
            line
        )
        if reverse_match:
            results.append({
                'test_name': _normalize_test_name(reverse_match.group(1)),
                'value': reverse_match.group(2),
                'unit': reverse_match.group(3) or '',
                'flag': reverse_match.group(4) or '',
                'date': reverse_match.group(5) or '',
                'ref_range': ''
            })
            continue

        # Try inline date format: "Test value unit (Date)"
        inline_match = re.match(
            r'^([A-Za-z][A-Za-z\s,]+)\s+'
            r'(<?\d+\.?\d*)\s*'
            r'([A-Za-z/%]+)?\s*'
            r'(?:\(([HL])\))?\s*'
            r'\(([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\)',
            line
        )
        if inline_match:
            results.append({
                'test_name': _normalize_test_name(inline_match.group(1)),
                'value': inline_match.group(2),
                'unit': inline_match.group(3) or '',
                'flag': inline_match.group(4) or '',
                'date': inline_match.group(5) or '',
                'ref_range': ''
            })

    return results


def _extract_from_labs_section(clinical_document: str) -> List[Dict]:
    """
    Extract endocrine markers from general LABS section.
    """
    results = []

    section_match = re.search(
        r'====+\s*LABS\s*====+\s*\n(.*?)(?====+|$)',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    if not section_match:
        return results

    section_content = section_match.group(1)

    # Define markers to look for
    markers = [
        'TESTOSTERONE', 'ESTROGEN', 'ESTRADIOL', 'LH', 'FSH',
        'LUTEINIZING', 'FOLLICLE', 'A1C', 'HBA1C', 'TSH',
        'PROLACTIN', 'CORTISOL', 'VITAMIN D', 'B12'
    ]

    for line in section_content.split('\n'):
        line_upper = line.upper().strip()
        if not line_upper:
            continue

        # Check if line contains an endocrine marker
        if not any(marker in line_upper for marker in markers):
            continue

        # Try to extract value and date
        # Pattern: "Test: value units (ref) - Date" or "Test: value (flag) (Date)"
        match = re.match(
            r'^([A-Za-z][A-Za-z0-9\s/\(\),\-%]+?):\s*'
            r'(<?\d+\.?\d*)\s*'
            r'([A-Za-z/%]+)?\s*'
            r'(?:\([^)]*\))?\s*'
            r'(?:\(([HL])\))?\s*'
            r'(?:-\s*)?'
            r'(?:\()?([A-Za-z]{3}\s+\d{1,2},\s+\d{4})(?:\))?',
            line.strip()
        )
        if match:
            results.append({
                'test_name': _normalize_test_name(match.group(1)),
                'value': match.group(2),
                'unit': match.group(3) or '',
                'flag': match.group(4) or '',
                'date': match.group(5) or '',
                'ref_range': ''
            })

    return results


def _extract_with_collection_date(clinical_document: str) -> List[Dict]:
    """
    Extract endocrine values by tracking collection dates through document.
    """
    results = []
    current_collection_date = None

    # Build combined test patterns
    test_patterns = [
        (TESTOSTERONE_PATTERNS, 'Total Testosterone', 'ng/dL'),
        (FREE_TESTOSTERONE_PATTERNS, 'Free Testosterone', 'pg/mL'),
        (PCT_FREE_TESTOSTERONE_PATTERNS, '% Free Testosterone', '%'),
        (ESTROGEN_PATTERNS, 'Estrogen', 'pg/mL'),
        (LH_PATTERNS, 'LH', 'mIU/mL'),
        (FSH_PATTERNS, 'FSH', 'mIU/mL'),
    ]

    for line in clinical_document.split('\n'):
        # Check for collection date headers
        date_match = re.search(
            r'(?:Specimen Collection Date|Collection date):\s*'
            r'([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
            line
        )
        if date_match:
            current_collection_date = date_match.group(1)
            continue

        # Also check for "your DATE test results" format
        alt_date = re.search(
            r'your\s+([A-Za-z]{3}\s+\d{1,2}\s+\d{4})\s+test results',
            line
        )
        if alt_date:
            current_collection_date = alt_date.group(1)
            continue

        if not current_collection_date:
            continue

        # Try each test pattern
        for patterns, normalized_name, default_unit in test_patterns:
            combined = '|'.join(f'(?:{p})' for p in patterns)
            match = re.search(
                rf'({combined})[:\s,]+(<?\d+\.?\d*)\s*([HL])?\s*'
                rf'({default_unit}|ng/dL|pg/mL|mIU/mL|%)?',
                line,
                re.IGNORECASE
            )
            if match:
                results.append({
                    'test_name': normalized_name,
                    'value': match.group(2),
                    'unit': match.group(4) or default_unit,
                    'flag': match.group(3) or '',
                    'date': current_collection_date,
                    'ref_range': ''
                })

    return results


def _normalize_test_name(raw_name: str) -> str:
    """
    Normalize test names to consistent format.
    """
    name_upper = raw_name.upper().strip()

    # Testosterone variants
    if 'TESTOSTERONE' in name_upper:
        if '%' in name_upper or 'PERCENT' in name_upper:
            return '% Free Testosterone'
        elif 'FREE' in name_upper:
            return 'Free Testosterone'
        else:
            return 'Total Testosterone'

    # Estrogen variants
    if 'ESTRADIOL' in name_upper or 'E2' in name_upper:
        return 'Estradiol'
    if 'ESTROGEN' in name_upper:
        return 'Total Estrogens'

    # LH/FSH
    if 'LUTEINIZING' in name_upper or name_upper == 'LH':
        return 'LH'
    if 'FOLLICLE' in name_upper or name_upper == 'FSH':
        return 'FSH'
    if 'LH/FSH' in name_upper or 'LH FSH' in name_upper:
        return 'LH/FSH Panel'

    # Other tests
    if 'A1C' in name_upper or 'HBA1C' in name_upper or 'GLYCO' in name_upper:
        return 'HbA1c'
    if 'TSH' in name_upper:
        return 'TSH'
    if 'PROLACTIN' in name_upper:
        return 'Prolactin'
    if 'CORTISOL' in name_upper:
        return 'Cortisol'
    if 'VITAMIN D' in name_upper:
        return 'Vitamin D'
    if 'B12' in name_upper:
        return 'Vitamin B12'
    if 'AFP' in name_upper or 'FETOPROTEIN' in name_upper:
        return 'AFP'
    if 'HCG' in name_upper:
        return 'HCG'
    if 'LDH' in name_upper or 'LACTATE' in name_upper:
        return 'LDH'

    # Default: title case the raw name
    return raw_name.strip().title()


def _deduplicate_results(results: List[Dict]) -> List[Dict]:
    """
    Remove duplicate results, preferring those with dates.
    """
    # Group by (test_name, value, date)
    seen = {}
    for r in results:
        key = (r['test_name'], r['value'], r.get('date', ''))
        if key not in seen:
            seen[key] = r
        else:
            # Prefer entry with more complete data
            existing = seen[key]
            if not existing.get('unit') and r.get('unit'):
                seen[key] = r
            elif not existing.get('date') and r.get('date'):
                seen[key] = r

    return list(seen.values())


def _format_endocrine_output(results: List[Dict]) -> str:
    """
    Format endocrine results for output.

    Uses table format for testosterone/estrogen/LH/FSH if multiple dates present,
    otherwise uses simple list format.

    Args:
        results: List of extracted endocrine lab dicts

    Returns:
        Formatted string output
    """
    # Group results by test name
    by_test: Dict[str, List[Dict]] = {}
    for r in results:
        name = r['test_name']
        if name not in by_test:
            by_test[name] = []
        by_test[name].append(r)

    # Check if we should use table format (multiple dates for hormone panels)
    hormone_tests = ['Total Testosterone', 'Free Testosterone', '% Free Testosterone',
                     'LH', 'FSH', 'Total Estrogens', 'Estradiol']

    # Collect all unique dates for hormone tests
    hormone_dates = set()
    for test in hormone_tests:
        if test in by_test:
            for r in by_test[test]:
                if r.get('date'):
                    hormone_dates.add(r['date'])

    output_lines = []

    # If we have multiple dates for hormones, use table format
    if len(hormone_dates) >= 2:
        table_output = _format_hormone_table(by_test, hormone_tests, hormone_dates)
        if table_output:
            output_lines.append(table_output)

        # Add non-hormone tests in simple format
        for test_name, test_results in by_test.items():
            if test_name not in hormone_tests:
                for r in test_results:
                    output_lines.append(_format_single_result(r))
    else:
        # Simple list format
        # Order by: Testosterone, LH/FSH, Estrogens, then others
        priority_order = ['Total Testosterone', 'Free Testosterone', '% Free Testosterone',
                          'LH', 'FSH', 'Total Estrogens', 'Estradiol']

        for test_name in priority_order:
            if test_name in by_test:
                for r in by_test[test_name]:
                    output_lines.append(_format_single_result(r))
                del by_test[test_name]

        # Remaining tests
        for test_name, test_results in by_test.items():
            for r in test_results:
                output_lines.append(_format_single_result(r))

    return '\n'.join(output_lines)


def _format_single_result(result: Dict) -> str:
    """
    Format a single endocrine lab result.
    """
    parts = [result['test_name'], result['value']]

    if result.get('unit'):
        parts.append(result['unit'])

    if result.get('flag'):
        parts.append(f"({result['flag']})")

    if result.get('date'):
        parts.append(f"({result['date']})")

    return ' '.join(parts)


def _format_hormone_table(
    by_test: Dict[str, List[Dict]],
    hormone_tests: List[str],
    dates: set
) -> str:
    """
    Format hormone results as a temporal trend table.

    Creates table like:
    +---------------------+-------------+-------------+-------------+
    | Test                | Jan 15 2025 | Mar 20 2025 | Jun 10 2025 |
    +---------------------+-------------+-------------+-------------+
    | Total Testosterone  | 343 ng/dL   | 289 ng/dL L | 312 ng/dL   |
    | Free Testosterone   | 8.5 pg/mL   | 7.2 pg/mL   | 8.0 pg/mL   |
    | LH                  | 5.2 mIU/mL  | 6.1 mIU/mL  | 5.8 mIU/mL  |
    | FSH                 | 4.8 mIU/mL  | 5.2 mIU/mL  | 5.0 mIU/mL  |
    +---------------------+-------------+-------------+-------------+

    Returns:
        Table string or empty string if no data
    """
    # Sort dates (try to parse, fall back to string sort)
    sorted_dates = _sort_dates(list(dates))

    # Only include dates with actual data
    dates_with_data = []
    for d in sorted_dates:
        has_data = False
        for test in hormone_tests:
            if test in by_test:
                for r in by_test[test]:
                    if r.get('date') == d:
                        has_data = True
                        break
            if has_data:
                break
        if has_data:
            dates_with_data.append(d)

    if len(dates_with_data) < 2:
        return ""  # Not enough dates for table

    # Width-capped column count. The rendered note targets CPRS lines —
    # the testosterone/hormone table must fit within 60 characters so
    # it doesn't wrap on the receiving side. We:
    #   1. Compute final column widths (test name col + date cols).
    #   2. Drop OLDEST dates first until the table fits in 60 chars or
    #      we hit the 2-date floor (table needs ≥2 dates to be useful).
    # If even 2 dates exceed 60 chars (very long test names), the table
    # still renders — we don't truncate values — but the line cap
    # preserves the contract for the common case.
    MAX_TABLE_WIDTH = 60

    # Tentative column widths (we recompute test_col_width after final
    # tests-with-data filter, since dropping dates can't shrink it).
    tentative_test_col_width = (
        max(len(t) for t in (hormone_tests if hormone_tests else ['Test'])) + 2
    )
    # Date column width: at minimum 13 to fit values like "293.91 ng/dL".
    tentative_date_col_width = max(
        max(len(_format_date_short(d)) for d in dates_with_data) + 2,
        13,
    )
    fixed_chars = 2 + tentative_test_col_width  # outer pipes + inner pipe
    chars_per_date = tentative_date_col_width + 1
    max_dates_for_width = max(
        2, (MAX_TABLE_WIDTH - fixed_chars) // chars_per_date
    )
    if len(dates_with_data) > max_dates_for_width:
        # Keep the MOST RECENT dates (list is ascending so slice from end).
        dates_with_data = dates_with_data[-max_dates_for_width:]

    # Build lookup for quick access
    lookup: Dict[str, Dict[str, Dict]] = {}
    for test_name in hormone_tests:
        lookup[test_name] = {}
        if test_name in by_test:
            for r in by_test[test_name]:
                if r.get('date'):
                    lookup[test_name][r['date']] = r

    # Only include tests that have data
    tests_with_data = [t for t in hormone_tests if t in lookup and lookup[t]]

    if not tests_with_data:
        return ""

    # Calculate column widths
    test_col_width = max(len(t) for t in tests_with_data) + 2
    date_col_width = max(len(_format_date_short(d)) for d in dates_with_data) + 2

    # Ensure minimum width for values
    date_col_width = max(date_col_width, 13)

    # Build table
    lines = []

    # Header separator
    header_sep = '+' + '-' * test_col_width + '+' + (('-' * date_col_width + '+') * len(dates_with_data))
    lines.append(header_sep)

    # Header row
    header = '|' + ' Test'.ljust(test_col_width) + '|'
    for d in dates_with_data:
        header += (' ' + _format_date_short(d)).ljust(date_col_width) + '|'
    lines.append(header)

    lines.append(header_sep)

    # Data rows
    for test_name in tests_with_data:
        row = '|' + (' ' + test_name).ljust(test_col_width) + '|'
        for d in dates_with_data:
            if d in lookup[test_name]:
                r = lookup[test_name][d]
                cell = f" {r['value']}"
                if r.get('unit'):
                    cell += f" {r['unit']}"
                if r.get('flag'):
                    cell += f" {r['flag']}"
            else:
                cell = ' -'
            row += cell.ljust(date_col_width) + '|'
        lines.append(row)

    lines.append(header_sep)

    return '\n'.join(lines)


def _format_date_short(date_str: str) -> str:
    """
    Format date string to shorter format: "Jan 15 2025" -> "Jan 15 '25"
    """
    match = re.match(r'([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', date_str)
    if match:
        month = match.group(1)
        day = match.group(2)
        year = match.group(3)[-2:]  # Last 2 digits
        return f"{month} {day} '{year}"
    return date_str


def _sort_dates(dates: List[str]) -> List[str]:
    """
    Sort dates chronologically.
    """
    def parse_date(d: str) -> datetime:
        try:
            # Try "MMM DD, YYYY" format
            return datetime.strptime(d.replace(',', ''), '%b %d %Y')
        except ValueError:
            try:
                # Try "MMM DD YYYY" format
                return datetime.strptime(d, '%b %d %Y')
            except ValueError:
                # Return epoch if can't parse
                return datetime(1970, 1, 1)

    return sorted(dates, key=parse_date)


# Legacy function for backward compatibility
def _extract_endocrine_values_from_line(line: str, date: str, results_list: list):
    """
    Extract endocrine lab values from a single line with a known date.

    DEPRECATED: Use extract_endocrine_labs() instead.

    Args:
        line: Line containing lab results
        date: Date string to associate with results
        results_list: List to append results to (modified in place)
    """
    # Build test patterns
    test_configs = [
        (TESTOSTERONE_PATTERNS, 'Total Testosterone', r'ng/dL|ng/dl'),
        (FREE_TESTOSTERONE_PATTERNS, 'Free Testosterone', r'pg/mL|pg/ml'),
        (PCT_FREE_TESTOSTERONE_PATTERNS, '% Free Testosterone', r'%'),
        (ESTROGEN_PATTERNS, 'Estrogen', r'pg/mL|pg/ml'),
        (LH_PATTERNS, 'LH', r'mIU/mL|mIU/ml|IU/L'),
        (FSH_PATTERNS, 'FSH', r'mIU/mL|mIU/ml|IU/L'),
    ]

    for patterns, normalized_name, unit_pattern in test_configs:
        combined = '|'.join(f'(?:{p})' for p in patterns)
        full_pattern = rf'({combined})[:\s,]+(<?\d+\.?\d*)\s*([HL])?\s*({unit_pattern})?'

        for match in re.finditer(full_pattern, line, re.IGNORECASE):
            value = match.group(2).strip()
            hl_marker = match.group(3).strip() if match.group(3) else ""
            unit = match.group(4).strip() if match.group(4) else ""

            result_str = f"{normalized_name} {value}"
            if unit:
                result_str += f" {unit}"
            if hl_marker:
                result_str += f" ({hl_marker})"
            result_str += f" ({date})"

            results_list.append(result_str)
