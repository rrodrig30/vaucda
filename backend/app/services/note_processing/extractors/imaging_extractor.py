"""
Imaging Results Extractor

Extracts imaging reports from clinical documents.
"""

import re


def extract_imaging(clinical_document: str) -> str:
    """
    Extract imaging reports from clinical documents.

    Looks for radiology reports, ultrasounds, CT scans, MRI reports, etc.
    Supports both VA format and human-readable format.

    Args:
        clinical_document: Full clinical document

    Returns:
        Extracted imaging reports (study name + date + impression), or "" if not found
    """
    imaging_reports = []

    # First, try to extract human-readable format (priority)
    # Pattern: "===== IMAGING =====" section with studies
    human_readable_imaging = extract_human_readable_imaging(clinical_document)
    if human_readable_imaging:
        imaging_reports.extend(human_readable_imaging)

    # Second, extract VA "Detailed Report" format
    detailed_report_imaging = extract_detailed_report_imaging(clinical_document)
    if detailed_report_imaging:
        imaging_reports.extend(detailed_report_imaging)

    # Third, extract VA format (traditional)
    va_format_imaging = extract_va_format_imaging(clinical_document)
    if va_format_imaging:
        imaging_reports.extend(va_format_imaging)

    if not imaging_reports:
        return ""

    # Remove duplicates while preserving order
    # Use improved deduplication that matches studies by name+date
    unique_reports = []
    seen_study_dates = {}  # Key: (study_name_normalized, date_normalized) -> report

    for report in imaging_reports:
        # Extract study name and date from report header
        header_match = re.match(r'([^(]+)\s*\(([^)]+)\):', report)
        if header_match:
            study_name = header_match.group(1).strip()
            date_str = header_match.group(2).strip()

            # Normalize study name and date for comparison
            study_normalized = re.sub(r'\s+', ' ', study_name.upper())
            # Remove contrast modifiers in the right order:
            # 1. First remove "W/O & W/ IV CONTRAST" or "W/O & W/" patterns
            study_normalized = re.sub(r'\s*W/O\s*&\s*W/\s*(?:IV\s*)?(?:CONTRAST)?', '', study_normalized)
            # 2. Then remove remaining contrast variations
            study_normalized = re.sub(r'\s*(?:WITH|WITHOUT|W/O|W/)\s*(?:IV\s*)?CONTRAST', '', study_normalized)
            study_normalized = re.sub(r'\s*(?:IV\s*)?CONTRAST', '', study_normalized)
            # 3. Clean up extra whitespace
            study_normalized = re.sub(r'\s+', ' ', study_normalized).strip()
            date_normalized = _normalize_date_for_comparison(date_str)

            key = (study_normalized, date_normalized)

            # If we've seen this study+date before, keep the longer version
            if key in seen_study_dates:
                if len(report) > len(seen_study_dates[key]):
                    # Replace with longer version
                    seen_study_dates[key] = report
            else:
                seen_study_dates[key] = report
        else:
            # No header match - keep as is
            unique_reports.append(report)

    # Add all unique studies
    unique_reports.extend(seen_study_dates.values())

    return '\n\n'.join(unique_reports)


def _normalize_date_for_comparison(date_str: str) -> str:
    """
    Normalize date string for comparison (handles different formats).

    Examples:
        "11/12/2019" -> "20191112"
        "NOV 12, 2019" -> "20191112"

    Args:
        date_str: Date string in various formats

    Returns:
        Normalized date string
    """
    # Try numeric format: MM/DD/YYYY
    numeric_match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
    if numeric_match:
        month, day, year = numeric_match.groups()
        return f"{year}{int(month):02d}{int(day):02d}"

    # Try text format: MON DD, YYYY
    text_match = re.match(r'([A-Z]{3})\s+(\d{1,2}),?\s+(\d{4})', date_str, re.IGNORECASE)
    if text_match:
        month_name, day, year = text_match.groups()
        month_map = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                     'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
        month = month_map.get(month_name.upper(), 1)
        return f"{year}{month:02d}{int(day):02d}"

    # Fallback: return as-is
    return date_str.upper()


