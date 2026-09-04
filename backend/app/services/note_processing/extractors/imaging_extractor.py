"""
Imaging Results Extractor

Extracts imaging reports from clinical documents.
"""

import re


# Comprehensive list of imaging keywords used across all extraction functions
# Includes: CT, MRI, Ultrasound (US, U/S, ULTRASOUND), X-ray, Bone Scan, Nuclear medicine
IMAGING_KEYWORDS = (
    r'(?:'
    r'CT[\s,]|CT$|'                         # CT scan (CT ABDOMEN or CT, ABDOMEN)
    r'MRI[\s,]|MRI$|MR[\s,]|'              # MRI (MRI PROSTATE or MRI, PROSTATE)
    r'ULTRASOUND|'                          # Full ultrasound
    r'\bUS[\s,]+[A-Z]|'                      # US abbreviation followed by body part (space or comma)
    r'\bU/S\s|'                             # U/S abbreviation
    r'SONOGRAM|SONO\s|'                    # Sonogram
    r'X-RAY|XRAY|'                          # X-ray
    r'RADIOGRAPH|'                          # Radiograph
    r'PET\s|PET/CT|PET$|'                  # PET scan
    r'BONE\s+SCAN|'                         # Bone scan
    r'NM\s+|NUCLEAR\s+MEDICINE|NUCLEAR\s+|' # Nuclear medicine
    r'SKELETAL\s+SCINTIGRAPHY|'            # Bone scan alternative name
    r'WHOLE\s+BODY\s+BONE|'                # Whole body bone scan
    r'RENAL\s+SCAN|'                        # Renal scan
    r'MAG3|DTPA|'                           # Renal scan types
    r'MAMMO|'                               # Mammogram
    r'FLUORO|'                              # Fluoroscopy
    r'DEXA|DXA|'                            # Bone density
    r'ECHO|'                                # Echocardiogram
    r'CYSTOGRAM|VCUG|'                     # Urologic imaging
    r'RETROGRADE|'                          # Retrograde studies
    r'IVP|IVU|'                             # IV pyelogram/urogram
    r'KUB|'                                 # Kidney-Ureter-Bladder
    r'ANGIOGRAM|ANGIO|'                    # Angiography
    r'VENOGRAM|'                            # Venography
    r'MYELOGRAM|'                           # Myelography
    r'ARTHROGRAM'                           # Arthrography
    r')'
)


# DXA / bone-density boilerplate patterns. These chunks repeat verbatim
# (modulo whitespace and percentages) in every VA DXA impression and
# contribute nothing to clinical decision making. See logs/dexa.txt for
# the source text. Stripped via _strip_dexa_boilerplate() after extraction.
#
# Each pattern is whitespace-tolerant and case-insensitive. Order doesn't
# matter — we apply them all as repeated subs.
_DEXA_BOILERPLATE_PATTERNS = [
    # FRAX 10-year probability sentence (percentages vary by patient)
    re.compile(
        r'\s*Based on the United States FRAX calculator,\s*'
        r"the patient'?s\s*10[\s-]year probability of major osteoporotic "
        r'fracture is\s*\d+(?:\.\d+)?\s*%\s*and\s*10[\s-]year probability of '
        r'hip fracture is\s*\d+(?:\.\d+)?\s*%\.?\s*',
        re.IGNORECASE | re.DOTALL,
    ),
    # WHO osteoporosis / osteopenia diagnostic criteria paragraph
    re.compile(
        r'\s*According to the World Health Organization guidelines,?\s*'
        r'osteoporosis may be diagnosed if the lowest T-score of the '
        r'lumbar spine,\s*total hip or femoral neck is\s*-?\s*2\.5\s*or less\.\s*'
        r'Low bone density \(osteopenia\) may be diagnosed if the T-score '
        r'falls between\s*-?\s*1\.0\s*and\s*-?\s*2\.5\.\s*'
        r'In certain circumstances the 33%\s*radius\s*'
        r'\(also called 1/3rd radius\) may be utilized\.?\s*',
        re.IGNORECASE | re.DOTALL,
    ),
    # Men age 50 diagnostic threshold reminder
    re.compile(
        r'\s*Osteoporosis may be diagnosed in men age 50 and older if the '
        r'T-score of the lumbar spine,\s*total hip or femoral neck is\s*'
        r'-?\s*2\.5\s*or less\.?\s*',
        re.IGNORECASE | re.DOTALL,
    ),
    # RECOMMENDATIONS block — three numbered items running from "1. If
    # therapy is contemplated..." through "...restore bone mass."
    re.compile(
        r'\s*RECOMMENDATIONS:?\s*'
        r'1\.\s*If therapy is contemplated.*?'
        r'2\.\s*The National Osteoporosis Foundation \(NOF\) guidelines.*?'
        r'3\.\s*Patients with diagnosed cases of osteoporosis.*?'
        r'restore bone mass\.?\s*',
        re.IGNORECASE | re.DOTALL,
    ),
]

