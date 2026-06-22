"""
Note Identifier

Splits clinical documents into GU and non-GU notes based on STANDARD TITLE markers.
"""

import re
from typing import Dict, List, Optional
from datetime import datetime


# Date patterns tried in priority order. The first one that matches wins.
# The captured group should yield the date string we want to store. Order
# reflects reliability: the VA "DATE OF NOTE:" stamp is the canonical
# date associated with a STANDARD TITLE block, so try that first.
_NOTE_DATE_PATTERNS = [
    # 1. "DATE OF NOTE: DEC 03, 2025@10:48" — canonical VA stamp.
    re.compile(
        r'DATE\s+OF\s+NOTE:\s*'
        r'([A-Za-z]{3,9}\s+\d{1,2}\s*,?\s*\d{4})'
        r'(?:@\d{1,2}:\d{2})?',
        re.IGNORECASE,
    ),
    # 2. "ENTRY DATE: DEC 03, 2025" — VA's secondary timestamp.
    re.compile(
        r'ENTRY\s+DATE:\s*'
        r'([A-Za-z]{3,9}\s+\d{1,2}\s*,?\s*\d{4})'
        r'(?:@\d{1,2}:\d{2}(?::\d{2})?)?',
        re.IGNORECASE,
    ),
    # 3. "Signed: 12/03/2025 11:14" — signature line (numeric date).
    re.compile(
        r'(?:^|\n)\s*Signed:\s*'
        r'(\d{1,2}/\d{1,2}/\d{2,4})'
        r'(?:\s+\d{1,2}:\d{2})?',
    ),
    # 4. "Date Signed: ..." / "Date/Time: ..." / "Date: ..." (numeric).
    re.compile(
        r'Date(?:\s+Signed|\s*[:/]\s*Time)?:\s*'
        r'(\d{1,2}/\d{1,2}/\d{2,4})'
        r'(?:\s+\d{1,2}:\d{2})?',
        re.IGNORECASE,
    ),
    # 5. "Date Signed: MON DD, YYYY" (text-month variant).
    re.compile(
        r'Date\s+Signed:\s*'
        r'([A-Za-z]{3,9}\s+\d{1,2}\s*,?\s*\d{4})',
        re.IGNORECASE,
    ),
    # 6. "Date Reported:" / "Report Released Date:" / "Date Verified:".
    re.compile(
        r'(?:Date\s+Reported|Report\s+Released\s+Date(?:/Time)?|Date\s+Verified):\s*'
        r'([A-Za-z]{3,9}\s+\d{1,2}\s*,?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})',
        re.IGNORECASE,
    ),
]


def _normalize_note_date(raw: str) -> str:
    """Normalize a captured date to "MON DD, YYYY" for consistent display.

    Accepts the formats matched by _NOTE_DATE_PATTERNS:
        "DEC 03, 2025"     -> "Dec 03, 2025"
        "12/03/2025"       -> "Dec 03, 2025"
        "12/03/25"         -> "Dec 03, 2025"  (2-digit year, pivot 50)
        "December 3, 2025" -> "Dec 03, 2025"
    Returns the raw input on parse failure so the note still has SOME
    date string rather than silently dropping it.
    """
    raw = raw.strip()
    if not raw:
        return ""
    for fmt_in, fmt_out in (
        ('%m/%d/%Y', '%b %d, %Y'),
        ('%m/%d/%y', '%b %d, %Y'),
        ('%b %d, %Y', '%b %d, %Y'),
        ('%b %d %Y', '%b %d, %Y'),
        ('%B %d, %Y', '%b %d, %Y'),
        ('%B %d %Y', '%b %d, %Y'),
    ):
        try:
            dt = datetime.strptime(raw.replace(',', ', ').replace('  ', ' '), fmt_in)
            return dt.strftime(fmt_out)
        except ValueError:
            continue
    # Last-ditch: collapse internal whitespace and return uppercase as-is.
    return ' '.join(raw.split())


