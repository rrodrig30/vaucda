"""
General Lab Results Extractor

Extracts general laboratory results from clinical documents.
"""

import re


# Lab filtering configuration
# Define which labs to keep for each category
CBC_KEEP = {'WBC', 'HEMOGLOBIN', 'HGB', 'HEMATOCRIT', 'HCT', 'PLT', 'PLATELET', 'PLATELETS'}
BMP_KEEP = {'BUN', 'CREATININE', 'CREAT', 'EGFR', 'GFR'}
UA_KEEP = {'SG', 'SPECIFIC GRAVITY', 'PH', 'GLU', 'GLUCOSE', 'PRO', 'PROTEIN', 'URINALYSIS'}

# Always report these regardless of filtering
ALWAYS_REPORT = {
    'TESTOSTERONE', 'TOTAL TESTOSTERONE', 'FREE TESTOSTERONE',
    'ESTROGEN', 'ESTROGENS', 'TOTAL ESTROGENS',
    'LH', 'FSH',
    'PTH', 'PARATHYROID HORMONE',
    'AFP', 'ALPHA-FETOPROTEIN',
    'HCG', 'BETA-HCG', 'B-HCG',
    'LDH', 'LACTATE DEHYDROGENASE',
    'URORISK'  # Report all Urorisk components
}


def should_keep_lab(test_name: str, lab_line: str) -> bool:
    """
    Determine if a lab result should be kept based on filtering rules.

    Args:
        test_name: The normalized test name (uppercase)
        lab_line: The full lab line

    Returns:
        True if the lab should be kept, False otherwise
    """
    # Sanity check: filter out impossible lab values
    if not _is_reasonable_lab_value(test_name, lab_line):
        return False

    # Always keep abnormal results (marked with H or L)
    if re.search(r'\d+\.?\d*\s*[HL]\b', lab_line):
        return True

    # Always keep special hormones and tumor markers
    for always_test in ALWAYS_REPORT:
        if always_test in test_name:
            return True

    # Check if it's a CBC component
    if any(cbc_test in test_name for cbc_test in CBC_KEEP):
        return True

    # Check if it's a BMP component
    if any(bmp_test in test_name for bmp_test in BMP_KEEP):
        return True

    # Check if it's a UA component
    if any(ua_test in test_name for ua_test in UA_KEEP):
        return True

    # Default: don't keep (will be filtered out)
    return False


def _is_reasonable_lab_value(test_name: str, lab_line: str) -> bool:
    """
    Check if lab value is within reasonable physiological ranges.
    Filters out corrupted/impossible data.

    Args:
        test_name: The normalized test name (uppercase)
        lab_line: The full lab line

    Returns:
        True if value is reasonable, False if impossible
    """
    # Extract numeric value from lab line
    value_match = re.search(r'\b(\d+\.?\d*)\s*[HL]?\s*(?:mg/dL|g/dL|10\.\w+/uL|mEq/L|mmol/L|ng/mL|%)', lab_line)
    if not value_match:
        return True  # Can't extract value, assume OK

    try:
        value = float(value_match.group(1))
    except ValueError:
        return True  # Can't parse, assume OK

    # Define reasonable ranges for common labs (not strict medical limits, just sanity checks)
    # These are very permissive to avoid false filtering
    sanity_ranges = {
        'CREATININE': (0.1, 20.0),  # Normal 0.5-1.5, max ~15 in severe renal failure
        'CREAT': (0.1, 20.0),
        'BUN': (1.0, 200.0),  # Normal 7-20, can be very high in renal failure
        'UREA NITROGEN': (1.0, 200.0),
        'GLUCOSE': (20.0, 1000.0),  # Normal 70-100, can be very high in DM crisis
        'GLU': (20.0, 1000.0),
        'HEMOGLOBIN': (3.0, 25.0),  # Normal 13-17, can be very low in anemia
        'HGB': (3.0, 25.0),
        'HEMATOCRIT': (10.0, 70.0),  # Normal 40-50%, expressed as percentage
        'HCT': (10.0, 70.0),
        'WBC': (0.5, 100.0),  # Normal 4-10, can be high in infection/leukemia
        'SODIUM': (100.0, 200.0),  # Normal 135-145 mEq/L
        'NA': (100.0, 200.0),
        'POTASSIUM': (1.0, 10.0),  # Normal 3.5-5.0 mEq/L
        'K': (1.0, 10.0),
        'PSA': (0.0, 1000.0),  # Normal <4, can be very high in prostate cancer
    }

    # Check if test name matches any sanity range
    for test_key, (min_val, max_val) in sanity_ranges.items():
        if test_key in test_name:
            if not (min_val <= value <= max_val):
                # Value is outside reasonable range - likely corrupted data
                return False

    return True  # Value is reasonable or test not in sanity check list