# Heuristic markers that identify a report as a DXA / bone-density study.
# Only DXA reports get the boilerplate stripped — we don't want to touch
# unrelated reports that happen to mention "T-score" in passing.
_DEXA_HEADER_RE = re.compile(
    r'\b(?:DXA|DEXA|DUAL[\s-]ENERGY|BONE\s+DENSIT(?:OMETRY|Y)|'
    r'XRAY\s+ABSORPTION|X-RAY\s+ABSORPTION)\b',
    re.IGNORECASE,
)


def _strip_dexa_boilerplate(report: str) -> str:
    """Remove non-actionable FRAX/WHO/NOF boilerplate from DXA impressions.

    No-op for non-DXA reports (gated on _DEXA_HEADER_RE matching anywhere
    in the report's header line).
    """
    if not report or not _DEXA_HEADER_RE.search(report):
        return report
    cleaned = report
    for pat in _DEXA_BOILERPLATE_PATTERNS:
        cleaned = pat.sub(' ', cleaned)
    # Collapse the whitespace runs the substitutions leave behind, but
    # preserve the "STUDY (DATE):\nIMPRESSION: ..." line break.
    head, sep, body = cleaned.partition('\n')
    body = re.sub(r'[ \t]+', ' ', body)
    body = re.sub(r'\s*\n\s*', '\n', body).strip()
    return f'{head.rstrip()}{sep}{body}' if sep else head.rstrip()


# Non-clinical boilerplate VA radiology reports append to impressions:
# attending/resident attestations, CT dose-metric footers, and journal
# citation footnotes. Stripped from EVERY report so the IMAGING section carries
# the clinical impression only.
_REPORT_BOILERPLATE = [
    re.compile(r"\s*I,?\s+the\s+attending\s+(?:physician|radiologist)?,?\s*"
               r"have\s+personally\s+reviewed[^\n]*", re.I),
    re.compile(r"\s*(?:I|We)\s+have\s+personally\s+reviewed\s+(?:the\s+)?image[^\n]*", re.I),
    re.compile(r"\s*(?:This\s+study\s+was|Images?\s+were)\s+(?:personally\s+)?"
               r"reviewed\s+by\s+the\s+attending[^\n]*", re.I),
    re.compile(r"\s*Approval\s+of\s+this\s+report\s+by\s+the\s+teaching\s+physician[^\n]*", re.I),
    re.compile(r"\s*Up-to-date\s+CT\s+equipment[^\n]*", re.I),
    re.compile(r"\s*CTDIvol:[^\n]*", re.I),
    re.compile(r"\s*DLP:\s*[\d.]+\s*mGy[- ]?cm\.?", re.I),
    re.compile(r"\s*This\s+(?:CT\s+)?exam\s+was\s+performed\s+using[^\n]*", re.I),
    re.compile(r"\s*(?:Radiation\s+)?dose\s+reduction\s+techniques[^\n]*", re.I),
    # journal citation footnote: "* Silverman, S. et al. ... Radiology 2019; 292:475-488."
    re.compile(r"\s*\*?\s*[A-Z][A-Za-z]+,\s+[A-Z]\.[^\n]*?"
               r"(?:Radiology|Radiographics|J\s*Urol|AJR|Eur\s*Urol|Urology)\s+\d{4}[^\n]*",
               re.I),
]


