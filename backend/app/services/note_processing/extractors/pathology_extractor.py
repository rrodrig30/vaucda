"""
Pathology Report Extractor

Extracts pathology reports from SURGICAL PATHOLOGY format.
"""

import re


def extract_pathology(clinical_document: str) -> str:
    """
    Extract pathology reports from SURGICAL PATHOLOGY sections.

    VA SURGICAL PATHOLOGY format example:
    ---- SURGICAL PATHOLOGY ----
    Reporting Lab: AUDIE L. MURPHY MEMORIAL HOSP [CLIA# 45D0987942]
    PATHOLOGY REPORT         Accession No. FLOW 24 60
    Date obtained: Feb 02, 2024 15:57
    Specimen: LYMPH NODE BIOPSY

    FLOW CYTOMETRY DIAGNOSIS; Lymph Node:
       -Involved by B-Cell lymphoma (see comment).

    Args:
        clinical_document: Full clinical document

    Returns:
        Extracted pathology reports (date + diagnosis), or "" if not found
    """
    pathology_reports = []

    # Split by SURGICAL PATHOLOGY sections
    sections = re.split(r'-{4,}\s*SURGICAL PATHOLOGY\s*-{4,}', clinical_document, flags=re.IGNORECASE)

    for i, section in enumerate(sections):
        if i == 0:
            # First section is before any SURGICAL PATHOLOGY marker
            continue

        # Extract date
        date_match = re.search(r'Date obtained:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', section, re.IGNORECASE)
        date = date_match.group(1) if date_match else ""

        # Extract specimen type
        specimen_match = re.search(r'Specimen:\s*([^\n]+)', section, re.IGNORECASE)
        specimen = specimen_match.group(1).strip() if specimen_match else ""

        # Extract diagnosis
        # Look for common diagnosis headers: "DIAGNOSIS:", "FLOW CYTOMETRY DIAGNOSIS:", "FINAL DIAGNOSIS:", etc.
        # CRITICAL: Exclude "PREOPERATIVE DIAGNOSIS", "OPERATIVE DIAGNOSIS", "POSTOPERATIVE DIAGNOSIS"
        diagnosis_match = re.search(
            r'(?:FINAL\s+|FLOW\s+CYTOMETRY\s+|FISH\s+)?DIAGNOSIS(?!\s*:\s*$)[:\s;]*([^\n]+(?:\n(?!\s*(?:Comment|Note|Clinical|Reporting))[^\n]+)*)',
            section,
            re.IGNORECASE | re.MULTILINE
        )

        # Skip if it's a surgical diagnosis (preoperative, operative, postoperative)
        if diagnosis_match:
            # Check if this is preceded by PREOPERATIVE, OPERATIVE, or POSTOPERATIVE
            match_pos = diagnosis_match.start()
            preceding_text = section[max(0, match_pos-30):match_pos]
            if any(term in preceding_text.upper() for term in ['PREOPERATIVE', 'POSTOPERATIVE', 'OPERATIVE FINDINGS']):
                continue

        if diagnosis_match:
            diagnosis = diagnosis_match.group(1).strip()

            # Skip if diagnosis is empty or only contains metadata markers
            if not diagnosis or len(diagnosis) < 5:
                continue

            # Filter out VA metadata lines from diagnosis
            diagnosis_lines = []
            for line in diagnosis.split('\n'):
                line = line.strip()
                # Skip metadata lines
                if any([
                    line.startswith('-' * 5),  # Dash separators
                    line.startswith('=' * 5),  # Equals separators
                    not line,  # Empty lines
                    'OPERATIVE FINDINGS' in line,
                    'POSTOPERATIVE DIAGNOSIS' in line,
                    'PREOPERATIVE DIAGNOSIS' in line,
                    'Surgeon/physician' in line,
                    'Accession No' in line,
                ]):
                    continue
                diagnosis_lines.append(line)

            if not diagnosis_lines:
                continue

            diagnosis = '\n'.join(diagnosis_lines)

            # Clean up: remove excessive whitespace
            diagnosis = re.sub(r' +', ' ', diagnosis)
            diagnosis = re.sub(r'\n{3,}', '\n', diagnosis)

            # Format: Date | Specimen | Diagnosis
            if date and diagnosis:
                report = f"{date} - {specimen}: {diagnosis}" if specimen else f"{date}: {diagnosis}"
                pathology_reports.append(report)
            elif diagnosis:
                report = f"{specimen}: {diagnosis}" if specimen else diagnosis
                pathology_reports.append(report)

    # Also extract colonoscopy findings
    colonoscopy_results = extract_colonoscopy_findings(clinical_document)
    if colonoscopy_results:
        pathology_reports.append(colonoscopy_results)

    if not pathology_reports:
        return ""

    return '\n\n'.join(pathology_reports)


