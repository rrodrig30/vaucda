"""
Stone-Related Labs Extractor

Extracts labs related to kidney stone evaluation:
- 24-hour urine tests
- Comprehensive Metabolic Panel (CMP)
- Parathyroid Hormone (PTH)
"""

import re


def extract_stone_labs(clinical_document: str) -> str:
    """
    Extract stone-related lab results from clinical documents with collection dates.

    Target labs:
    - PTH (Parathyroid Hormone)
    - Calcium
    - Uric Acid
    - Phosphorus / Phosphate
    - Alkaline Phosphatase
    - 24-hour urine (calcium, oxalate, citrate, uric acid, volume, etc.)
    - Stone Composition (if available)

    Args:
        clinical_document: Full clinical document

    Returns:
        Extracted stone-related lab results with dates, or "" if not found
    """
    stone_results = []

    # First, look for STONE LABS section with date-prefixed or VA reverse format
    stone_section_match = re.search(
        r'====+\s*STONE\s+LABS\s*====+\s*\n(.*?)(?====+|$)',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    if stone_section_match:
        stone_section = stone_section_match.group(1)

        # Parse VA reverse format: "LAB: value - DATE"
        for line in stone_section.split('\n'):
            line = line.strip()
            if not line:
                continue

            # Try VA reverse format: "PTH: 45 pg/mL (ref: 10-65) - Aug 19, 2025"
            va_reverse_match = re.match(r'^([A-Z][A-Za-z0-9\s/\(\),\-]+?):\s*([^-\n]+?)\s+-\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})$', line)
            if va_reverse_match:
                test_name = va_reverse_match.group(1).strip()
                value_ref = va_reverse_match.group(2).strip()
                date_str = va_reverse_match.group(3).strip()
                stone_results.append(f"{test_name}: {value_ref} - {date_str}")

    # Extract from general LABS section using VA reverse format
    general_labs_section_match = re.search(
        r'====+\s*LABS\s*====+\s*\n(.*?)(?====+|$)',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    if general_labs_section_match:
        general_labs_section = general_labs_section_match.group(1)

        # Define stone markers to extract
        stone_markers = ['PTH', 'PARATHYROID', 'CALCIUM', 'URIC ACID',
                        'PHOSPHORUS', 'PHOSPHATE', 'ALKALINE PHOSPHATASE']

        # Parse lines with VA reverse format
        for line in general_labs_section.split('\n'):
            line = line.strip()
            if not line or line.startswith('Lipids:') or line.startswith('-'):
                continue

            # Try VA reverse format: "Calcium: 9.7 mg/dL (ref: 8.6-10.3) - Aug 19, 2025"
            va_reverse_match = re.match(r'^([A-Z][A-Za-z0-9\s/\(\),\-]+?):\s*([^-\n]+?)\s+-\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})$', line)
            if va_reverse_match:
                test_name = va_reverse_match.group(1).strip()
                value_ref = va_reverse_match.group(2).strip()
                date_str = va_reverse_match.group(3).strip()

                # Check if this is a stone marker
                test_name_upper = test_name.upper()
                if any(marker in test_name_upper for marker in stone_markers):
                    # Avoid duplicate if already in stone_results
                    result_str = f"{test_name}: {value_ref} - {date_str}"
                    if result_str not in stone_results:
                        stone_results.append(result_str)

    # Legacy extraction support for non-VA format documents
    current_collection_date = None

    # Track collection dates as we parse through document
    for line in clinical_document.split('\n'):
        # Check for collection date headers
        date_match = re.search(r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', line)
        if not date_match:
            date_match = re.search(r'Collection date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', line)

        if date_match:
            current_collection_date = date_match.group(1)

    # Pattern 1: 24-hour urine section
    urine_24h_match = re.search(
        r'24[- ]hour\s+[Uu]rine[:\s]*(.*?)(?=\n\s*(?:CMP|Comprehensive|PTH|ASSESSMENT:|PLAN:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    if urine_24h_match:
        urine_results = urine_24h_match.group(1).strip()
        # Clean up
        urine_results = re.sub(r' +', ' ', urine_results)
        urine_results = re.sub(r'\n{3,}', '\n', urine_results)
        header = "24-Hour Urine"
        if current_collection_date:
            header += f" ({current_collection_date})"
        stone_results.append(f"{header}:\n{urine_results}")

    # Pattern 2: CMP section
    cmp_match = re.search(
        r'(?:CMP|Comprehensive\s+Metabolic\s+Panel)[:\s]*(.*?)(?=\n\s*(?:PTH|ASSESSMENT:|PLAN:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)',
        clinical_document,
        re.IGNORECASE | re.DOTALL
    )

    if cmp_match:
        cmp_results = cmp_match.group(1).strip()
        # Clean up
        cmp_results = re.sub(r' +', ' ', cmp_results)
        cmp_results = re.sub(r'\n{3,}', '\n', cmp_results)
        header = "Comprehensive Metabolic Panel"
        if current_collection_date:
            header += f" ({current_collection_date})"
        stone_results.append(f"{header}:\n{cmp_results}")

    # Pattern 3: PTH
    pth_pattern = r'(?:PTH|Parathyroid\s+Hormone)[:\s]+(\d+\.?\d*)\s*(pg/mL|pg/ml)?(?:\s*\(?([A-Za-z]{3}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})\)?)?'

    for match in re.finditer(pth_pattern, clinical_document, re.IGNORECASE):
        value = match.group(1).strip()
        unit = match.group(2).strip() if match.group(2) else "pg/mL"
        inline_date = match.group(3).strip() if match.group(3) else ""

        # Use inline date if present, otherwise use tracked collection date
        date = inline_date if inline_date else current_collection_date

        result_str = f"PTH: {value} {unit}"
        if date:
            result_str += f" ({date})"

        stone_results.append(result_str)

    if not stone_results:
        return ""

    return '\n\n'.join(stone_results)
