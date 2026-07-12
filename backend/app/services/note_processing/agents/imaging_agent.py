"""
Imaging Agent

Combines and summarizes imaging results.
"""

import re
from typing import List, Dict, Optional
from ..llm_helper import combine_sections_with_llm
from .history_cleaners import clean_llm_commentary


# Break a run-together numbered impression ("1. X 2. Y 3. Z") so each item
# starts on its own line. Matches " N. " (1-2 digits) only when followed by a
# capital letter or "(" — so decimals (7.1), "US-3", and "(SEE NOTE 1.)" are
# left intact — and only reflows lines that actually carry >=2 such markers.
_ENUM_BREAK = re.compile(r'\s+(?=\d{1,2}\.\s+[A-Z(])')
_ENUM_HAS2 = re.compile(r'\d{1,2}\.\s+[A-Z(].*?\d{1,2}\.\s+[A-Z(]')


def _break_enumerated_findings(text: str) -> str:
    if not text:
        return text
    out = []
    for line in text.split('\n'):
        if _ENUM_HAS2.search(line):
            line = _ENUM_BREAK.sub('\n', line)
        out.append(line)
    return '\n'.join(out)


def _render_procedure_imaging_entries(procedure_findings) -> str:
    """Render cystoscopy / urodynamics / DEXA findings as IMAGING-style
    entries (STUDY (DATE):\n<finding>). These are diagnostic procedures
    with imaging-like findings but live outside the radiology pipeline
    in `clinical_timeline.extract_procedure_findings`. Surfacing them in
    the IMAGING section keeps them visible at a glance and ensures the
    date travels with the finding (the HPI prose was previously dropping
    the date because the skeleton's free-text formatter could lose it)."""
    if not procedure_findings:
        return ""
    # Categories worth promoting to IMAGING. Pure pathology/biopsy stays
    # in the PATHOLOGY section; surgical procedures (TURP, TURBT) belong
    # in PSH.
    promote = {
        "cystoscopy": "CYSTOSCOPY",
        "cystourethroscopy": "CYSTOURETHROSCOPY",
        "urodynamics": "URODYNAMICS",
        "dexa": "DEXA",
    }
    seen = set()
    lines: List[str] = []
    # Sort newest first (date_key is the sortable form populated by the
    # extractor; falls back to "0" for undated).
    sorted_pf = sorted(
        procedure_findings,
        key=lambda f: (f.date_key or "0"),
        reverse=True,
    )
    for pf in sorted_pf:
        proc_label = promote.get(pf.procedure.lower())
        if not proc_label:
            continue
        if not pf.finding:
            continue
        date_disp = pf.date_display or "(undated)"
        key = (proc_label, date_disp, pf.finding[:60].lower())
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{proc_label} ({date_disp}):\n{pf.finding}\n")
    return "\n".join(lines)


def synthesize_imaging(
    document_imaging: str,
    gu_notes: List[Dict[str, str]],
    procedure_findings: Optional[List] = None,
) -> str:
    """
    Synthesize imaging results from document-level extraction and notes.

    Args:
        document_imaging: Imaging from document RADIOLOGY sections
        gu_notes: List of GU note dictionaries
        procedure_findings: Optional list of ProcedureFinding from the
            clinical_timeline. Cystoscopy / urodynamics / DEXA entries
            are appended to the imaging output so providers see them
            alongside radiology and the date always travels with the
            finding.

    Returns:
        Summarized imaging results in reverse chronological order
    """
    return _break_enumerated_findings(_synthesize_imaging_body(
        document_imaging, gu_notes, procedure_findings))