def extract_labs(clinical_document: str) -> str:
    """
    Extract general lab results from clinical documents.

    Extracts lab values with collection dates while filtering VA administrative metadata.
    Supports both VA format and human-readable format.

    Args:
        clinical_document: Full clinical document

    Returns:
        Clean lab results with dates, or "" if not found
    """
    lab_lines = []

    # First, try to extract human-readable format (priority)
    # Pattern 1: "DATE: LAB VALUES" format
    # Example: "9/4/25: PSA 7.46 ng/mL (H), Free PSA 1.31 ng/mL, Free PSA percentage 17.57%"
    human_readable_labs = extract_human_readable_labs(clinical_document)
    if human_readable_labs:
        lab_lines.extend(human_readable_labs)

    # Second, extract VA format (traditional)
    va_format_labs = extract_va_format_labs(clinical_document)
    if va_format_labs:
        lab_lines.extend(va_format_labs)

    if not lab_lines:
        return ""

    # Remove duplicates while preserving order
    seen = set()
    unique_labs = []
    for line in lab_lines:
        # Create a normalized key for deduplication
        normalized = line.lower().strip()
        if normalized not in seen:
            seen.add(normalized)

            # Filter out non-lab lines (medications, patient IDs, etc.)
            if _is_valid_lab_line(line):
                unique_labs.append(line)

    return '\n'.join(unique_labs) if unique_labs else ""


def _is_valid_lab_line(line: str) -> bool:
    """
    Check if a line is a valid lab result (not medication, patient ID, etc.).

    Args:
        line: The line to check

    Returns:
        True if valid lab line, False otherwise
    """
    line_upper = line.upper().strip()

    # Filter out medication names (end with dosage forms)
    medication_endings = [
        'TAB', 'CAP', 'CAPSULE', 'TABLET', 'MG TAB', 'MG CAP',
        'OINT', 'CREAM', 'GEL', 'PATCH', 'SOLUTION', 'SYRUP',
        'INJ', 'INJECTION', 'SUSP', 'SUSPENSION'
    ]
    for ending in medication_endings:
        if line_upper.endswith(ending):
            return False

    # Filter out patient identifiers (SSN patterns, Age/Sex info)
    if re.search(r'\d{3}-\d{2}-\d{4}', line):  # SSN pattern
        return False
    if re.search(r'Age:\d+\s+Sex:(MALE|FEMALE)', line, re.IGNORECASE):
        return False
    if re.match(r'^[A-Z]+,[A-Z\s]+\s+\d{3}-\d{2}-\d{4}', line):  # Name with SSN
        return False

    # Valid lab lines typically contain numbers and units
    has_number = re.search(r'\d+\.?\d*', line)

    # REMOVED: Overly aggressive date requirement
    # The extraction functions (extract_human_readable_labs, extract_va_format_labs)
    # already handle date formatting and attach dates to lab results.
    # Requiring a date here was filtering out all labs because the date pattern
    # didn't match the various date formats returned by extraction functions.

    # If no number, it's probably not a lab result
    if not has_number:
        return False

    return True