def extract_detailed_report_imaging(clinical_document: str) -> list:
    """
    Extract VA "Detailed Report" format imaging.

    Pattern:
    Detailed Report
     CT ABD & PELVIS W/ IV CONTRAST

     Exm Date: APR 02, 2025@11:50
     ...
     Impression:
        No acute abdominopelvic abnormality.

    Returns:
        List of imaging report strings
    """
    imaging_reports = []

    # Look for "Detailed Report" followed by imaging study names
    detailed_reports = re.finditer(
        r'Detailed Report\s+(.*?)(?=Detailed Report|Facility:|Performing Lab|Printed at:|={30,}|$)',
        clinical_document,
        re.DOTALL | re.IGNORECASE
    )

    for match in detailed_reports:
        content = match.group(1).strip()

        # Check if this contains imaging keywords
        if not re.search(r'(?:CT|MRI|ULTRASOUND|X-RAY|XRAY|RADIOGRAPH)', content, re.IGNORECASE):
            continue

        # Extract study name (first line after "Detailed Report" containing imaging keyword)
        # The study name is typically on the first line, may have leading whitespace
        lines = content.split('\n')
        study_name = "Imaging Study"
        for line in lines[:5]:  # Check first 5 lines
            if re.search(r'(?:CT|MRI|ULTRASOUND|X-RAY|XRAY|RADIOGRAPH)', line, re.IGNORECASE):
                # Exclude lines with "Exm Date:", "Req Phys:", etc
                if not re.search(r'(?:Exm Date:|Req Phys:|Pat Loc:|Service:|Img Loc:)', line, re.IGNORECASE):
                    study_name = line.strip()
                    break

        # Extract date
        date_match = re.search(
            r'Exm Date:\s*([A-Z]{3}\s+\d{1,2},\s+\d{4})',
            content,
            re.IGNORECASE
        )
        date = date_match.group(1).strip() if date_match else ""

        # Extract impression
        impression_match = re.search(
            r'Impression:\s*(.*?)(?=\n\s*(?:Signed by|Primary|Facility:|Printed at:|$))',
            content,
            re.IGNORECASE | re.DOTALL
        )

        if impression_match:
            impression = impression_match.group(1).strip()

            # Clean up whitespace
            impression = re.sub(r'\s+', ' ', impression)
            impression = impression.strip()

            # Skip if too short
            if len(impression) < 10:
                continue

            # Also check for cyst findings in Kidneys section (important for stone workup)
            cyst_match = re.search(
                r'((?:\d+\.?\d*)\s*cm\s+hyperdense\s+lesion.*?(?:cyst|lesion))',
                content,
                re.IGNORECASE | re.DOTALL
            )
            if cyst_match:
                cyst_finding = cyst_match.group(1).strip()
                # Clean up whitespace
                cyst_finding = re.sub(r'\s+', ' ', cyst_finding)
                # Append to impression
                impression = f"{impression}. FINDINGS: {cyst_finding}"

            # Format report
            if date:
                report = f"{study_name} ({date}):\nIMPRESSION: {impression}"
            else:
                report = f"{study_name}:\nIMPRESSION: {impression}"

            imaging_reports.append(report)

    return imaging_reports


def extract_human_readable_imaging(clinical_document: str) -> list:
    """
    Extract human-readable imaging format.

    Pattern:
    STUDY NAME (DATE):
    IMPRESSION: findings

    Examples:
    MRI PROSTATE (8/29/25):
    IMPRESSION: PI-RADS 2 (clinically significant cancer is unlikely to be present)

    Returns:
        List of imaging report strings
    """
    imaging_reports = []

    # Look for the IMAGING section marker
    imaging_section_match = re.search(
        r'={30,}\s*IMAGING\s*={30,}(.*?)(?:={30,}|$)',
        clinical_document,
        re.DOTALL | re.IGNORECASE
    )

    if not imaging_section_match:
        return imaging_reports

    imaging_content = imaging_section_match.group(1).strip()

    # Pattern: Study name line, followed by IMPRESSION line(s) or direct content
    # Examples:
    # MRI PROSTATE (8/29/25):
    # IMPRESSION: PI-RADS 2 (clinically significant cancer is unlikely to be present)
    #
    # CT Urogram (11/12/2019):
    # 6.7 cm posterior superior pole mildly complex fluid attenuating cyst...

    # Split into individual studies
    # Each study starts with text (may include uppercase, lowercase, numbers) and has a date in parentheses
    # Updated pattern to handle:
    # - Mixed case study names like "CT Urogram"
    # - Content with or without "IMPRESSION:" prefix
    # - Multi-line content that ends at next study or section boundary
    study_pattern = r'([A-Z][A-Za-z0-9\s/\(\)]+(?:\([0-9/]+\))):?\s*\n(?:IMPRESSION:?\s*)?(.*?)(?=\n[A-Z][A-Za-z]+(?:[A-Za-z0-9\s/]+)?\([0-9/]+\):|={30,}|$)'

    for match in re.finditer(study_pattern, imaging_content, re.DOTALL):
        study_line = match.group(1).strip()
        impression = match.group(2).strip()

        # Parse study name and date
        study_date_match = re.match(r'(.+?)\s*\((\d{1,2}/\d{1,2}/\d{2,4})\)', study_line)
        if study_date_match:
            study_name = study_date_match.group(1).strip()
            date = study_date_match.group(2).strip()
        else:
            study_name = study_line.strip()
            date = ""

        # Clean up impression
        # Remove "IMPRESSION:" prefix if it appears
        impression = re.sub(r'^IMPRESSION:\s*', '', impression, flags=re.IGNORECASE)

        # Clean up whitespace
        impression = re.sub(r'\s+', ' ', impression)
        impression = impression.strip()

        # Skip if impression is too short (likely parsing error)
        if len(impression) < 10:
            continue

        # Format report
        # Note: Don't add "IMPRESSION:" prefix if the content doesn't already have it
        # The extracted content is the full imaging results/impression
        if date:
            report = f"{study_name} ({date}):\n{impression}"
        else:
            report = f"{study_name}:\n{impression}"

        imaging_reports.append(report)

    return imaging_reports