def _synthesize_imaging_body(
    document_imaging: str,
    gu_notes: List[Dict[str, str]],
    procedure_findings: Optional[List] = None,
) -> str:
    procedure_block = _render_procedure_imaging_entries(procedure_findings)

    # Document-level extraction wins when available. extract_imaging()
    # already produces the canonical "STUDY (DATE):\nIMPRESSION: ..."
    # format with cross-note dedup and reverse-chronological sort. Feeding
    # this PLUS each gu_note's per-note "Imaging" field to the LLM
    # combiner produced an output where the LLM kept "Impression: ..."
    # lines but dropped every study-name and date header — turning a
    # 4-study clinical record into four anonymous impressions. The
    # document-level extractor already aggregates across all source notes,
    # so the per-note path is redundant when it succeeds.
    if document_imaging and document_imaging.strip():
        if procedure_block:
            return f"{procedure_block}\n{document_imaging}"
        return document_imaging

    all_imaging = []
    for note in gu_notes:
        if note.get("Imaging"):
            all_imaging.append(note["Imaging"])

    if not all_imaging:
        return procedure_block

    if len(all_imaging) == 1:
        # Return as-is - extractor already formats correctly
        body = all_imaging[0]
        return f"{procedure_block}\n{body}" if procedure_block else body

    instructions = """Combine and summarize these imaging results.
- Include: Study name, Date, Impression
- Remove duplicates
- Sort by date (most recent first)
- Keep summaries concise but clinically complete
- Focus on urologically relevant imaging

CRITICAL: Provide ONLY the imaging results. NO meta-commentary, NO explanations, NO statements like "No recent urologic imaging provided". Just the imaging data."""

    synthesized_imaging = combine_sections_with_llm("Imaging Results", all_imaging, instructions)

    # Clean any LLM meta-commentary
    cleaned = clean_llm_commentary(synthesized_imaging)

    # Return as-is - don't reformat since extractor already formatted correctly
    return f"{procedure_block}\n{cleaned}" if procedure_block else cleaned


def _format_imaging_report(imaging_text: str) -> str:
    """
    Format imaging report to numbered bullet points.

    Converts:
        CT RENAL STONE (ABD/PEL WO CONTRAST) (MAY 05, 2025):
        IMPRESSION: 1. Finding... 2. Another finding...

    To:
        CT RENAL STONE (ABD/PEL WO CONTRAST) - May 05, 2025:
        1. Finding...
        2. Another finding...
    """
    import re
    from datetime import datetime

    if not imaging_text:
        return ""

    lines = []
    current_study = None

    # Split into individual studies/reports
    for line in imaging_text.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Check if this is a study header (contains date pattern)
        date_pattern = r'\(([A-Z]{3}\s+\d{1,2},\s+\d{4})\)'
        date_match = re.search(date_pattern, line)

        if date_pattern and ':' in line and date_match:
            # Format study header
            study_name = line.split('(')[0].strip()
            date_str = date_match.group(1)

            # Convert date to proper format (May 05, 2025)
            try:
                date_obj = datetime.strptime(date_str, '%b %d, %Y')
                formatted_date = date_obj.strftime('%B %d, %Y')
            except:
                try:
                    date_obj = datetime.strptime(date_str, '%B %d, %Y')
                    formatted_date = date_obj.strftime('%B %d, %Y')
                except:
                    formatted_date = date_str

            lines.append(f"{study_name} - {formatted_date}:")
            current_study = study_name
        elif 'IMPRESSION:' in line:
            # Remove IMPRESSION: label and process findings
            findings_text = line.replace('IMPRESSION:', '').strip()
            # Split by numbered findings
            findings = re.split(r'(\d+\.)', findings_text)
            for i in range(1, len(findings), 2):
                if i + 1 < len(findings):
                    number = findings[i]
                    text = findings[i + 1].strip()
                    # Clean up redundant phrasing
                    text = re.sub(r'^There (?:is|are)\s+(?:a\s+)?', '', text)
                    lines.append(f"{number} {text}")
        elif re.match(r'^\d+\.', line):
            # Already numbered finding
            lines.append(line)
        elif current_study:
            # Continuation of previous finding or additional text
            if lines and re.match(r'^\d+\.', lines[-1]):
                # Append to previous finding
                lines[-1] += ' ' + line
            else:
                lines.append(line)

    return '\n'.join(lines)