def _strip_report_boilerplate(report: str) -> str:
    """Remove non-clinical attestation / dose-metric / citation boilerplate from
    a single imaging report, keeping the clinical impression."""
    if not report:
        return report
    for pat in _REPORT_BOILERPLATE:
        report = pat.sub("", report)
    report = re.sub(r"[ \t]{2,}", " ", report)
    report = re.sub(r"[ \t]+\n", "\n", report)
    report = re.sub(r"\s+([.,;])", r"\1", report)
    return report.rstrip()


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

    # Fourth, extract external/non-VA facility imaging (BAMC, SAMC, etc.)
    external_imaging = extract_external_imaging(clinical_document)
    if external_imaging:
        imaging_reports.extend(external_imaging)

    # Fifth, extract CPRS report-verified format. Used by VistA CPRS exports
    # where each study is a block of bareword headers
    # ("Exam Date/Time", "Procedure Name", "Reason for Study",
    #  "Clinical History", "Impression", "Report") each followed by an
    # indented value. None of the prior four extractors match this layout
    # because it lacks "===== IMAGING =====", "Detailed Report",
    # "---- RADIOLOGY ----", or the short FACILITY-prefix bullet form.
    cprs_imaging = extract_cprs_format_imaging(clinical_document)
    if cprs_imaging:
        imaging_reports.extend(cprs_imaging)

    if not imaging_reports:
        return ""

    # Remove duplicates while preserving order
    # Use improved deduplication that matches studies by name+date
    unique_reports = []
    seen_study_dates = {}  # Key: (study_name_normalized, date_normalized) -> report

    for report in imaging_reports:
        # Extract study name and date from report header. The date is
        # always the LAST parenthesized group on the header line (e.g.
        # "(MAR 13, 2026):") — study names themselves may contain
        # parentheses such as "XRAY ABSORPTION (DXA) AXIAL", so we can't
        # anchor the date paren to the first one we see. A non-greedy
        # `.+?` followed by `\(([^()]+)\)\s*:` lets the engine extend the
        # study-name capture past any internal parens until it finds the
        # final "(date):" right before the line break.
        header_match = re.match(r'^(.+?)\s*\(([^()]+)\)\s*:', report)
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
            # No "(date):" header — try a dateless fallback so reports
            # like "MRI, PROSTATE W/O & W/CONTRAST:" (which some VA
            # exports emit without a date paren) still dedup against
            # other dateless copies of the same study. Key on
            # (normalized_study_name, "") + a short content hash so
            # reports with the same study name but genuinely different
            # impressions don't collapse into one.
            head_match = re.match(r'^(.+?)\s*:', report)
            if head_match:
                study_name = head_match.group(1).strip()
                study_normalized = re.sub(r'\s+', ' ', study_name.upper())
                study_normalized = re.sub(r'\s*W/O\s*&\s*W/\s*(?:IV\s*)?(?:CONTRAST)?', '', study_normalized)
                study_normalized = re.sub(r'\s*(?:WITH|WITHOUT|W/O|W/)\s*(?:IV\s*)?CONTRAST', '', study_normalized)
                study_normalized = re.sub(r'\s*(?:IV\s*)?CONTRAST', '', study_normalized)
                study_normalized = re.sub(r'\s+', ' ', study_normalized).strip()
                # First 80 chars of the body as a coarse content fingerprint
                body_start = report.split('\n', 1)[1] if '\n' in report else ''
                content_fp = re.sub(r'\s+', ' ', body_start)[:80].upper()
                key = (study_normalized, '', content_fp)
                if key in seen_study_dates:
                    if len(report) > len(seen_study_dates[key]):
                        seen_study_dates[key] = report
                else:
                    seen_study_dates[key] = report
            else:
                # Truly unparseable header — keep verbatim (last resort)
                unique_reports.append(report)

    # Add all unique studies
    unique_reports.extend(seen_study_dates.values())

    # Strip non-actionable boilerplate from DXA / bone-density studies.
    # VA DXA impressions always tail with the same FRAX/WHO/NOF
    # paragraphs and a generic RECOMMENDATIONS list — text that clutters
    # the rendered note without changing clinical decision making.
    unique_reports = [_strip_report_boilerplate(_strip_dexa_boilerplate(r))
                      for r in unique_reports]

    # Sort reverse chronologically — most recent study at the top of the
    # IMAGING section. Reports with an unparseable / missing date sort
    # LAST so they remain visible but don't push current imaging down.
    unique_reports.sort(key=_imaging_report_sort_key, reverse=True)

    return '\n\n'.join(unique_reports)


