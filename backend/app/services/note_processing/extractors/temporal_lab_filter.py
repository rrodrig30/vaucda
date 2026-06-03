"""
Temporal Lab Filter

Applies date-based filtering to lab results:
- Routine labs (BMP, CBC, UA): 6 months
- Cultures: 2 years
- Abnormal results: Always keep regardless of age
- Endocrine labs: Always keep regardless of age

Author: VAUCDA Development Team
Date: February 2026
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Set
import logging

logger = logging.getLogger(__name__)


# Temporal windows for different lab types
ROUTINE_LAB_WINDOW_MONTHS = 6
CULTURE_WINDOW_MONTHS = 24
ABNORMAL_LAB_WINDOW_MONTHS = 12  # Keep abnormals longer

# Expanded lab categories
CBC_COMPONENTS = {
    'WBC', 'WHITE BLOOD', 'WHITE CELL',
    'RBC', 'RED BLOOD', 'RED CELL',
    'HEMOGLOBIN', 'HGB', 'HB',
    'HEMATOCRIT', 'HCT',
    'PLATELET', 'PLATELETS', 'PLT',
    'MCV', 'MEAN CORPUSCULAR VOLUME',
    'MCH', 'MEAN CORPUSCULAR HEMOGLOBIN',
    'MCHC',
    'RDW', 'RED CELL DISTRIBUTION',
    'MPV', 'MEAN PLATELET VOLUME',
}

BMP_COMPONENTS = {
    'SODIUM', 'NA',
    'POTASSIUM', 'K',
    'CHLORIDE', 'CL',
    'CO2', 'BICARBONATE', 'HCO3', 'CARBON DIOXIDE',
    'BUN', 'BLOOD UREA', 'UREA NITROGEN',
    'CREATININE', 'CREAT', 'CR',
    'GLUCOSE', 'GLU', 'BLOOD SUGAR',
    'CALCIUM', 'CA',
    'EGFR', 'GFR', 'GLOMERULAR FILTRATION',
    'ANION GAP',
}

CMP_ADDITIONAL = {  # Additional for comprehensive metabolic panel
    'ALBUMIN', 'ALB',
    'TOTAL PROTEIN', 'PROTEIN TOTAL',
    'BILIRUBIN', 'BILI',
    'ALT', 'ALANINE AMINOTRANSFERASE', 'SGPT',
    'AST', 'ASPARTATE AMINOTRANSFERASE', 'SGOT',
    'ALKALINE PHOSPHATASE', 'ALP', 'ALK PHOS',
}

UA_COMPONENTS = {
    'URINALYSIS', 'UA ',
    'SPECIFIC GRAVITY', 'SG',
    'PH',
    'GLUCOSE', 'GLU',
    'PROTEIN', 'PRO',
    'BLOOD', 'RBC', 'HEMATURIA',
    'LEUKOCYTE', 'WBC', 'PYURIA',
    'NITRITE',
    'BACTERIA',
    'KETONE',
    'BILIRUBIN',
    'UROBILINOGEN',
    'CLARITY', 'APPEARANCE',
    'COLOR',
}

CULTURE_MARKERS = {
    'CULTURE', 'C&S', 'CULTURE AND SENSITIVITY',
    'URINE CULTURE', 'UCX', 'U/C',
    'BLOOD CULTURE', 'BCX', 'B/C',
    'WOUND CULTURE', 'WCX',
    'SPUTUM CULTURE',
    'STOOL CULTURE',
    'ORGANISM', 'ISOLATED',
    'SENSITIVITY', 'SUSCEPTIBILITY',
    'NO GROWTH', 'NEGATIVE',
    'CFU', 'COLONY FORMING',
    'ESCHERICHIA', 'E. COLI', 'E.COLI',
    'KLEBSIELLA', 'PROTEUS', 'PSEUDOMONAS',
    'ENTEROCOCCUS', 'STAPHYLOCOCCUS', 'STREPTOCOCCUS',
    'CANDIDA', 'YEAST',
}

# Labs to always keep regardless of age
ALWAYS_KEEP_LABS = {
    'PSA', 'PROSTATE SPECIFIC',
    'TESTOSTERONE', 'FREE TESTOSTERONE', 'TOTAL TESTOSTERONE',
    'ESTROGEN', 'ESTRADIOL', 'E2',
    'LH', 'LUTEINIZING',
    'FSH', 'FOLLICLE',
    'TSH', 'THYROID STIMULATING',
    'VITAMIN D', '25-OH',
    'VITAMIN B12', 'B12', 'COBALAMIN',
    'FERRITIN', 'IRON',
    'PTH', 'PARATHYROID',
    'AFP', 'ALPHA-FETOPROTEIN',
    'HCG', 'BETA-HCG',
    'LDH', 'LACTATE DEHYDROGENASE',
    'A1C', 'HBA1C', 'HEMOGLOBIN A1C', 'GLYCATED',
    'PROLACTIN',
    'CORTISOL',
    'DHEA',
}


def parse_lab_date(date_str: str) -> Optional[datetime]:
    """
    Parse various date formats into datetime.

    Args:
        date_str: Date string in various formats

    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None

    # Try multiple formats
    formats = [
        '%b %d, %Y',      # Jan 15, 2025
        '%B %d, %Y',      # January 15, 2025
        '%m/%d/%Y',       # 01/15/2025
        '%m/%d/%y',       # 01/15/25
        '%Y-%m-%d',       # 2025-01-15
        '%b %d %Y',       # Jan 15 2025
    ]

    # Remove time component if present
    date_str = re.sub(r'@\d{2}:\d{2}', '', date_str)
    date_str = re.sub(r'\s+\d{2}:\d{2}', '', date_str)
    date_str = date_str.strip()

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    # Try to extract date components
    match = re.search(r'([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', date_str)
    if match:
        month_str = match.group(1)
        day = int(match.group(2))
        year = int(match.group(3))

        months = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        month = months.get(month_str)
        if month:
            try:
                return datetime(year, month, day)
            except ValueError:
                pass

    return None


