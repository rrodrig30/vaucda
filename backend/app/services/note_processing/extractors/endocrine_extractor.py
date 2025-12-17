"""
Endocrine Labs Extractor

Extracts endocrine-related lab results (testosterone, estrogens, LH, FSH, A1C, etc.).
"""

import re


def extract_endocrine_labs(clinical_document: str) -> str:
    """
    Extract endocrine lab results from clinical documents with collection dates.

    Target labs:
    - Total Testosterone
    - % Free Testosterone
    - Total Estrogens
    - LH (Luteinizing Hormone)
    - FSH (Follicle-Stimulating Hormone)
    - A1C (Hemoglobin A1C)
    - Prolactin
    - Epinephrine
    - Norepinephrine
    - Metanephrines
    - Cortisol
    - Aldosterone
    - Glucose
    - C-peptide
    - GAD65AB (Glutamic Acid Decarboxylase Antibody)
    - Alpha Fetoprotein (AFP)
    - HCG (Human Chorionic Gonadotropin)
    - LDH (Lactate Dehydrogenase)

    Args:
        clinical_document: Full clinical document

    Returns:
        Extracted endocrine lab results with dates, or "" if not found
    """
    endocrine_results = []

    # First, look for ENDOCRINE LABS section with date-prefixed format
    # Format: "9/4/25: A1c 8.7% (H)"
    endocrine_section_match = re.search(
        r'====+\s*ENDOCRINE\s+LABS\s*====+\s*\n(.*?)(?====+|$)',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    # ALSO look in general LABS section for endocrine markers (A1C, TSH, Vitamin D, etc.)
    # These often get placed in LABS section instead of ENDOCRINE LABS section
    general_labs_section_match = re.search(
        r'====+\s*LABS\s*====+\s*\n(.*?)(?====+|$)',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    if endocrine_section_match:
        endocrine_section = endocrine_section_match.group(1)

        # Parse lines with BOTH formats:
        # Format 1 (traditional): "DATE: LABS"
        # Format 2 (VA reverse): "LAB: value - DATE"
        for line in endocrine_section.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Try VA reverse format first: "TSH: 2.57 uIU/ml (ref: 0.45-5.33) - Aug 19, 2025"
            va_reverse_match = re.match(r'^([A-Z][A-Za-z0-9\s/\(\),\-]+?):\s*([^-\n]+?)\s+-\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})$', line)
            if va_reverse_match:
                test_name = va_reverse_match.group(1).strip()
                value_ref = va_reverse_match.group(2).strip()
                date_str = va_reverse_match.group(3).strip()
                endocrine_results.append(f"{test_name}: {value_ref} - {date_str}")
                continue

            # Try traditional date prefix format: "9/4/25:" or "6/3/25:"
            date_match = re.match(r'(\d{1,2}/\d{1,2}/\d{2,4}):\s*(.*)', line)
            if date_match:
                date_str = date_match.group(1)
                labs_str = date_match.group(2)

                # Parse all labs on this line separated by commas
                _extract_endocrine_values_from_line(labs_str, date_str, endocrine_results)

    # Process general LABS section for endocrine markers (A1C, TSH, Vitamin D, etc.)
    if general_labs_section_match:
        general_labs_section = general_labs_section_match.group(1)

        # Parse lines with VA reverse format: "LAB: value - DATE"
        for line in general_labs_section.split('\n'):
            line = line.strip()
            if not line or line.startswith('Lipids:') or line.startswith('-'):
                continue

            # Try VA reverse format: "Hemoglobin A1c: 8.3% (ref: 4.0-6.0) - Aug 19, 2025"
            va_reverse_match = re.match(r'^([A-Z][A-Za-z0-9\s/\(\),\-]+?):\s*([^-\n]+?)\s+-\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})$', line)
            if va_reverse_match:
                test_name = va_reverse_match.group(1).strip()
                value_ref = va_reverse_match.group(2).strip()
                date_str = va_reverse_match.group(3).strip()

                # Check if this is an endocrine marker
                test_name_upper = test_name.upper()
                endocrine_markers = ['A1C', 'HBA1C', 'HEMOGLOBIN A1C', 'TSH', 'VITAMIN D', 'VITAMIN B12',
                                    'TESTOSTERONE', 'ESTROGEN', 'LH', 'FSH', 'PROLACTIN', 'AFP', 'HCG', 'LDH']

                if any(marker in test_name_upper for marker in endocrine_markers):
                    endocrine_results.append(f"{test_name}: {value_ref} - {date_str}")

    # Also check for standard VA format with "Specimen Collection Date:" or date in header
    current_collection_date = None
    for line in clinical_document.split('\n'):
        # Check for collection date headers
        date_match = re.search(r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', line)
        if not date_match:
            date_match = re.search(r'Collection date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', line)
        # Also check for VA lab report header format: "your Oct 30 2025 test results"
        if not date_match:
            date_match = re.search(r'your\s+([A-Za-z]{3}\s+\d{1,2}\s+\d{4})\s+test results', line)

        if date_match:
            current_collection_date = date_match.group(1)

        # Look for endocrine labs on this line with the current date
        if current_collection_date:
            _extract_endocrine_values_from_line(line, current_collection_date, endocrine_results)

    if not endocrine_results:
        return ""

    return '\n'.join(endocrine_results)


def _extract_endocrine_values_from_line(line: str, date: str, results_list: list):
    """
    Extract endocrine lab values from a single line with a known date.

    Args:
        line: Line containing lab results
        date: Date string to associate with results
        results_list: List to append results to (modified in place)
    """
    # Define patterns for each endocrine test
    test_patterns = [
        (r'(?:Total\s+Testosterone|TESTOSTERONE,?\s+SERUM\s+TOTA?L?)', r'ng/dL|ng/dl'),
        (r'(?:Free\s+Testosterone|FREE\s+TESTOSTERONE,?\s+SERUM)', r'pg/mL|pg/ml'),
        (r'(?:%\s*Free\s+Testosterone|%\s*FREE\s+TESTOSTERONE)', r'%'),
        (r'Total\s+Estrogen(?:s)?', r'pg/mL|pg/ml'),
        (r'(?:LH|Luteinizing\s+Hormone)', r'mIU/mL|mIU/ml|IU/L'),
        (r'(?:FSH|Follicle[- ]?Stimulating\s+Hormone)', r'mIU/mL|mIU/ml|IU/L'),
        (r'(?:A1[Cc]|Hemoglobin\s+A1[Cc]|HbA1[Cc])', r'%'),
        (r'Prolactin', r'ng/mL|ng/ml'),
        (r'Epinephrine', r'pg/mL|pg/ml|ng/L'),
        (r'Norepinephrine', r'pg/mL|pg/ml|ng/L'),
        (r'Metanephrines?', r'pg/mL|pg/ml|mcg/24h|μg/24h'),
        (r'Cortisol', r'mcg/dL|mcg/dl|μg/dL|ug/dL'),
        (r'Aldosterone', r'ng/dL|ng/dl'),
        (r'Glucose', r'mg/dL|mg/dl'),
        (r'C[- ]?peptide', r'ng/mL|ng/ml'),
        (r'GAD\s*65\s*AB|GAD65\s*Antibody|Glutamic\s+Acid\s+Decarboxylase', r'U/mL|U/ml'),
        (r'(?:AFP|Alpha[- ]?Fetoprotein)', r'ng/mL|ng/ml'),
        (r'(?:HCG|Human\s+Chorionic\s+Gonadotropin)', r'mIU/mL|mIU/ml'),
        (r'(?:LDH|Lactate\s+Dehydrogenase)', r'U/L|IU/L'),
    ]

    for test_name_pattern, unit_pattern in test_patterns:
        # Pattern: Test name + whitespace + value + optional H/L + optional unit
        # Updated to handle VA format with lots of whitespace
        full_pattern = rf'({test_name_pattern})[:\s,]+(\d+\.?\d*)\s*([HL])?\s*({unit_pattern})?'

        for match in re.finditer(full_pattern, line, re.IGNORECASE):
            test_name = match.group(1).strip()
            value = match.group(2).strip()
            hl_marker_char = match.group(3).strip() if match.group(3) else ""
            unit = match.group(4).strip() if match.group(4) else ""

            # Normalize test name for VA format
            if 'TESTOSTERONE' in test_name.upper() and 'SERUM' in test_name.upper():
                if 'FREE' in test_name.upper():
                    test_name = "Free Testosterone, Serum"
                elif '%' in test_name:
                    test_name = "% Free Testosterone"
                else:
                    test_name = "Total Testosterone, Serum"

            # Format result
            result_str = f"{date}: {test_name} {value}"
            if unit:
                result_str += f" {unit}"
            if hl_marker_char:
                result_str += f" ({hl_marker_char})"

            results_list.append(result_str)