def extract_va_format_imaging(clinical_document: str) -> list:
    """
    Extract VA-formatted imaging reports (traditional format).

    Pattern: "---- RADIOLOGY ----" sections with Exam, Date, and IMPRESSION fields.

    Returns:
        List of imaging report strings
    """
    imaging_reports = []

    # Look for imaging sections - more specific patterns
    # Pattern 1: "---- RADIOLOGY ----" or similar headers
    radiology_sections = re.split(r'-{4,}\s*(?:RADIOLOGY|IMAGING)\s*-{4,}', clinical_document, flags=re.IGNORECASE)

    for i, section in enumerate(radiology_sections):
        if i == 0:
            continue  # Skip content before first marker

        # Take only the first 2000 chars of section (one report)
        section = section[:2000]

        # Skip if this looks like a lab report (common false positive)
        if re.search(r'(?:URINALYSIS|CHEMISTRY|HEMATOLOGY|CBC|CMP|BMP|URINE|CLEAN CATCH)', section, re.IGNORECASE):
            continue

        # Only process if section contains actual imaging keywords
        if not re.search(r'(?:CT|MRI|ULTRASOUND|X-RAY|XRAY|RADIOGRAPH|SCAN|IMPRESSION)', section, re.IGNORECASE):
            continue

        # Extract study name/type
        study_match = re.search(
            r'(?:Exam|Study|Procedure)[:\s]+([^\n]+)',
            section,
            re.IGNORECASE
        )
        study_name = study_match.group(1).strip() if study_match else "Imaging Study"

        # Extract date
        date_match = re.search(
            r'(?:Date|Exam Date|Study Date)[:\s]+([A-Za-z]{3}\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})',
            section,
            re.IGNORECASE
        )
        date = date_match.group(1).strip() if date_match else ""

        # Extract impression
        impression_match = re.search(
            r'IMPRESSION[:\s]+(.*?)(?=\n\s*(?:ADDENDUM|ELECTRONICALLY|Radiologist|Report|------|$))',
            section,
            re.IGNORECASE | re.DOTALL
        )

        if impression_match:
            impression = impression_match.group(1).strip()

            # Filter out VA administrative metadata
            va_metadata_patterns = [
                r'UCID:.*',
                r'Patient Type:.*',
                r'Service Connection:.*',
                r'SC Percent:.*',
                r'Facility:.*',
                r'Submitted by:.*',
                r'As of:.*'
            ]

            for pattern_str in va_metadata_patterns:
                impression = re.sub(pattern_str, '', impression, flags=re.IGNORECASE | re.MULTILINE)

            # Clean up: remove excessive whitespace
            impression = re.sub(r' +', ' ', impression)
            impression = re.sub(r'\n{3,}', '\n', impression)
            impression = impression.strip()

            # Validate completeness - ensure impression is not truncated
            is_complete, validation_msg = validate_imaging_completeness(impression, study_name)
            if not is_complete:
                # Log warning but still include - better to have truncated data than none
                impression += f" [WARNING: {validation_msg}]"

            # Format report
            if date:
                report = f"{study_name} ({date}):\n  {impression}"
            else:
                report = f"{study_name}:\n  {impression}"

            if impression and len(impression) > 10:
                imaging_reports.append(report)

    return imaging_reports


