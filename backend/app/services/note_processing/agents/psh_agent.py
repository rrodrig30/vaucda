"""
PSH (Past Surgical History) Agent

Combines surgical histories from all notes, including VA surgical data.
Formats as a numbered list with surgery dates.
"""

from typing import List, Dict, Tuple
import re
from ..llm_helper import combine_sections_with_llm


def _parse_surgery_with_date(surgery_line: str) -> Tuple[str, str]:
    """
    Parse a surgery line to extract surgery name and date.

    Handles formats:
    - "Left partial nephrectomy (7/8/2025)"
    - "TURP on 3/15/2024"
    - "Appendectomy - 2020"
    - "Cholecystectomy, 01/2019"

    Returns:
        Tuple of (surgery_name, date_string) - date may be empty string
    """
    surgery_line = surgery_line.strip()

    # Pattern 1: Date in parentheses at end "(MM/DD/YYYY)" or "(MM/DD/YY)"
    match = re.match(r'^(.+?)\s*\((\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4}|\d{4})\)\s*$', surgery_line)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern 2: "on MM/DD/YYYY" or "on MM/DD/YY"
    match = re.match(r'^(.+?)\s+on\s+(\d{1,2}/\d{1,2}/\d{2,4})\s*$', surgery_line, re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern 3: Date at end with dash "- MM/DD/YYYY" or "- YYYY"
    match = re.match(r'^(.+?)\s*[-–]\s*(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4}|\d{4})\s*$', surgery_line)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern 4: Date at end with comma ", MM/DD/YYYY" or ", YYYY"
    match = re.match(r'^(.+?),\s*(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4}|\d{4})\s*$', surgery_line)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Pattern 5: Just a date at end (MM/DD/YYYY format)
    match = re.match(r'^(.+?)\s+(\d{1,2}/\d{1,2}/\d{2,4})\s*$', surgery_line)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # No date found
    return surgery_line, ""


def _format_surgery_entry(surgery: str, date: str, number: int) -> str:
    """
    Format a surgery entry as a numbered line with date.

    Format: "N. Surgery Name (MM/DD/YYYY)"

    Args:
        surgery: Surgery name
        date: Date string (may be empty)
        number: Line number

    Returns:
        Formatted surgery line
    """
    surgery = surgery.strip()
    # Clean up surgery name - remove leading numbers/bullets if present
    surgery = re.sub(r'^[\d\.\-\*\)]+\s*', '', surgery)
    # Remove markdown formatting
    surgery = re.sub(r'\*\*([^*]+)\*\*', r'\1', surgery)
    # Capitalize first letter
    if surgery and not surgery[0].isupper():
        surgery = surgery[0].upper() + surgery[1:]

    if date:
        return f"{number}. {surgery} ({date})"
    else:
        return f"{number}. {surgery}"


# Canonical-name aliases. Surgical history coming from multiple sources
# (VistA SR section, per-visit prior-note PSH blurbs, HPI narrative
# scrapings) routinely names the same procedure several different ways:
#   "TURP"  /  "transurethral resection of prostate"  /  "TUR-P"
#   "Robotic prostatectomy"  /  "RALP"  /  "robot-assisted laparoscopic prostatectomy"
#   "TURBT" / "transurethral resection of bladder tumor"
# Exact-match dedup leaves all variants visible, so the rendered PSH
# shows the same procedure three times in a row. Each (regex, canonical
# name) pair below collapses to ONE canonical surgery for dedup
# purposes. The first variant seen still drives the displayed text.
_SURGERY_ALIASES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:robot[\s\-]?assisted|robotic)\s+(?:laparoscopic\s+)?"
                r"(?:radical\s+)?prostatectomy\b|\bRALP\b|\bRARP\b",
                re.IGNORECASE),
     "robotic prostatectomy"),
    (re.compile(r"\b(?:open\s+)?radical\s+prostatectomy\b|\bRRP\b",
                re.IGNORECASE),
     "radical prostatectomy"),
    (re.compile(r"\btrans[\s\-]?urethral\s+resection\s+of\s+(?:the\s+)?prostate\b|"
                r"\bTUR[\s\-]?P\b",
                re.IGNORECASE),
     "TURP"),
    (re.compile(r"\btrans[\s\-]?urethral\s+resection\s+of\s+(?:the\s+)?bladder"
                r"(?:\s+tumou?r)?\b|\bTURBT\b",
                re.IGNORECASE),
     "TURBT"),
    (re.compile(r"\b(?:laser\s+)?enucleation\s+of\s+(?:the\s+)?prostate\b|"
                r"\bHoLEP\b|\bThuLEP\b",
                re.IGNORECASE),
     "laser prostate enucleation (HoLEP/ThuLEP)"),
    (re.compile(r"\bUreteroscop(?:y|ies)\b|\bURS\b", re.IGNORECASE),
     "ureteroscopy"),
    (re.compile(r"\b(?:percutaneous\s+nephrolithotomy|PCNL)\b", re.IGNORECASE),
     "PCNL"),
    (re.compile(r"\b(?:shock\s+wave\s+lithotripsy|extracorporeal\s+shock\s+wave"
                r"\s+lithotripsy|ESWL|SWL)\b", re.IGNORECASE),
     "SWL"),
    (re.compile(r"\bcystolitholapaxy\b|\bcystolithotripsy\b|"
                r"\bbladder\s+stone\s+removal\b",
                re.IGNORECASE),
     "cystolitholapaxy"),
    (re.compile(r"\b(?:radical|partial|simple)?\s*nephrectomy\b", re.IGNORECASE),
     "nephrectomy"),
    (re.compile(r"\b(?:radical\s+)?cystectomy\b", re.IGNORECASE),
     "cystectomy"),
    (re.compile(r"\bvasectomy\b", re.IGNORECASE),
     "vasectomy"),
    (re.compile(r"\bcircumcision\b", re.IGNORECASE),
     "circumcision"),
    (re.compile(r"\borchiectomy\b|\borchidectomy\b", re.IGNORECASE),
     "orchiectomy"),
    (re.compile(r"\bhydrocelectomy\b", re.IGNORECASE),
     "hydrocelectomy"),
    (re.compile(r"\bvaricocelectomy\b", re.IGNORECASE),
     "varicocelectomy"),
    (re.compile(r"\bprostate\s+biops(?:y|ies)\b|\bTRUS\s*[-/]?\s*Bx\b|"
                r"\bMRI[\s\-]?fusion\s+biopsy\b|\bfusion\s+biopsy\b",
                re.IGNORECASE),
     "prostate biopsy"),
    (re.compile(r"\bcystoscop(?:y|ies)\b", re.IGNORECASE),
     "cystoscopy"),
    (re.compile(r"\bappendectomy\b", re.IGNORECASE),
     "appendectomy"),
    (re.compile(r"\bcholecystectomy\b", re.IGNORECASE),
     "cholecystectomy"),
    (re.compile(r"\binguinal\s+hernia\s+repair\b|\bherniorrhaphy\b",
                re.IGNORECASE),
     "inguinal hernia repair"),
    (re.compile(r"\bcataract\s+(?:extraction|surgery|removal)\b",
                re.IGNORECASE),
     "cataract surgery"),
]