def _normalize_date_for_comparison(date_str: str) -> str:
    """
    Normalize date string for comparison (handles different formats).

    Examples:
        "11/12/2019"  -> "20191112"
        "11/12/19"    -> "20191112"   (2-digit year, assume 2000+)
        "NOV 12, 2019"-> "20191112"
        "8/2017"      -> "20170801"   (month/year only — day defaults to 01)

    Args:
        date_str: Date string in various formats

    Returns:
        Normalized YYYYMMDD string sortable as text, or the raw input
        uppercased if nothing parses.
    """
    # Try numeric format: MM/DD/YYYY or MM/DD/YY
    numeric_match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', date_str)
    if numeric_match:
        month, day, year = numeric_match.groups()
        if len(year) == 2:
            # 2-digit year — pivot at 50 (>=50 -> 19xx, <50 -> 20xx).
            # All clinic notes here are recent (2000+) so the common case
            # resolves to 20xx, but the pivot keeps legacy dates correct.
            year = ('19' + year) if int(year) >= 50 else ('20' + year)
        return f"{year}{int(month):02d}{int(day):02d}"

    # Try M/YYYY shorthand (no day) — assume day 01 for sortability.
    my_match = re.match(r'(\d{1,2})/(\d{4})$', date_str)
    if my_match:
        month, year = my_match.groups()
        return f"{year}{int(month):02d}01"

    # Try text format: MON DD, YYYY
    text_match = re.match(r'([A-Z]{3,9})\s+(\d{1,2}),?\s+(\d{4})', date_str, re.IGNORECASE)
    if text_match:
        month_name, day, year = text_match.groups()
        month_map = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                     'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
        month = month_map.get(month_name[:3].upper(), 1)
        return f"{year}{month:02d}{int(day):02d}"

    # Fallback: return as-is
    return date_str.upper()