def _extract_note_date(section: str) -> str:
    """Pull the most reliable date out of a STANDARD TITLE section.

    Tries `_NOTE_DATE_PATTERNS` in order; returns "" if none match.
    """
    for pat in _NOTE_DATE_PATTERNS:
        m = pat.search(section)
        if m:
            return _normalize_note_date(m.group(1))
    return ""


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
        # Iterate over EVERY "Provisional Diagnosis:" occurrence. Each one
        # is a candidate consult request. Don't split by "===== END ====="
        # — that delimiter is unreliable: VistA dumps in particular use
        # "MM/DD/YYYY HH:MM Local Title:" record boundaries instead of
        # equal-sign sections, so a single split would treat the whole
        # document as one giant consult region.
        from datetime import datetime, timedelta

        # Header that precedes each historical note in a VistA/CPRS dump:
        # "MM/DD/YYYY HH:MM  Local Title: <TITLE>". The note's true date
        # comes from this header — NOT from "Clinically Ind. Date" (which
        # is often absent) and NOT from "Date: ..." (which can be a note-
        # signed date months later).
        _note_header_re = re.compile(
            r'(\d{1,2})/(\d{1,2})/(\d{4})\s+\d{1,2}:\d{2}\s+Local Title:',
            re.IGNORECASE,
        )

        for prov_match in re.finditer(r'Provisional Diagnosis:', clinical_document):
            prov_idx = prov_match.start()

            # Find the nearest preceding "MM/DD/YYYY HH:MM Local Title:"
            # header. Its date is the consult's date.
            preceding = list(_note_header_re.finditer(
                clinical_document[:prov_idx]
            ))
            if not preceding:
                # No anchor header — fall back to Clinically Ind. Date if
                # present, else accept as undated (don't gate).
                date = ""
                ci_match = re.search(
                    r'Clinically Ind\. Date:\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})',
                    clinical_document[prov_idx:prov_idx + 2000],
                )
                if ci_match:
                    date = ci_match.group(1).strip()
                consult_dt = None
            else:
                anchor = preceding[-1]
                mm, dd, yyyy = int(anchor.group(1)), int(anchor.group(2)), int(anchor.group(3))
                try:
                    consult_dt = datetime(yyyy, mm, dd)
                    date = consult_dt.strftime("%b %d, %Y")
                except ValueError:
                    consult_dt = None
                    date = ""

            # Verify there's a matching "Reason for Consult Request" /
            # "Reason For Request" within ~3000 chars of this Provisional
            # Diagnosis (same record).
            window = clinical_document[prov_idx:prov_idx + 3000]
            if not (
                "Reason for Consult Request:" in window
                or "Reason For Request:" in window
            ):
                continue

            # Recency gate: a "consult request" older than 18 months is a
            # HISTORICAL consult, not the reason for today's visit.
            # Treating ancient consults as current routes the CC/HPI
            # pipeline through the consult flow with stale provisional-
            # diagnosis + multi-year-old ER narrative as the supposed
            # presenting complaint.
            if consult_dt is not None:
                if (datetime.now() - consult_dt) > timedelta(days=548):
                    continue

            # Build the consult body as content from the anchor header (if
            # any) forward through ~3000 chars or to the next note header.
            body_start = preceding[-1].start() if preceding else prov_idx
            next_header = _note_header_re.search(
                clinical_document, prov_idx + 1
            )
            body_end = next_header.start() if next_header else (prov_idx + 3000)
            body = clinical_document[body_start:body_end].strip()

            consult_requests.append({
                "title": "CONSULT REQUEST",
                "date": date,
                "content": body,
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

        # Extract date. The VA "DATE OF NOTE: MON DD, YYYY@HH:MM"
        # stamp is the canonical timestamp for a STANDARD TITLE block
        # — every clinic/consult note has one, and it's the date the
        # encounter actually occurred (vs the date the note was signed,
        # which can be days later). The helper tries that first, then
        # falls back through ENTRY DATE, Signed:, Date Signed:, etc.
        # Previous regex only matched MM/DD/YYYY numeric dates, so the
        # MON-DD-YYYY format that VA actually emits was silently
        # dropped — every note ended up with date="". Downstream HPI
        # synthesis then couldn't differentiate prior-visit snapshots
        # by time.
        date = _extract_note_date(section)

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