def extract_human_readable_labs(clinical_document: str) -> list:
    """
    Extract human-readable lab format.

    Patterns:
    - "DATE: LAB VALUES" (traditional)
    - "Panel name (DATE): LAB VALUES" (traditional)
    - "LAB: value units (ref: range) - DATE" (VA reverse format)

    Examples:
    - "9/4/25: PSA 7.46 ng/mL (H), Free PSA 1.31 ng/mL"
    - "Lipid panel (9/4/25): Total cholesterol 179 mg/dL, Triglycerides 195 mg/dL"
    - "Hemoglobin A1c: 8.3% (ref: 4.0-6.0) - Aug 19, 2025" (VA format)

    Returns:
        List of lab result strings with dates
    """
    lab_results = []

    # Look for the LABS section marker
    labs_section_match = re.search(
        r'={30,}\s*LABS\s*={30,}(.*?)(?:={30,}|$)',
        clinical_document,
        re.DOTALL | re.IGNORECASE
    )

    if not labs_section_match:
        return lab_results

    labs_content = labs_section_match.group(1).strip()

    # Define endocrine markers to EXCLUDE from general LABS (they go in ENDOCRINE section)
    endocrine_markers = ['A1C', 'HBA1C', 'HEMOGLOBIN A1C', 'TSH', 'VITAMIN D', 'VITAMIN B12',
                        'TESTOSTERONE', 'ESTROGEN', 'LH', 'FSH', 'PROLACTIN', 'AFP', 'HCG', 'LDH']

    # FIRST: Extract VA reverse format "TEST: value - DATE"
    # Pattern: "TEST_NAME: value units (ref: range) - DATE"
    # Example: "Hemoglobin A1c: 8.3% (ref: 4.0-6.0) - Aug 19, 2025"
    va_reverse_pattern = r'^(.+?):\s*(.+?)\s+-\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})$'

    for line in labs_content.split('\n'):
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith('Lipids:') or line_stripped.startswith('-'):
            continue

        match = re.match(va_reverse_pattern, line_stripped, re.MULTILINE)
        if match:
            test_name = match.group(1).strip()
            value_ref = match.group(2).strip()
            date = match.group(3).strip()

            # Skip endocrine markers - they go in ENDOCRINE section
            test_name_upper = test_name.upper()
            if any(marker in test_name_upper for marker in endocrine_markers):
                continue

            # Apply filtering logic
            full_line = f"{test_name}: {value_ref}"

            if should_keep_lab(test_name_upper, full_line):
                lab_results.append(f"{test_name}: {value_ref} - {date}")

    # Handle Lipids sub-section with bullets
    lipids_match = re.search(r'Lipids:\s*\n((?:\s*-\s*[^\n]+\n?)+)', labs_content, re.MULTILINE)
    if lipids_match:
        lipids_text = lipids_match.group(1)
        for lipid_line in lipids_text.split('\n'):
            lipid_line = lipid_line.strip()
            if lipid_line.startswith('- '):
                # Remove bullet and parse
                lipid_line = lipid_line[2:].strip()
                match = re.match(va_reverse_pattern, lipid_line)
                if match:
                    test_name = match.group(1).strip()
                    value_ref = match.group(2).strip()
                    date = match.group(3).strip()

                    # Apply filtering logic - only keep abnormal lipids
                    test_name_upper = test_name.upper()
                    full_line = f"{test_name}: {value_ref}"

                    if should_keep_lab(test_name_upper, full_line):
                        lab_results.append(f"{test_name}: {value_ref} - {date}")

    # Pattern 1: Date-prefixed format "M/D/YY: LAB VALUES"
    # Matches: "9/4/25: PSA 7.46 ng/mL (H), Free PSA 1.31 ng/mL, Free PSA percentage 17.57%"
    date_prefix_pattern = r'(\d{1,2}/\d{1,2}/\d{2,4}):\s*([^\n]+(?:\n(?!\d{1,2}/\d{1,2}/|[A-Z][a-z]+ panel|Urinalysis)[^\n]+)*)'

    for match in re.finditer(date_prefix_pattern, labs_content):
        date = match.group(1)
        values = match.group(2).strip()

        # Clean up line breaks and excessive whitespace
        values = re.sub(r'\s+', ' ', values)

        # Skip if this is just PSA (already extracted by PSA extractor)
        if re.match(r'^PSA\s+[\d.]+', values, re.IGNORECASE):
            # Check if there's more than just PSA
            if not re.search(r',\s*(?!PSA)', values, re.IGNORECASE):
                continue

        lab_results.append(f"{date}: {values}")

    # Pattern 2: Panel format "Panel name (DATE): VALUES"
    # Matches: "Lipid panel (9/4/25): Total cholesterol 179 mg/dL, Triglycerides 195 mg/dL"
    panel_pattern = r'([A-Z][a-z]+(?:\s+[a-z]+)*)\s*\((\d{1,2}/\d{1,2}/\d{2,4})\):\s*([^\n]+(?:\n(?!\d{1,2}/\d{1,2}/|[A-Z][a-z]+ panel|Urinalysis)[^\n]+)*)'

    for match in re.finditer(panel_pattern, labs_content):
        panel_name = match.group(1)
        date = match.group(2)
        values = match.group(3).strip()

        # Clean up line breaks and excessive whitespace
        values = re.sub(r'\s+', ' ', values)

        lab_results.append(f"{panel_name} ({date}): {values}")

    # Pattern 3: Urinalysis format "Urinalysis (DATE): VALUES"
    urinalysis_pattern = r'(Urinalysis)\s*\((\d{1,2}/\d{1,2}/\d{2,4})\):\s*([^\n]+(?:\n(?!\d{1,2}/\d{1,2}/|[A-Z][a-z]+ panel|Urinalysis)[^\n]+)*)'

    for match in re.finditer(urinalysis_pattern, labs_content, re.IGNORECASE):
        test_name = match.group(1)
        date = match.group(2)
        values = match.group(3).strip()

        # Clean up line breaks and excessive whitespace
        values = re.sub(r'\s+', ' ', values)

        lab_results.append(f"{test_name} ({date}): {values}")

    return lab_results