def _imaging_report_sort_key(report: str) -> str:
    """Return a YYYYMMDD sort key for an imaging report block.

    Looks for the date in the report's header line first
    ("STUDY (DATE):"), falling back to any inline date if the header
    has no date. Reports with no parseable date get '00000000' so they
    sort to the bottom under descending sort.
    """
    if not report:
        return '00000000'
    header = report.split('\n', 1)[0]
    # Last "(...)" group right before the trailing colon is the date.
    paren = re.findall(r'\(([^()]+)\)', header)
    if paren:
        normalized = _normalize_date_for_comparison(paren[-1].strip())
        if re.fullmatch(r'\d{8}', normalized):
            return normalized
    # Last resort: try any MM/DD/YYYY or "MON DD, YYYY" anywhere in the
    # first line of the body in case the header is dateless but the
    # body mentions one (e.g. embedded "Exm Date:" leakage).
    body_first = report.split('\n', 2)[1] if '\n' in report else ''
    for cand in re.findall(
        r'(\d{1,2}/\d{1,2}/\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})',
        body_first,
    ):
        normalized = _normalize_date_for_comparison(cand)
        if re.fullmatch(r'\d{8}', normalized):
            return normalized
    return '00000000'


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

    # Use module-level IMAGING_KEYWORDS constant

    # Look for "Detailed Report" followed by imaging study names
    detailed_reports = re.finditer(
        r'Detailed Report\s+(.*?)(?=Detailed Report|Facility:|Performing Lab|Printed at:|={30,}|$)',
        clinical_document,
        re.DOTALL | re.IGNORECASE
    )

    for match in detailed_reports:
        content = match.group(1).strip()

        # Check if this contains imaging keywords
        if not re.search(IMAGING_KEYWORDS, content, re.IGNORECASE):
            continue

        # Extract study name - look for the FULL study name line
        # The study name is typically on the first non-empty line, may have leading whitespace
        lines = content.split('\n')
        study_name = "Imaging Study"
        for line in lines[:8]:  # Check first 8 lines (increased from 5)
            line = line.strip()
            if not line:
                continue

            # Match imaging keywords - must contain keyword AND not be metadata
            if re.search(IMAGING_KEYWORDS, line, re.IGNORECASE):
                # Exclude lines with metadata markers
                if not re.search(r'(?:Exm Date:|Req Phys:|Pat Loc:|Service:|Img Loc:|Provider:|Performed:)', line, re.IGNORECASE):
                    # Strip department prefix (e.g., "GENERAL RADIOLOGY")
                    # VA format uses 2+ spaces OR single space between dept and study
                    # Strategy: try double-space split first, fall back to keyword position
                    parts = re.split(r'\s{2,}', line.strip())
                    if len(parts) > 1:
                        # Take the last part that contains an imaging keyword
                        for part in reversed(parts):
                            if re.search(IMAGING_KEYWORDS, part.strip(), re.IGNORECASE):
                                study_name = part.strip()
                                break
                        else:
                            study_name = parts[-1].strip()
                    else:
                        # Single-space separated — find the imaging keyword and take from there
                        # This strips "GENERAL RADIOLOGY " prefix from "GENERAL RADIOLOGY MRI PROSTATE"
                        kw_match = re.search(IMAGING_KEYWORDS, line.strip(), re.IGNORECASE)
                        if kw_match:
                            study_name = line.strip()[kw_match.start():]
                        else:
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

            # Filter out reading physician metadata and patient contact info
            # Pattern: "READING PHYSICIAN: Name ID DATE TIME Timezone VHA..."
            impression = re.sub(
                r'READING PHYSICIAN:.*?(?=\d{1,2}\.\s+|$)',
                '',
                impression,
                flags=re.IGNORECASE | re.DOTALL
            )

            # Filter out VHA teleradiology contact info
            impression = re.sub(
                r'VHA National Teleradiology Program.*?(?=\d{1,2}\.\s+|$)',
                '',
                impression,
                flags=re.IGNORECASE | re.DOTALL
            )

            # Filter out patient/veteran disclaimers
            impression = re.sub(
                r'\(For Medical Practitioner Use Only\).*',
                '',
                impression,
                flags=re.IGNORECASE | re.DOTALL
            )
            impression = re.sub(
                r'Attention Patients\s*/\s*Veterans:.*',
                '',
                impression,
                flags=re.IGNORECASE | re.DOTALL
            )
            impression = re.sub(
                r'If you have questions or concerns.*',
                '',
                impression,
                flags=re.IGNORECASE | re.DOTALL
            )

            # Filter out phone numbers and numeric IDs
            impression = re.sub(r'\d{3}-\d{3}-\d{4}', '', impression)  # Phone numbers
            impression = re.sub(r'-?\d{10,}', '', impression)  # Long numeric IDs

            # Clean up whitespace
            impression = re.sub(r'\s+', ' ', impression)
            impression = impression.strip()

            # Skip if too short
            if len(impression) < 10:
                continue

            # CRITICAL: Extract stone measurements from findings (not just impression)
            # Pattern: "calculus...5-6 mm" or "stone measuring X mm" or "X mm calculus"
            stone_measurements = []
            stone_patterns = [
                r'((?:left|right)\s+kidney[^.]*calcul(?:us|i)[^.]*?(\d+(?:-\d+)?\s*(?:mm|cm)))',
                r'(echogenic\s+calcul(?:us|i)[^.]*?(?:measur(?:es|ing)|is)\s*(\d+(?:-\d+)?\s*(?:mm|cm)))',
                r'((?:left|right)\s+(?:renal|kidney)[^.]*stone[^.]*?(\d+(?:-\d+)?\s*(?:mm|cm)))',
                r'((\d+(?:-\d+)?\s*(?:mm|cm))\s+(?:calcul(?:us|i)|stone|nephrolith))',
                r'(By measurement,?\s*(?:it\s+is\s*)?(\d+(?:-\d+)?\s*(?:mm|cm)))',
            ]

            for pattern in stone_patterns:
                stone_match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
                if stone_match:
                    size = stone_match.group(2).strip() if stone_match.lastindex >= 2 else stone_match.group(1).strip()
                    # Normalize size
                    size = re.sub(r'\s+', '', size)
                    if size and size not in stone_measurements:
                        stone_measurements.append(size)

            # Extract kidney laterality for stone findings
            kidney_side = ""
            if re.search(r'left\s+kidney', content, re.IGNORECASE):
                kidney_side = "left"
            elif re.search(r'right\s+kidney', content, re.IGNORECASE):
                kidney_side = "right"

            # Append stone details to impression if found
            if stone_measurements:
                stone_detail = f"{kidney_side.title() + ' ' if kidney_side else ''}stone size: {', '.join(stone_measurements)}"
                impression = f"{impression}. FINDINGS: {stone_detail}"

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
                if 'FINDINGS:' not in impression:
                    impression = f"{impression}. FINDINGS: {cyst_finding}"
                else:
                    impression = f"{impression}; {cyst_finding}"

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
    # Each study starts with a study name line containing an imaging keyword
    # followed by a date in parentheses, e.g.:
    #   CT ABD & PELVIS W/O & W/ IV CONTRAST (11/12/2019):
    #   MRI PROSTATE W/O & W/ IV CONTRAST (8/29/25):
    #   US RENAL BILATERAL (3/15/25):
    # Study names can contain: letters, digits, spaces, /, &, -, W/O, W/
    # The date is always in parentheses: (M/D/YY) or (MM/DD/YYYY)
    study_pattern = r'([A-Za-z][A-Za-z0-9\s/&\-,.\(\)]+?\(\d{1,2}/\d{1,2}/\d{2,4}\)):?\s*\n(?:IMPRESSION:?\s*)?(.*?)(?=\n[A-Za-z][A-Za-z0-9\s/&\-,.]+?\(\d{1,2}/\d{1,2}/\d{2,4}\):?|={30,}|$)'

    for match in re.finditer(study_pattern, imaging_content, re.DOTALL):
        study_line = match.group(1).strip()
        impression = match.group(2).strip()

        # Parse study name and date from the matched study line
        study_date_match = re.match(r'(.+?)\s*\((\d{1,2}/\d{1,2}/\d{2,4})\)', study_line)
        if study_date_match:
            study_name = study_date_match.group(1).strip()
            date = study_date_match.group(2).strip()
        else:
            study_name = study_line.strip()
            date = ""

        # Clean up impression
        impression = re.sub(r'^IMPRESSION:\s*', '', impression, flags=re.IGNORECASE)
        impression = re.sub(r'\s+', ' ', impression)
        impression = impression.strip()

        # Skip if impression is too short (likely parsing error)
        if len(impression) < 10:
            continue

        # Format report
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

        # Only process if section contains actual imaging keywords (use module-level constant)
        if not re.search(IMAGING_KEYWORDS, section, re.IGNORECASE):
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

        # Only return if it contains actual imaging keywords (use module-level constant)
        if not re.search(IMAGING_KEYWORDS, imaging_text, re.IGNORECASE):
            return ""

        # Clean up whitespace
        imaging_text = re.sub(r' +', ' ', imaging_text)
        imaging_text = re.sub(r'\n{3,}', '\n\n', imaging_text)
        return imaging_text

    return ""


