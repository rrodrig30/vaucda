"""
Note Identifier

Splits clinical documents into GU and non-GU notes based on STANDARD TITLE markers.
"""

import re
from typing import Dict, List
from datetime import datetime


def identify_notes(clinical_document: str) -> Dict[str, List[Dict[str, str]]]:
    """
    Split clinical document into GU (urology), non-GU notes, and consult requests.

    Notes are identified by "STANDARD TITLE:" markers. Urology notes have
    "STANDARD TITLE: UROLOGY" (case-insensitive).

    Consult requests are identified by "Provisional Diagnosis:" and
    "Reason for Consult Request:" markers (VA consult request form format).

    Args:
        clinical_document: Raw clinical document text

    Returns:
        Dictionary with:
        {
            "gu_notes": [
                {"title": "UROLOGY", "date": "...", "content": "..."},
                ...
            ],
            "non_gu_notes": [
                {"title": "SLEEP MEDICINE", "date": "...", "content": "..."},
                ...
            ],
            "consult_requests": [
                {"title": "CONSULT REQUEST", "date": "...", "content": "..."},
                ...
            ]
        }

    Each note dictionary contains:
        - title: The specialty from STANDARD TITLE (or "CONSULT REQUEST")
        - date: Note date if extractable, otherwise ""
        - content: Full note content from STANDARD TITLE to next STANDARD TITLE
    """
    gu_notes = []
    non_gu_notes = []
    consult_requests = []

    # First, check for consult request forms (invariant VA format)
    # These are identified by "Provisional Diagnosis:" and either
    # "Reason for Consult Request:" or "Reason For Request:"
    has_provisional = "Provisional Diagnosis:" in clinical_document
    has_reason = ("Reason for Consult Request:" in clinical_document or
                  "Reason For Request:" in clinical_document)

    if has_provisional and has_reason:
        # Split by "===== END =====" markers to handle multiple consult requests
        consult_sections = re.split(r'=+\s*END\s*=+', clinical_document)

        for section in consult_sections:
            section_has_provisional = "Provisional Diagnosis:" in section
            section_has_reason = ("Reason for Consult Request:" in section or
                                 "Reason For Request:" in section)

            if section_has_provisional and section_has_reason:
                # Extract date from "Clinically Ind. Date:"
                date = ""
                date_match = re.search(r'Clinically Ind\. Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})', section)
                if date_match:
                    date = date_match.group(1).strip()

                consult_requests.append({
                    "title": "CONSULT REQUEST",
                    "date": date,
                    "content": section.strip()
                })

    # Split by "STANDARD TITLE:" markers (case-insensitive)
    # Use lookahead to keep the marker in each section
    sections = re.split(r'(?=STANDARD TITLE:)', clinical_document, flags=re.IGNORECASE)

    for section in sections:
        if not section.strip():
            continue

        # Extract the title after "STANDARD TITLE:"
        title_match = re.search(r'STANDARD TITLE:\s*([^\n]+)', section, re.IGNORECASE)
        if not title_match:
            # This section doesn't have a STANDARD TITLE marker (probably header/footer)
            continue

        title = title_match.group(1).strip()

        # Extract date if present
        # Common VA formats: "Date Signed: 10/17/2025", "Date/Time: 10/17/2025 14:30"
        date = ""
        date_match = re.search(r'Date(?:\s+Signed|\s*[:/]\s*Time)?:\s*(\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?)', section, re.IGNORECASE)
        if date_match:
            date = date_match.group(1).strip()

        # Create note object
        note = {
            "title": title,
            "date": date,
            "content": section.strip()
        }

        # Classify as GU or non-GU
        if re.search(r'\bUROLOGY\b', title, re.IGNORECASE):
            gu_notes.append(note)
        else:
            non_gu_notes.append(note)

    return {
        "gu_notes": gu_notes,
        "non_gu_notes": non_gu_notes,
        "consult_requests": consult_requests
    }


def get_note_summary(notes_dict: Dict[str, List[Dict[str, str]]]) -> str:
    """
    Generate a human-readable summary of identified notes.

    Args:
        notes_dict: Output from identify_notes()

    Returns:
        Formatted string summarizing note counts and titles
    """
    gu_count = len(notes_dict["gu_notes"])
    non_gu_count = len(notes_dict["non_gu_notes"])
    consult_count = len(notes_dict.get("consult_requests", []))

    summary = f"Identified {gu_count} GU note(s), {non_gu_count} non-GU note(s), and {consult_count} consult request(s)\n\n"

    if consult_count > 0:
        summary += "CONSULT REQUESTS:\n"
        for i, note in enumerate(notes_dict["consult_requests"], 1):
            date_str = f" ({note['date']})" if note['date'] else ""
            summary += f"  {i}. {note['title']}{date_str}\n"
        summary += "\n"

    if gu_count > 0:
        summary += "GU NOTES:\n"
        for i, note in enumerate(notes_dict["gu_notes"], 1):
            date_str = f" ({note['date']})" if note['date'] else ""
            summary += f"  {i}. {note['title']}{date_str}\n"
        summary += "\n"

    if non_gu_count > 0:
        summary += "NON-GU NOTES:\n"
        for i, note in enumerate(notes_dict["non_gu_notes"], 1):
            date_str = f" ({note['date']})" if note['date'] else ""
            summary += f"  {i}. {note['title']}{date_str}\n"

    return summary
