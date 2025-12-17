"""
Imaging Agent

Combines and summarizes imaging results.
"""

from typing import List, Dict
from ..llm_helper import combine_sections_with_llm
from .history_cleaners import clean_llm_commentary


def synthesize_imaging(document_imaging: str, gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize imaging results from document-level extraction and notes.

    Args:
        document_imaging: Imaging from document RADIOLOGY sections
        gu_notes: List of GU note dictionaries

    Returns:
        Summarized imaging results in reverse chronological order
    """
    all_imaging = []

    if document_imaging:
        all_imaging.append(document_imaging)

    for note in gu_notes:
        if note.get("Imaging"):
            all_imaging.append(note["Imaging"])

    if not all_imaging:
        return ""

    if len(all_imaging) == 1:
        # Return as-is - extractor already formats correctly
        return all_imaging[0]

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
    return cleaned


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