def _surgery_canonical_key(surgery_name: str) -> str:
    """Return the canonical key for a surgery name, used purely for
    dedup. If no alias matches, fall back to an aggressive token-set
    normalization (lowercase, drop punctuation, drop laterality and
    common modifier words, sort tokens) so trivial wording differences
    collapse.
    """
    if not surgery_name:
        return ""
    # 1. Alias-table match
    for pat, canonical in _SURGERY_ALIASES:
        if pat.search(surgery_name):
            return canonical
    # 2. Aggressive token-set normalization
    s = surgery_name.lower()
    s = re.sub(r"\b(?:s/p|status\s+post|history\s+of|hx\s+of|"
               r"prior|remote|past)\b", "", s)
    s = re.sub(r"\b(?:left|right|bilateral|lt|rt|bilat|"
               r"approximately|around|circa|about|approx)\b", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    tokens = sorted(t for t in s.split() if t and not t.isdigit())
    return " ".join(tokens) or surgery_name.lower().strip()


def _prefer_more_specific(a: Tuple[str, str], b: Tuple[str, str]) -> Tuple[str, str]:
    """When two surgery entries share a canonical key, keep the more
    informative one. Prefer:
      1. The one that carries a date (vs no date)
      2. Among dated entries, the one with the more-precise date
         (full MM/DD/YYYY beats MM/YYYY beats YYYY)
      3. The one with the longer surgery-name text (e.g.
         "Left partial nephrectomy" beats "nephrectomy")
    """
    name_a, date_a = a
    name_b, date_b = b

    def _date_precision(d: str) -> int:
        if not d:
            return 0
        if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", d):
            return 3
        if re.match(r"^\d{1,2}/\d{4}$", d):
            return 2
        if re.match(r"^\d{4}$", d):
            return 1
        return 1

    pa, pb = _date_precision(date_a), _date_precision(date_b)
    if pa != pb:
        return a if pa > pb else b
    if len(name_a) != len(name_b):
        return a if len(name_a) > len(name_b) else b
    return a


def synthesize_psh(gu_notes: List[Dict[str, str]], non_gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize Past Surgical History from all notes.

    Per instructions: Combine PSH from all notes, including any surgery data
    from VA clinical documents.

    Output format: Numbered list with dates
    Example:
        1. Left partial nephrectomy (7/8/2025)
        2. TURP (3/15/2024)
        3. Appendectomy (2015)

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries

    Returns:
        Synthesized, enumerated PSH list with dates
    """
    # Collect all PSH entries
    all_psh = []

    for note in gu_notes:
        if note.get("PSH"):
            all_psh.append(note["PSH"])

    for note in non_gu_notes:
        if note.get("PSH"):
            all_psh.append(note["PSH"])

    if not all_psh:
        return ""

    # Parse all surgeries and their dates. Canonical-key dedup: when
    # two entries normalize to the same canonical surgery (e.g. "TURP"
    # and "transurethral resection of prostate"), keep the more
    # informative one (longer name and/or more precise date) and drop
    # the other.
    by_canonical: Dict[str, Tuple[str, str]] = {}  # canon_key -> (name, date)
    canon_order: List[str] = []                    # first-seen order

    for psh_block in all_psh:
        lines = psh_block.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip headers and section markers
            if any(header in line.upper() for header in ['PSH:', 'PAST SURGICAL HISTORY:', '===', '---']):
                continue

            # Parse surgery and date
            surgery_name, date_str = _parse_surgery_with_date(line)

            if not surgery_name:
                continue

            canon_key = _surgery_canonical_key(surgery_name)
            if not canon_key:
                continue

            new_entry = (surgery_name, date_str)
            if canon_key in by_canonical:
                # Duplicate canonical procedure — keep whichever entry
                # carries the better date / longer name.
                by_canonical[canon_key] = _prefer_more_specific(
                    by_canonical[canon_key], new_entry,
                )
            else:
                by_canonical[canon_key] = new_entry
                canon_order.append(canon_key)

    surgeries_with_dates = [by_canonical[k] for k in canon_order]
    seen_surgeries = set(by_canonical.keys())  # used by the LLM-path branch below

    # If we couldn't parse any surgeries locally, use LLM
    if not surgeries_with_dates and len(all_psh) > 1:
        instructions = """
Combine these surgical histories into a single, deduplicated list.
- Remove duplicate surgeries
- Preserve dates in format (MM/DD/YYYY) or (YYYY) at the end of each line
- Sort by date (most recent first) if dates are available
- Include ALL surgeries
- Format EACH surgery as: "Surgery Name (date)" - one per line
- If no date available, just list the surgery name

CRITICAL: Provide ONLY the surgical history list. NO meta-commentary, NO explanations, NO preamble.
Format example:
Left partial nephrectomy (7/8/2025)
TURP (3/15/2024)
Appendectomy (2015)
"""

        synthesized_psh = combine_sections_with_llm(
            section_name="Past Surgical History",
            section_instances=all_psh,
            instructions=instructions
        )

        if synthesized_psh:
            # Clean up LLM meta-commentary
            synthesized_psh = re.sub(r'^(Here is|Here are|I have combined|Note:).*?\n', '', synthesized_psh, flags=re.MULTILINE | re.IGNORECASE)
            synthesized_psh = re.sub(r'\n(Note:|I removed|Since there).*$', '', synthesized_psh, flags=re.DOTALL | re.IGNORECASE)

            # Re-parse the LLM output using the same canonical-key
            # dedup so the LLM cannot reintroduce duplicates the
            # deterministic pass already removed.
            for line in synthesized_psh.split('\n'):
                line = line.strip()
                if not line:
                    continue
                surgery_name, date_str = _parse_surgery_with_date(line)
                if not surgery_name:
                    continue
                canon_key = _surgery_canonical_key(surgery_name)
                if not canon_key:
                    continue
                new_entry = (surgery_name, date_str)
                if canon_key in by_canonical:
                    merged = _prefer_more_specific(by_canonical[canon_key], new_entry)
                    # If we picked up a better entry, replace in the
                    # ordered list in place.
                    if merged != by_canonical[canon_key]:
                        idx = canon_order.index(canon_key)
                        by_canonical[canon_key] = merged
                        surgeries_with_dates[idx] = merged
                else:
                    by_canonical[canon_key] = new_entry
                    canon_order.append(canon_key)
                    surgeries_with_dates.append(new_entry)
                    seen_surgeries.add(canon_key)

    # Sort by date (most recent first)
    def sort_key(item):
        surgery, date = item
        if not date:
            return (0, "")  # No date = sort to end

        # Try to parse various date formats
        import re
        # MM/DD/YYYY
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date)
        if match:
            month, day, year = match.groups()
            return (1, f"{year}{int(month):02d}{int(day):02d}")

        # MM/DD/YY
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{2})', date)
        if match:
            month, day, year = match.groups()
            full_year = f"20{year}" if int(year) < 50 else f"19{year}"
            return (1, f"{full_year}{int(month):02d}{int(day):02d}")

        # MM/YYYY
        match = re.match(r'(\d{1,2})/(\d{4})', date)
        if match:
            month, year = match.groups()
            return (1, f"{year}{int(month):02d}00")

        # YYYY only
        match = re.match(r'(\d{4})', date)
        if match:
            return (1, f"{match.group(1)}0000")

        return (0, date)

    surgeries_with_dates.sort(key=sort_key, reverse=True)

    # Format as numbered list
    formatted_lines = []
    for i, (surgery, date) in enumerate(surgeries_with_dates, 1):
        formatted_lines.append(_format_surgery_entry(surgery, date, i))

    return '\n'.join(formatted_lines)