def extract_external_imaging(clinical_document: str) -> list:
    """
    Extract imaging from external/non-VA facilities (BAMC, SAMC, civilian hospitals).

    These reports have a simpler format:
    BAMC Prostate MRI
    27 mL
    Right anterior PIRADS 4

    Or in note context:
    Prostate MRI (BAMC):
    - 27 mL
    - Right anterior PIRADS 4

    Returns:
        List of imaging report strings
    """
    imaging_reports = []

    # Pattern 1: "[FACILITY] [Study Type] MRI/CT/US" followed by findings
    external_pattern = r'(?:^|\n)([A-Z]{2,5})\s+(Prostate|Kidney|Bladder|Renal)\s+(MRI|CT|US|Ultrasound)\s*\n((?:[^\n]+\n?){1,5}?)(?=\n\s*(?:PAST|MEDICATIONS|ALLERGIES|===|$)|\n\n)'

    for match in re.finditer(external_pattern, clinical_document, re.IGNORECASE | re.MULTILINE):
        facility = match.group(1).upper()
        body_part = match.group(2).strip()
        modality = match.group(3).upper()
        findings_block = match.group(4).strip()

        if not findings_block:
            continue

        # Parse findings
        findings = []
        for line in findings_block.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('==='):
                # Remove bullet markers
                line = re.sub(r'^[-•]\s*', '', line)
                if line:
                    findings.append(line)

        if not findings:
            continue

        # Build report
        study_name = f"{facility} {body_part} {modality}"
        findings_text = '; '.join(findings)
        report = f"{study_name}:\n{findings_text}"

        imaging_reports.append(report)

    # Pattern 2: "Prostate MRI" within pathology section (BAMC format)
    # Look for pattern after "Prostate Cancer Biopsy at [FACILITY]"
    pathology_mri_pattern = r'(?:^|\n)([A-Z]{2,5})\s+Prostate\s+MRI\s*\n((?:[^\n]+\n?){1,3}?)(?=\n\s*(?:PAST|MEDICATIONS|$)|\n\n)'

    for match in re.finditer(pathology_mri_pattern, clinical_document, re.IGNORECASE | re.MULTILINE):
        facility = match.group(1).upper()
        findings_block = match.group(2).strip()

        if not findings_block:
            continue

        findings = []
        for line in findings_block.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                line = re.sub(r'^[-•]\s*', '', line)
                if line:
                    findings.append(line)

        if findings:
            study_name = f"{facility} Prostate MRI"
            findings_text = '; '.join(findings)
            report = f"{study_name}:\n{findings_text}"

            # Avoid duplicates
            if report not in imaging_reports:
                imaging_reports.append(report)

    return imaging_reports