def extract_date_from_lab_line(lab_line: str) -> Optional[str]:
    """
    Extract date from a lab result line.

    Args:
        lab_line: Lab result line

    Returns:
        Date string or None
    """
    # Pattern 1: (Jan 15, 2025)
    match = re.search(r'\(([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})\)', lab_line)
    if match:
        return match.group(1)

    # Pattern 2: - Jan 15, 2025
    match = re.search(r'-\s*([A-Za-z]{3}\s+\d{1,2},?\s+\d{4})', lab_line)
    if match:
        return match.group(1)

    # Pattern 3: M/D/YY or M/D/YYYY at start
    match = re.match(r'^(\d{1,2}/\d{1,2}/\d{2,4})', lab_line)
    if match:
        return match.group(1)

    return None


def classify_lab_type(test_name: str, lab_line: str) -> str:
    """
    Classify a lab into a category.

    Args:
        test_name: Normalized test name (uppercase)
        lab_line: Full lab line

    Returns:
        Category: 'cbc', 'bmp', 'cmp', 'ua', 'culture', 'always_keep', 'other'
    """
    test_upper = test_name.upper()
    line_upper = lab_line.upper()

    # Check always-keep labs first
    for marker in ALWAYS_KEEP_LABS:
        if marker in test_upper or marker in line_upper:
            return 'always_keep'

    # Check cultures
    for marker in CULTURE_MARKERS:
        if marker in test_upper or marker in line_upper:
            return 'culture'

    # Check UA FIRST (before BMP) - UA-specific markers
    # URINALYSIS is a more specific marker than generic terms
    ua_specific = ['URINALYSIS', 'UA ', 'SPECIFIC GRAVITY', 'NITRITE',
                   'BACTERIA', 'LEUKOCYTE', 'KETONE', 'UROBILINOGEN']
    for marker in ua_specific:
        if marker in test_upper or marker in line_upper:
            return 'ua'

    # Check CBC
    for marker in CBC_COMPONENTS:
        if marker in test_upper:
            return 'cbc'

    # Check BMP
    for marker in BMP_COMPONENTS:
        if marker in test_upper:
            return 'bmp'

    # Check CMP additional
    for marker in CMP_ADDITIONAL:
        if marker in test_upper:
            return 'cmp'

    # Check remaining UA components
    for marker in UA_COMPONENTS:
        if marker in test_upper or marker in line_upper:
            return 'ua'

    return 'other'


