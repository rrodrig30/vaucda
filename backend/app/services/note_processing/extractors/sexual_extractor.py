"""
Sexual History Extractor

Extracts sexual history from clinical notes.
"""

import re


# Header variations seen in real clinic notes. Order does not matter
# (regex alternation is tried left-to-right but we use a broad
# alternation that covers them all).
_HEADER_RE = re.compile(
    r'(?:'
    r'\*{0,2}\s*'                       # optional **bold** prefix
    r'(?:'
    r'Sexual\s+History|'
    r'Sexual\s+Hx|'
    r'Sex\s+Hx|'
    r'Sexual(?!\s+(?:abuse|assault|orientation))|'
    r'SEXUAL|'
    r'SHx|'
    r'SHX'
    r')'
    r'\s*\*{0,2}\s*[:\-\u2013\u2014]'   # colon / hyphen / en-dash / em-dash
    r')',
    re.IGNORECASE,
)

# Section boundaries that mark the end of the sexual history block.
# Broader than before — captures more common chart layouts including
# uppercase, lowercase, mixed-case, and abbreviated forms. The leading
# `\*{0,2}` allows a markdown **PMH:** style bold-wrapped header to
# trigger the terminator just as a plain `PMH:` would.
_TERMINATOR_RE = re.compile(
    r'\n\s*\*{0,2}\s*'
    r'(?:'
    r'PAST\s+MEDICAL\s+HISTORY|PMH|'
    r'PAST\s+SURGICAL\s+HISTORY|PSH|Surgical\s+(?:Hx|History)|'
    r'FAMILY\s+HISTORY|FHx|Family\s+Hx|'
    r'SOCIAL\s+HISTORY|SHx?\s+\(social\)|Social\s+Hx|'
    r'MEDICATIONS|MEDS|Current\s+Medications|'
    r'ALLERGIES|ADVERSE\s+REACTIONS|'
    r'REVIEW\s+OF\s+SYSTEMS|ROS|'
    r'PHYSICAL\s+EXAM|PHYSICAL\s+EXAMINATION|EXAM|PE\b|VITAL\s+SIGNS|'
    r'ASSESSMENT|IMPRESSION|'
    r'PLAN|RECOMMENDATIONS|'
    r'LABS?\b|LABORATORY|IMAGING|RADIOLOGY|'
    r'PATHOLOGY|'
    r'IPSS|'
    r'CHIEF\s+COMPLAINT|REASON\s+FOR\s+VISIT|HPI|'
    r'={3,}|-{3,}|_{3,}|\*{3,}'         # horizontal-rule terminators
    r')'
    r'\s*\*{0,2}\s*'
    r'(?:[:\s\-\u2013\u2014]|$)',
    re.IGNORECASE,
)


def extract_sexual(note_content: str) -> str:
    """
    Extract Sexual History from a clinical note.

    Recognized header variants:
        Sexual History:          Sexual Hx:
        SEXUAL HISTORY:          Sex Hx:
        Sexual:                  SHx:
        **Sexual History:**      SEXUAL -

    Plus en-dash and em-dash separators after the header.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted sexual history text, or "" if not found
    """
    if not note_content:
        return ""

    match = _HEADER_RE.search(note_content)
    if not match:
        return ""

    body_start = match.end()
    after = note_content[body_start:]

    term = _TERMINATOR_RE.search(after)
    body = after[:term.start()] if term else after

    # Take at most ~30 lines or 2000 chars — sexual histories are short
    body = body[:2000]
    body = '\n'.join(body.split('\n')[:30])

    # Strip leading markdown bold/italic remnants left by header
    # patterns like `**Sexual History:**` where the closing `**` lives
    # at the start of the body capture.
    body = re.sub(r'^\s*\*{1,3}\s*', '', body)

    # Clean up whitespace
    body = re.sub(r'[ \t]+', ' ', body).strip()
    body = re.sub(r'\n{3,}', '\n\n', body)

    # Drop trailing fragments that look like a stray section header
    # leftover after the terminator (defensive — terminator should have
    # caught these but real notes are messy).
    body = re.sub(
        r'\n\s*(?:PAST|MEDIC|ALLERG|FAMIL|SOCIAL|REVIEW|PHYSICAL|EXAM|'
        r'ASSESS|PLAN|LAB|IMAGING|PATH|IPSS|CHIEF|HPI).*$',
        '',
        body,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()

    return body