def extract_va_format_labs(clinical_document: str) -> list:
    """
    Extract VA-formatted lab results (traditional format).

    Pattern: lines like "TEST_NAME    VALUE  units  range"
    Between "Test name" header and next major section.

    Returns:
        List of lab result strings
    """
    lab_lines = []
    current_collection_date = None

    # Comprehensive VA metadata patterns to filter
    va_metadata_patterns = [
        r'^Reporting Lab:.*$',
        r'^\s*\d{5,}.*$',  # Long numbers (CLIA numbers, etc.)
        r'^.*CLIA#.*$',
        r'^\s*7400 MERTON MINTER.*$',  # Address lines
        r'^\s*SAN ANTONIO.*$',
        r'^Report Released Date/Time:.*$',
        r'^Provider:.*$',
        r'^Specimen:.*$',
        r'^\s*Specimen Collection Date:.*$',
        r'^\s*Collection sample:.*$',
        r'^\s*Collection date:.*$',
        r'^\s*Collection time:.*$',
        r'^\s*Site/Specimen:.*$',
        r'^\s*Accession.*$',
        r'^\s*Received:.*$',
        r'^\s*Test name\s+Result\s+units.*$',  # Header lines
        r'^\s*-+\s+-+\s+-+.*$',  # Separator lines
        r'^\s*Comment:.*$',
        r'^\s*Eval:.*$',  # Evaluation commentary
        r'^\s*For Glucose.*$',
        r'^\s*\*.*$',  # Lines starting with asterisks
        r'^={50,}$',  # Long separator lines
        r'^\+{50,}$',  # Plus sign separators
        r'^\s*Test\(s\) ordered:.*$',
        r'^\s*Ordered by:.*$',
        r'^\s*Location:.*$',
    ]

    for line in clinical_document.split('\n'):
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            continue

        # Check for collection date and extract it
        # Pattern 1: "Specimen Collection Date: May 02, 2024@10:29"
        date_match = re.search(r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', line)
        if date_match:
            current_collection_date = date_match.group(1)
            continue

        # Pattern 2: "Collection date: Aug 15, 2022 09:58"
        date_match = re.search(r'Collection date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', line)
        if date_match:
            current_collection_date = date_match.group(1)
            continue

        # Check if line is VA metadata
        is_metadata = False
        for pattern in va_metadata_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                is_metadata = True
                break

        if is_metadata:
            continue

        # Look for actual lab values
        # Pattern: TEST_NAME  VALUE  units  range
        # Examples:
        # GLUCOSE                         113H  mg/dL            70 - 105
        # WBC                             6.7   10.e3/uL   4.0 - 10.0
        if re.search(r'^\s*[A-Z][A-Z\s,\-\(\)]+\s+(?:\d+\.?\d*\s*[HL]?|Negative|NEGATIVE|Positive|POSITIVE|Normal|NORMAL)', line):
            # Clean up excessive spacing
            cleaned = re.sub(r'\s{2,}', '  ', line.strip())

            # Extract test name for filtering - try multiple patterns
            test_name = None

            # Pattern 1: TEST_NAME followed by 2+ spaces
            test_name_match = re.match(r'^\s*([A-Z][A-Z\s,\-\(\)]+?)\s{2,}', cleaned)
            if test_name_match:
                test_name = test_name_match.group(1).strip().upper()
            else:
                # Pattern 2: TEST_NAME followed by single space and value
                test_name_match = re.match(r'^\s*([A-Z][A-Z\s,\-\(\)]+?)\s+\d', cleaned)
                if test_name_match:
                    test_name = test_name_match.group(1).strip().upper()

            # Only keep if we extracted a test name AND it passes filtering
            if test_name and should_keep_lab(test_name, cleaned):
                # Append collection date if available
                if current_collection_date:
                    lab_with_date = f"{cleaned} ({current_collection_date})"
                    lab_lines.append(lab_with_date)
                else:
                    lab_lines.append(cleaned)

    return lab_lines


def extract_stone_labs(clinical_document: str) -> str:
    """
    Extract stone-specific laboratory results.

    Stone evaluation requires:
    - BUN (Blood Urea Nitrogen)
    - Creatinine
    - eGFR (estimated Glomerular Filtration Rate)
    - Calcium (serum)
    - Urinalysis (pH, specific gravity, blood, protein)

    Args:
        clinical_document: Full clinical document

    Returns:
        Formatted stone labs, or "" if not found
    """
    stone_labs = {}

    # Target tests for stone workup
    # Note: \d*\.?\d+ pattern allows for numbers like .7 (no leading zero)
    target_tests = {
        'BUN': r'(?:BUN|UREA NITROGEN)\s+(\d+\.?\d*)\s*([HL])?\s*mg/dL\s+(?:Ref:\s*)?(\d*\.?\d+\s*-\s*\d*\.?\d+)',
        'CREATININE': r'CREATININE\s+(\d+\.?\d*)\s*([HL])?\s*mg/dL\s+(?:Ref:\s*)?(\d*\.?\d+\s*-\s*\d*\.?\d+)',
        'EGFR': r'EGFR\s+(?:CKD\s+EPI\s+)?(\d+)\s*([HL])?\s*(?:\[|mL/min)?',
        'CALCIUM': r'CALCIUM\s+(\d+\.?\d*)\s*([HL])?\s*mg/dL\s+(?:Ref:\s*)?(\d*\.?\d+\s*-\s*\d*\.?\d+)',
        'GLUCOSE': r'GLUCOSE\s+(\d+\.?\d*)\s*([HL])?\s*mg/dL\s+(?:Ref:\s*)?(\d*\.?\d+\s*-\s*\d*\.?\d+)'
    }

    # Extract collection date for context
    date_match = re.search(r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', clinical_document)
    collection_date = date_match.group(1) if date_match else None

    # Extract targeted tests
    for test_name, pattern in target_tests.items():
        matches = list(re.finditer(pattern, clinical_document, re.IGNORECASE))
        if matches:
            # Use most recent (last occurrence is typically most recent in VA format)
            match = matches[-1]
            value = match.group(1)
            flag = match.group(2) if len(match.groups()) > 1 and match.group(2) else ''
            ref_range = match.group(3) if len(match.groups()) > 2 and match.group(3) else ''

            stone_labs[test_name] = {
                'value': value,
                'flag': flag,
                'range': ref_range
            }

    # Extract urinalysis components
    ua_pattern = r'(?:Urinalysis|UA)[:\s]+([^\n]+(?:\n(?!\w+:)[^\n]+)*)'
    ua_match = re.search(ua_pattern, clinical_document, re.IGNORECASE)
    if ua_match:
        ua_text = ua_match.group(1)
        # Extract pH
        ph_match = re.search(r'(?:pH|PH)\s*[:\s]+(\d+\.?\d*)', ua_text, re.IGNORECASE)
        if ph_match:
            stone_labs['UA_PH'] = {'value': ph_match.group(1), 'flag': '', 'range': ''}

        # Extract specific gravity
        sg_match = re.search(r'(?:SG|specific gravity|SPECIFIC GRAVITY)\s*[:\s]+(\d+\.?\d*)', ua_text, re.IGNORECASE)
        if sg_match:
            stone_labs['UA_SG'] = {'value': sg_match.group(1), 'flag': '', 'range': ''}

    if not stone_labs:
        return ""

    # Format output
    lines = []
    if collection_date:
        lines.append(f"STONE LABS ({collection_date}):")
    else:
        lines.append("STONE LABS:")

    # Format renal function tests first
    if 'BUN' in stone_labs:
        lab = stone_labs['BUN']
        lines.append(f"BUN: {lab['value']}{' ' + lab['flag'] if lab['flag'] else ''} mg/dL (Ref: {lab['range']})")

    if 'CREATININE' in stone_labs:
        lab = stone_labs['CREATININE']
        lines.append(f"Creatinine: {lab['value']}{' ' + lab['flag'] if lab['flag'] else ''} mg/dL (Ref: {lab['range']})")

    if 'EGFR' in stone_labs:
        lab = stone_labs['EGFR']
        egfr_value = int(lab['value'])
        # Interpret CKD stage
        if egfr_value >= 90:
            stage = "G1 - Normal"
        elif egfr_value >= 60:
            stage = "G2 - Mild decrease"
        elif egfr_value >= 45:
            stage = "G3a - Mild-moderate decrease"
        elif egfr_value >= 30:
            stage = "G3b - Moderate-severe decrease"
        elif egfr_value >= 15:
            stage = "G4 - Severe decrease"
        else:
            stage = "G5 - Kidney failure"

        lines.append(f"eGFR: {lab['value']} mL/min/1.73m² (CKD stage {stage})")

    # Then metabolic tests
    if 'CALCIUM' in stone_labs:
        lab = stone_labs['CALCIUM']
        lines.append(f"Calcium: {lab['value']}{' ' + lab['flag'] if lab['flag'] else ''} mg/dL (Ref: {lab['range']})")

    if 'GLUCOSE' in stone_labs:
        lab = stone_labs['GLUCOSE']
        lines.append(f"Glucose: {lab['value']}{' ' + lab['flag'] if lab['flag'] else ''} mg/dL (Ref: {lab['range']})")

    # Then urinalysis
    if 'UA_PH' in stone_labs:
        lines.append(f"Urinalysis pH: {stone_labs['UA_PH']['value']}")

    if 'UA_SG' in stone_labs:
        lines.append(f"Urinalysis Specific Gravity: {stone_labs['UA_SG']['value']}")

    return '\n'.join(lines)


def extract_calcium_series(clinical_document: str) -> str:
    """
    Extract chronological series of calcium values.

    Important for stone workup to track trends.

    Args:
        clinical_document: Full clinical document

    Returns:
        Formatted calcium series in chronological order
    """
    calcium_values = []

    # Pattern: Look for all calcium measurements with dates
    # VA format: each specimen has a collection date followed by test results
    # Format: "Specimen Collection Date: May 05, 2025@15:50"
    #         "  Test name                Result    units      Ref.   range   Site Code"
    #         "CALCIUM                         9.6     mg/dL      8.6 - 10.3       [671]"
    calcium_pattern = r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4}(?:@\d{2}:\d{2})?).*?CALCIUM\s+(\d+\.?\d*)\s*([HL])?\s*mg/d[Ll]\s+(\d+\.?\d*\s*-\s*\d+\.?\d*)'

    for match in re.finditer(calcium_pattern, clinical_document, re.DOTALL | re.IGNORECASE):
        date_str = match.group(1)
        value = match.group(2)
        flag = match.group(3) if match.group(3) else ''
        ref_range = match.group(4)

        calcium_values.append({
            'date': date_str,
            'value': value,
            'flag': flag,
            'range': ref_range
        })

    if not calcium_values:
        return ""

    # Sort by date (most recent first) - would need datetime parsing for accuracy
    # For now, keep in order found (typically chronological in VA format)

    lines = ["CALCIUM:"]
    for ca in calcium_values:
        lines.append(f"{ca['date']}: Calcium {ca['value']}{' ' + ca['flag'] if ca['flag'] else ''} mg/dL (Ref: {ca['range']})")

    return '\n'.join(lines)