def is_abnormal_result(lab_line: str) -> bool:
    """
    Check if a lab result is marked as abnormal.

    Args:
        lab_line: Lab result line

    Returns:
        True if abnormal (H or L flag)
    """
    # Check for H or L flags
    if re.search(r'\d+\.?\d*\s*[HL]\b', lab_line):
        return True

    # Check for (H) or (L) markers
    if re.search(r'\([HL]\)', lab_line):
        return True

    # Check for HIGH or LOW text
    if re.search(r'\b(HIGH|LOW|ABNORMAL|ELEVATED|DECREASED)\b', lab_line, re.IGNORECASE):
        return True

    return False


def is_within_window(
    lab_date: Optional[datetime],
    window_months: int,
    reference_date: Optional[datetime] = None
) -> bool:
    """
    Check if a lab date is within the specified window.

    Args:
        lab_date: Date of the lab result
        window_months: Window in months
        reference_date: Reference date (defaults to now)

    Returns:
        True if within window
    """
    if not lab_date:
        # No date - assume it's recent
        return True

    if not reference_date:
        reference_date = datetime.now()

    cutoff_date = reference_date - timedelta(days=window_months * 30)
    return lab_date >= cutoff_date


def filter_labs_by_date(
    lab_lines: List[str],
    reference_date: Optional[datetime] = None
) -> List[str]:
    """
    Filter lab results based on date and category.

    Filtering rules:
    - Routine labs (CBC, BMP, UA): 6 months
    - Cultures: 2 years
    - Abnormal results: Keep up to 12 months
    - Always-keep labs (hormones, tumor markers): No filter
    - Labs without dates: Keep (assume recent)

    Args:
        lab_lines: List of lab result lines
        reference_date: Reference date (defaults to now)

    Returns:
        Filtered list of lab results
    """
    if not reference_date:
        reference_date = datetime.now()

    filtered_labs = []

    for line in lab_lines:
        # Extract test name
        test_name_match = re.match(r'^([A-Za-z][A-Za-z0-9\s,\-\(\)]+?)(?::|[\s]{2,}|\d)', line)
        test_name = test_name_match.group(1).strip().upper() if test_name_match else ""

        # Classify the lab
        lab_type = classify_lab_type(test_name, line)

        # Extract date
        date_str = extract_date_from_lab_line(line)
        lab_date = parse_lab_date(date_str) if date_str else None

        # Check if abnormal
        is_abnormal = is_abnormal_result(line)

        # Apply filtering rules
        should_keep = False

        if lab_type == 'always_keep':
            # Always keep hormone/tumor marker labs
            should_keep = True
        elif lab_type == 'culture':
            # Cultures: 2 years
            should_keep = is_within_window(lab_date, CULTURE_WINDOW_MONTHS, reference_date)
        elif is_abnormal:
            # Abnormal results: 12 months
            should_keep = is_within_window(lab_date, ABNORMAL_LAB_WINDOW_MONTHS, reference_date)
        elif lab_type in ('cbc', 'bmp', 'cmp', 'ua'):
            # Routine labs: 6 months
            should_keep = is_within_window(lab_date, ROUTINE_LAB_WINDOW_MONTHS, reference_date)
        elif lab_type == 'other':
            # Other labs: 6 months by default
            should_keep = is_within_window(lab_date, ROUTINE_LAB_WINDOW_MONTHS, reference_date)

        if should_keep:
            filtered_labs.append(line)
        else:
            logger.debug(f"Filtered out old lab: {line[:50]}... (date: {date_str}, type: {lab_type})")

    return filtered_labs