def extract_cprs_format_imaging(clinical_document: str) -> list:
    """
    Extract CPRS "report-verified" format imaging.

    Layout (one study per block):

        Exam Date/Time
         05/07/2026 10:44
        Procedure Name
         MRI, PROSTATE W/O & W/CONTRAST
        Reason for Study
         Multiparametric study
        Clinical History
         Elevated PSA
        Impression


         Moderate transitional zone hypertrophy.  No suspicious prostate lesion (no
         PI-RADS 3-5 lesion).

         Signed by DASHARTHA HARSEWAK, MD on 5/12/2026 10:14 AM CDT
        Report
         EXAM: MRI, PROSTATE W/O & W/CONTRAST
         ...

    Each "header" is a bareword line (e.g. "Procedure Name"); the value
    follows on one or more indented lines. The Impression block ends at
    "Signed by", "Report", "Facility:", "Printed at:", a "====" divider,
    or the start of the next study ("Exam Date/Time").

    Returns:
        List of imaging report strings (one per study).
    """
    imaging_reports: list = []

    # Anchor on "Procedure Name" so we don't accidentally pick up sections
    # that have "Exam Date/Time" but no procedure (lab specimens etc.).
    # Capture (in order):
    #   1. The procedure value (study name)
    #   2. The optional Exam Date/Time block — looked up separately, since
    #      it can appear BEFORE Procedure Name in this layout.
    block_pat = re.compile(
        r'^Procedure Name\s*\n'
        r'(?P<study>[^\n]+(?:\n[ \t]+[^\n]+)*)\n'
        r'(?P<rest>.*?)'
        r'(?=^Procedure Name\s*$|^={30,}\s*$|^Facility:|^Printed at:|\Z)',
        re.MULTILINE | re.DOTALL,
    )

    impression_pat = re.compile(
        r'^Impression\s*\n'
        r'(?P<imp>.*?)'
        r'(?=^Report\s*$|^Signed by |^Facility:|^Printed at:|^={30,}\s*$|\Z)',
        re.MULTILINE | re.DOTALL,
    )

    # Walk the document looking for blocks. For each block we also
    # look BACK at the preceding ~10 lines for an "Exam Date/Time" header
    # since CPRS places it just before Procedure Name.
    for match in block_pat.finditer(clinical_document):
        study_raw = match.group('study').strip()
        # Collapse multi-line study name to a single line and strip CPRS's
        # leading single-space indent.
        study_name = re.sub(r'\s+', ' ', study_raw).strip()

        # Must contain an imaging keyword — otherwise skip (filters out
        # non-imaging procedures like dental extractions that share this
        # bareword-header layout).
        if not re.search(IMAGING_KEYWORDS, study_name, re.IGNORECASE):
            continue

        rest = match.group('rest')

        # Date: look in the 400 chars BEFORE this "Procedure Name" line
        # for a date in any of three layouts CPRS uses, in priority order:
        #   1. "Exam Date/Time\n MM/DD/YYYY HH:MM"   (explicit label)
        #   2. A bareword "MM/DD/YYYY[ HH:MM]" line  sitting on its own
        #      immediately before "Procedure Name". Some VA exports skip
        #      the label entirely and just stamp the date+time on a
        #      single line above the block. Without this branch the
        #      block emerges as an undated MRI in the rendered note.
        #   3. "Exm Date:" / "Date Reported:" / "Date Verified:" inline
        #      inside the rest block (last-ditch fallback).
        block_start = match.start()
        prefix = clinical_document[max(0, block_start - 400):block_start]
        date_str = ""
        prefix_match = re.search(
            r'Exam Date/Time\s*\n[ \t]+(\d{1,2}/\d{1,2}/\d{2,4}(?:[ \t]+\d{1,2}:\d{2})?)',
            prefix,
        )
        if prefix_match:
            date_str = prefix_match.group(1).strip()
        if not date_str:
            # Bareword date line right before Procedure Name. Match
            # against the TAIL of the prefix so we don't grab an
            # earlier unrelated date elsewhere in the 400-char window.
            bareword_match = re.search(
                r'(?:^|\n)\s*'
                r'(\d{1,2}/\d{1,2}/\d{2,4})'
                r'(?:[ \t]+\d{1,2}:\d{2}(?:\s*(?:AM|PM))?)?'
                r'\s*\n\s*\Z',
                prefix,
                re.IGNORECASE,
            )
            if bareword_match:
                date_str = bareword_match.group(1).strip()
        if not date_str:
            inline_match = re.search(
                r'(?:Exm Date|Date Reported|Date Verified):\s*'
                r'([A-Z]{3}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})',
                rest,
                re.IGNORECASE,
            )
            if inline_match:
                date_str = inline_match.group(1).strip()

        # Normalize the date to just MM/DD/YYYY (strip the time component
        # if present) so the downstream dedupe key matches other formats.
        if date_str:
            date_only = re.match(r'(\d{1,2}/\d{1,2}/\d{2,4})', date_str)
            if date_only:
                date_str = date_only.group(1)

        # Impression: find the impression block within `rest`.
        imp_match = impression_pat.search(rest)
        if not imp_match:
            continue
        impression = imp_match.group('imp')

        # Strip CPRS's per-line leading space and collapse blank-line runs.
        impression_lines = [ln.strip() for ln in impression.split('\n')]
        # Drop trailing "Signed by ..." that may have leaked past the lookahead.
        impression_lines = [
            ln for ln in impression_lines if not ln.startswith('Signed by ')
        ]
        impression = ' '.join(ln for ln in impression_lines if ln).strip()

        # Filter out boilerplate that occasionally bleeds in.
        impression = re.sub(
            r'\(For Medical Practitioner Use Only\).*', '', impression,
            flags=re.IGNORECASE,
        )
        impression = re.sub(
            r'Attention Patients\s*/\s*Veterans:.*', '', impression,
            flags=re.IGNORECASE,
        )
        impression = re.sub(r'\s+', ' ', impression).strip()

        if len(impression) < 10:
            continue

        if date_str:
            report = f"{study_name} ({date_str}):\nIMPRESSION: {impression}"
        else:
            report = f"{study_name}:\nIMPRESSION: {impression}"

        imaging_reports.append(report)

    return imaging_reports


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