def extract_pathology_from_note(note_content: str) -> str:
    """
    Extract pathology section from a clinical note (alternative format).

    Some notes may have embedded pathology results in a "Pathology:" section.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted pathology text, or "" if not found
    """
    # Pattern: "Pathology:" followed by content
    pattern = r'(?:Pathology|PATHOLOGY|Path):\s*(.*?)(?=\n\s*(?:MEDICATIONS:|ALLERGIES:|ASSESSMENT:|PLAN:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        path_text = match.group(1).strip()

        # Filter out VA metadata and empty surgical report sections
        va_metadata_patterns = [
            r'^\s*-{10,}\s*$',  # Lines with just dashes
            r'^\s*={10,}\s*$',  # Lines with just equals signs
            r'^\s*PREOPERATIVE DIAGNOSIS:\s*$',  # Empty preop diagnosis
            r'^\s*OPERATIVE FINDINGS:\s*$',  # Empty operative findings
            r'^\s*POSTOPERATIVE DIAGNOSIS:\s*$',  # Empty postop diagnosis
            r'^\s*Surgeon/physician:.*$',  # Surgeon info
            r'^\s*Accession No\..*$',  # Accession numbers
            r'^\s*PATHOLOGY REPORT\s+Accession.*$',  # Pathology report header with accession
            r'^\s*Specimen ID:.*$',  # Specimen IDs
            r'^\s*Body Site:.*$',  # Body site lines when standalone
        ]

        lines = path_text.split('\n')
        filtered_lines = []

        for line in lines:
            # Check if line matches any metadata pattern
            is_metadata = False
            for pattern_str in va_metadata_patterns:
                if re.match(pattern_str, line, re.IGNORECASE):
                    is_metadata = True
                    break

            if not is_metadata and line.strip():
                filtered_lines.append(line)

        path_text = '\n'.join(filtered_lines)

        # Remove ** markdown formatting
        path_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', path_text)
        # Clean up whitespace
        path_text = re.sub(r' +', ' ', path_text)
        path_text = re.sub(r'\n{3,}', '\n\n', path_text)
        return path_text.strip()

    return ""


def extract_colonoscopy_findings(clinical_document: str) -> str:
    """
    Extract colonoscopy pathology findings from Provider Narrative sections.

    Pattern: Look for "History of colonoscopy" Provider Narratives with Note Narrative containing pathology findings.

    Args:
        clinical_document: Full clinical document

    Returns:
        Extracted colonoscopy findings, or "" if not found
    """
    colonoscopy_findings = []

    # Look for colonoscopy Provider Narrative sections
    # Pattern: "History of colonoscopy" followed by "Note Narrative" with findings
    pattern = r'Provider Narrative\s+History of colonoscopy.*?Note Narrative\s+(.*?)(?=Exposures|Facility:|Provider Narrative|={30,}|$)'

    for match in re.finditer(pattern, clinical_document, re.IGNORECASE | re.DOTALL):
        narrative = match.group(1).strip()

        # Clean up the narrative
        narrative = re.sub(r'\s+', ' ', narrative)

        # Skip if narrative is empty or too short
        if len(narrative) < 10:
            continue

        # Extract date if present
        date_match = re.search(r'(?:Last done in|done in|in)\s+(\d{4})', narrative, re.IGNORECASE)
        date = date_match.group(1) if date_match else ""

        # Format the finding
        if date:
            colonoscopy_findings.append(f"Colonoscopy ({date}): {narrative}")
        else:
            colonoscopy_findings.append(f"Colonoscopy: {narrative}")

    if not colonoscopy_findings:
        return ""

    return '\n\n'.join(colonoscopy_findings)