def extract_cultures(clinical_document: str) -> str:
    """
    Extract culture results from clinical document.

    Captures:
    - Urine cultures
    - Blood cultures
    - Wound cultures
    - Organism identification
    - Sensitivity patterns

    Args:
        clinical_document: Full clinical document

    Returns:
        Formatted culture results
    """
    cultures = []
    current_date = None

    # Pattern for culture sections
    culture_section_patterns = [
        r'(URINE CULTURE.*?)(?=\n\n|\n[A-Z]{2,}:|$)',
        r'(BLOOD CULTURE.*?)(?=\n\n|\n[A-Z]{2,}:|$)',
        r'(CULTURE AND SENSITIVITY.*?)(?=\n\n|\n[A-Z]{2,}:|$)',
        r'(CULTURE RESULTS.*?)(?=\n\n|\n[A-Z]{2,}:|$)',
    ]

    for pattern in culture_section_patterns:
        for match in re.finditer(pattern, clinical_document, re.DOTALL | re.IGNORECASE):
            culture_text = match.group(1).strip()
            if culture_text and len(culture_text) > 10:
                cultures.append(culture_text)

    # Extract individual culture lines with dates
    culture_line_patterns = [
        # VA format: "Specimen Collection Date: DATE ... ORGANISM: ..."
        r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4}).*?(?:ORGANISM|CULTURE|GROWTH)[:\s]+([^\n]+)',
        # Human readable: "Urine culture (DATE): RESULT"
        r'(?:Urine|Blood|Wound)\s+culture\s*\(([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\):\s*([^\n]+)',
        # Simple format: "Culture - DATE: RESULT"
        r'Culture\s*-\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4}):\s*([^\n]+)',
    ]

    for pattern in culture_line_patterns:
        for match in re.finditer(pattern, clinical_document, re.IGNORECASE):
            date = match.group(1)
            result = match.group(2).strip()
            if result:
                cultures.append(f"Culture ({date}): {result}")

    # Extract organisms and sensitivities
    organism_patterns = [
        r'((?:E\.\s*COLI|ESCHERICHIA COLI|KLEBSIELLA|PROTEUS|PSEUDOMONAS|ENTEROCOCCUS|STAPHYLOCOCCUS|STREPTOCOCCUS|CANDIDA)[^\n]+)',
        r'NO GROWTH[^\n]*',
        r'NEGATIVE[^\n]*(?:CULTURE)?[^\n]*',
        r'(\d+,?\d*\s*CFU[^\n]+)',
    ]

    for pattern in organism_patterns:
        for match in re.finditer(pattern, clinical_document, re.IGNORECASE):
            organism_line = match.group(0).strip()
            if organism_line and organism_line not in cultures:
                cultures.append(organism_line)

    if not cultures:
        return ""

    # Remove duplicates while preserving order
    seen = set()
    unique_cultures = []
    for c in cultures:
        c_normalized = c.lower().strip()
        if c_normalized not in seen:
            seen.add(c_normalized)
            unique_cultures.append(c)

    return '\n'.join(unique_cultures)


def extract_complete_bmp(clinical_document: str) -> str:
    """
    Extract complete Basic Metabolic Panel.

    Includes: Sodium, Potassium, Chloride, CO2, BUN, Creatinine, Glucose, Calcium

    Args:
        clinical_document: Full clinical document

    Returns:
        Formatted BMP results
    """
    bmp_results = {}
    current_date = None

    # Find specimen collection dates
    date_pattern = r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})'

    # BMP test patterns
    bmp_patterns = {
        'SODIUM': r'SODIUM\s+(\d+)\s*([HL])?\s*(?:mEq/L|mmol/L)',
        'POTASSIUM': r'POTASSIUM\s+(\d+\.?\d*)\s*([HL])?\s*(?:mEq/L|mmol/L)',
        'CHLORIDE': r'CHLORIDE\s+(\d+)\s*([HL])?\s*(?:mEq/L|mmol/L)',
        'CO2': r'(?:CO2|CARBON DIOXIDE|BICARBONATE)\s+(\d+)\s*([HL])?\s*(?:mEq/L|mmol/L)',
        'BUN': r'(?:BUN|UREA NITROGEN)\s+(\d+)\s*([HL])?\s*mg/dL',
        'CREATININE': r'CREATININE\s+(\d+\.?\d*)\s*([HL])?\s*mg/dL',
        'GLUCOSE': r'GLUCOSE\s+(\d+)\s*([HL])?\s*mg/dL',
        'CALCIUM': r'CALCIUM\s+(\d+\.?\d*)\s*([HL])?\s*mg/dL',
        'EGFR': r'(?:E?GFR|EGFR)[:\s]+[>]?(\d+)',
    }

    # Scan document
    lines = clinical_document.split('\n')
    for line in lines:
        # Check for date
        date_match = re.search(date_pattern, line)
        if date_match:
            current_date = date_match.group(1)
            continue

        # Check for BMP components
        for test_name, pattern in bmp_patterns.items():
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1)
                flag = match.group(2) if len(match.groups()) > 1 and match.group(2) else ''

                # Store with date as key for most recent
                key = f"{test_name}_{current_date or 'unknown'}"
                bmp_results[test_name] = {
                    'value': value,
                    'flag': flag,
                    'date': current_date
                }

    if not bmp_results:
        return ""

    # Format output
    lines = []
    date = bmp_results.get('SODIUM', {}).get('date') or \
           bmp_results.get('POTASSIUM', {}).get('date') or \
           list(bmp_results.values())[0].get('date')

    if date:
        lines.append(f"BMP ({date}):")
    else:
        lines.append("BMP:")

    # Order: Na, K, Cl, CO2, BUN, Cr, Glucose, Ca
    order = ['SODIUM', 'POTASSIUM', 'CHLORIDE', 'CO2', 'BUN', 'CREATININE', 'GLUCOSE', 'CALCIUM', 'EGFR']
    for test in order:
        if test in bmp_results:
            r = bmp_results[test]
            flag_str = f" ({r['flag']})" if r['flag'] else ""
            lines.append(f"  {test}: {r['value']}{flag_str}")

    return '\n'.join(lines)