def extract_imaging_from_note(note_content: str) -> str:
    """
    Extract imaging section from a clinical note (alternative format).

    Some notes may have embedded imaging results in an "Imaging:" section.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted imaging text, or "" if not found
    """
    # Pattern: "Imaging:" or "IMAGING:" followed by content
    pattern = r'(?:Imaging|IMAGING):\s*(.*?)(?=\n\s*(?:ASSESSMENT:|PLAN:|MEDICATIONS:|ALLERGIES:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        imaging_text = match.group(1).strip()

        # Filter out lab results that appear in imaging sections
        if re.search(r'(?:URINALYSIS|CHEMISTRY|HEMATOLOGY|CBC|CMP|BMP|URINE|CLEAN CATCH)', imaging_text, re.IGNORECASE):
            return ""

        # Only return if it contains actual imaging keywords
        if not re.search(r'(?:CT|MRI|ULTRASOUND|X-RAY|XRAY|RADIOGRAPH|SCAN|IMPRESSION)', imaging_text, re.IGNORECASE):
            return ""

        # Clean up whitespace
        imaging_text = re.sub(r' +', ' ', imaging_text)
        imaging_text = re.sub(r'\n{3,}', '\n\n', imaging_text)
        return imaging_text

    return ""


def validate_imaging_completeness(impression_text: str, study_name: str = "") -> tuple:
    """
    Validate that an imaging impression is complete and not truncated.

    Args:
        impression_text: The extracted impression text
        study_name: Optional study name for context

    Returns:
        Tuple of (is_complete: bool, message: str)
    """
    # Check 1: Minimum length - impressions should have substance
    if len(impression_text) < 20:
        return False, "Impression too short - likely incomplete"

    # Check 2: Ends with proper punctuation or complete thought
    # Valid endings: period, numbered list, "above", "below", complete sentences
    valid_endings = ['.', ')', 'above', 'below', 'noted', 'seen', 'identified', 'present', 'absent']
    text_lower = impression_text.lower().strip()

    has_valid_ending = False
    for ending in valid_endings:
        if text_lower.endswith(ending):
            has_valid_ending = True
            break

    # Also check if it ends with a number (numbered findings like "4.")
    if re.search(r'\d+\.\s*$', impression_text.strip()):
        has_valid_ending = True

    if not has_valid_ending:
        # Check if it looks like it was cut off mid-sentence
        if re.search(r',\s*$', impression_text):
            return False, "Impression appears truncated (ends with comma)"
        if re.search(r'\b(?:and|or|with|for|to|the)\s*$', impression_text, re.IGNORECASE):
            return False, "Impression appears truncated (ends mid-phrase)"

    # Check 3: For multi-finding reports, ensure all findings are present
    # If numbered findings (1., 2., 3.), check sequence is complete
    numbered_findings = re.findall(r'\b(\d+)\.\s+', impression_text)
    if numbered_findings:
        numbers = [int(n) for n in numbered_findings]
        # Check if sequence is continuous (1, 2, 3...) without gaps
        expected = list(range(1, max(numbers) + 1))
        if numbers != expected:
            return False, f"Numbered findings may be incomplete (found {numbers}, expected {expected})"

    # Check 4: Critical findings should not be cut off
    # Look for critical terms that should have complete descriptions
    critical_terms = [
        r'calcul(?:us|i)',  # kidney stone/calculi
        r'cyst',
        r'mass',
        r'nodule',
        r'lesion',
        r'fracture',
        r'obstruction'
    ]

    for term_pattern in critical_terms:
        matches = list(re.finditer(term_pattern, impression_text, re.IGNORECASE))
        if matches:
            last_match = matches[-1]
            # Ensure there's sufficient text after the critical finding
            remaining_text = impression_text[last_match.end():]
            if len(remaining_text.strip()) < 15:
                return False, f"Critical finding '{matches[-1].group()}' may be incompletely described"

    # Check 5: Study-specific validation
    if 'CT' in study_name.upper() or 'MRI' in study_name.upper():
        # CT/MRI reports should have reasonable length
        if len(impression_text) < 50:
            return False, "CT/MRI impression unusually short"

    # All checks passed
    return True, "Complete"