def extract_complete_cbc(clinical_document: str) -> str:
    """
    Extract complete Complete Blood Count.

    Includes: WBC, RBC, Hemoglobin, Hematocrit, Platelets, MCV, MCH, MCHC

    Args:
        clinical_document: Full clinical document

    Returns:
        Formatted CBC results
    """
    cbc_results = {}
    current_date = None

    # Find specimen collection dates
    date_pattern = r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})'

    # CBC test patterns
    cbc_patterns = {
        'WBC': r'WBC\s+(\d+\.?\d*)\s*([HL])?\s*(?:10\.[eE]3/uL|K/uL|x10\^9/L)',
        'RBC': r'RBC\s+(\d+\.?\d*)\s*([HL])?\s*(?:10\.[eE]6/uL|M/uL)',
        'HEMOGLOBIN': r'(?:HEMOGLOBIN|HGB)\s+(\d+\.?\d*)\s*([HL])?\s*g/dL',
        'HEMATOCRIT': r'(?:HEMATOCRIT|HCT)\s+(\d+\.?\d*)\s*([HL])?\s*%',
        'PLATELETS': r'(?:PLATELET|PLT)S?\s+(\d+)\s*([HL])?\s*(?:10\.[eE]3/uL|K/uL)',
        'MCV': r'MCV\s+(\d+\.?\d*)\s*([HL])?\s*(?:fL|FL)',
        'MCH': r'MCH\s+(\d+\.?\d*)\s*([HL])?\s*(?:pg|PG)(?!\s*C)',
        'MCHC': r'MCHC\s+(\d+\.?\d*)\s*([HL])?\s*(?:g/dL|%)',
        'RDW': r'RDW\s+(\d+\.?\d*)\s*([HL])?\s*%',
    }

    # Scan document
    lines = clinical_document.split('\n')
    for line in lines:
        # Check for date
        date_match = re.search(date_pattern, line)
        if date_match:
            current_date = date_match.group(1)
            continue

        # Check for CBC components
        for test_name, pattern in cbc_patterns.items():
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1)
                flag = match.group(2) if len(match.groups()) > 1 and match.group(2) else ''

                cbc_results[test_name] = {
                    'value': value,
                    'flag': flag,
                    'date': current_date
                }

    if not cbc_results:
        return ""

    # Format output
    lines = []
    date = cbc_results.get('WBC', {}).get('date') or \
           cbc_results.get('HEMOGLOBIN', {}).get('date') or \
           list(cbc_results.values())[0].get('date')

    if date:
        lines.append(f"CBC ({date}):")
    else:
        lines.append("CBC:")

    # Order: WBC, RBC, Hgb, Hct, Plt, MCV, MCH, MCHC
    order = ['WBC', 'RBC', 'HEMOGLOBIN', 'HEMATOCRIT', 'PLATELETS', 'MCV', 'MCH', 'MCHC', 'RDW']
    for test in order:
        if test in cbc_results:
            r = cbc_results[test]
            flag_str = f" ({r['flag']})" if r['flag'] else ""
            lines.append(f"  {test}: {r['value']}{flag_str}")

    return '\n'.join(lines)


def extract_complete_ua(clinical_document: str) -> str:
    """
    Extract complete Urinalysis.

    Includes: Color, clarity, specific gravity, pH, glucose, protein, blood, etc.

    Args:
        clinical_document: Full clinical document

    Returns:
        Formatted UA results
    """
    ua_results = {}
    current_date = None

    # Find specimen collection dates
    date_pattern = r'Specimen Collection Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})'

    # UA test patterns
    ua_patterns = {
        'COLOR': r'(?:COLOR|COLOUR)\s*[:\s]+([A-Za-z]+)',
        'CLARITY': r'(?:CLARITY|APPEARANCE)\s*[:\s]+([A-Za-z]+)',
        'SPECIFIC GRAVITY': r'(?:SPECIFIC GRAVITY|SG)\s*[:\s]+(\d+\.?\d*)',
        'PH': r'\bPH\s*[:\s]+(\d+\.?\d*)',
        'GLUCOSE': r'(?:UA\s+)?GLUCOSE\s*[:\s]+([A-Za-z0-9+\-]+)',
        'PROTEIN': r'(?:UA\s+)?PROTEIN\s*[:\s]+([A-Za-z0-9+\-]+)',
        'BLOOD': r'(?:UA\s+)?BLOOD\s*[:\s]+([A-Za-z0-9+\-]+)',
        'LEUKOCYTE': r'LEUKOCYTE\s*(?:ESTERASE)?\s*[:\s]+([A-Za-z0-9+\-]+)',
        'NITRITE': r'NITRITE\s*[:\s]+([A-Za-z0-9+\-]+)',
        'BACTERIA': r'BACTERIA\s*[:\s]+([A-Za-z0-9+\-]+)',
        'WBC': r'(?:UA\s+)?WBC\s*[:\s]+(\d+[\-\d]*)',
        'RBC': r'(?:UA\s+)?RBC\s*[:\s]+(\d+[\-\d]*)',
    }

    # Scan document
    lines = clinical_document.split('\n')
    for line in lines:
        # Check for date
        date_match = re.search(date_pattern, line)
        if date_match:
            current_date = date_match.group(1)
            continue

        # Check for UA components
        for test_name, pattern in ua_patterns.items():
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()

                ua_results[test_name] = {
                    'value': value,
                    'date': current_date
                }

    if not ua_results:
        return ""

    # Format output
    lines = []
    date = list(ua_results.values())[0].get('date') if ua_results else None

    if date:
        lines.append(f"Urinalysis ({date}):")
    else:
        lines.append("Urinalysis:")

    # Order
    order = ['COLOR', 'CLARITY', 'SPECIFIC GRAVITY', 'PH', 'GLUCOSE', 'PROTEIN',
             'BLOOD', 'LEUKOCYTE', 'NITRITE', 'BACTERIA', 'WBC', 'RBC']
    for test in order:
        if test in ua_results:
            r = ua_results[test]
            lines.append(f"  {test}: {r['value']}")

    return '\n'.join(lines)


def extract_labs_with_temporal_filter(
    clinical_document: str,
    reference_date: Optional[datetime] = None
) -> Dict[str, str]:
    """
    Extract all lab types with temporal filtering.

    Args:
        clinical_document: Full clinical document
        reference_date: Reference date for filtering (defaults to now)

    Returns:
        Dictionary with 'bmp', 'cbc', 'ua', 'cultures', 'other' keys
    """
    from .lab_extractor import extract_labs

    results = {}

    # Extract BMP
    bmp = extract_complete_bmp(clinical_document)
    if bmp:
        bmp_lines = bmp.split('\n')
        filtered_bmp = filter_labs_by_date(bmp_lines, reference_date)
        results['bmp'] = '\n'.join(filtered_bmp)

    # Extract CBC
    cbc = extract_complete_cbc(clinical_document)
    if cbc:
        cbc_lines = cbc.split('\n')
        filtered_cbc = filter_labs_by_date(cbc_lines, reference_date)
        results['cbc'] = '\n'.join(filtered_cbc)

    # Extract UA
    ua = extract_complete_ua(clinical_document)
    if ua:
        ua_lines = ua.split('\n')
        filtered_ua = filter_labs_by_date(ua_lines, reference_date)
        results['ua'] = '\n'.join(filtered_ua)

    # Extract cultures (2 year window)
    cultures = extract_cultures(clinical_document)
    if cultures:
        culture_lines = cultures.split('\n')
        filtered_cultures = filter_labs_by_date(culture_lines, reference_date)
        results['cultures'] = '\n'.join(filtered_cultures)

    # Extract general labs and filter
    general_labs = extract_labs(clinical_document)
    if general_labs:
        general_lines = general_labs.split('\n')
        filtered_general = filter_labs_by_date(general_lines, reference_date)
        results['other'] = '\n'.join(filtered_general)

    return results
