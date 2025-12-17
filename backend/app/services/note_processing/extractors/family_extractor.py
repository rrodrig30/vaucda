"""
Family History Extractor

Extracts family history from clinical notes.
Enhanced to extract from PCP notes and narrative formats.
"""

import re


def extract_family(note_content: str) -> str:
    """
    Extract Family History from a clinical note.

    Common markers: "Family History:", "FAMILY:", "Family Hx:"
    Also extracts from narrative formats in PCP notes and problem lists.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted family history text, or "" if not found
    """
    # Pattern 1: VA consult format with indented lines (try this first)
    pattern1 = r'FAMILY HISTORY:\s*\n((?:\s+[^\n]+\n)+)'
    match = re.search(pattern1, note_content, re.IGNORECASE | re.MULTILINE)

    if match:
        # Post-process to stop at blank lines or section headers
        raw_family = match.group(1)
        lines = raw_family.split('\n')
        family_lines = []
        for line in lines:
            # Stop if we hit a section header, blank line, or just a dot
            if any(header in line.upper() for header in ['CURRENT HEALTH', 'MEDICATIONS:', 'PMH', 'PSH']):
                break
            stripped = line.strip()
            if not stripped or stripped == '.':
                break
            family_lines.append(stripped)
        family_text = '\n'.join(family_lines)
    else:
        # Pattern 2: Standard clinic note format
        # Match everything from "FAMILY HISTORY:" up to the next section header
        # Section headers can be:
        #   - All caps words followed by colon (e.g., "SEXUAL HISTORY:")
        #   - Equal sign delimited sections (e.g., "====== SECTION ======")
        #   - Dashed separators (e.g., "------")
        pattern2 = r'(?:FAMILY HISTORY|Family History|FAMILY|Family Hx):\s*(.*?)(?=\n\s*(?:[A-Z][A-Z\s]+:|={3,}|------|$))'
        match = re.search(pattern2, note_content, re.DOTALL | re.MULTILINE)
        if match:
            family_text = match.group(1).strip()
        else:
            family_text = ""

        # DON'T skip if it's just a single negative statement - include everything we captured
        # Clean up whitespace
        family_text = re.sub(r' +', ' ', family_text)
        family_text = re.sub(r'\n{3,}', '\n', family_text)
        return family_text if family_text else ""

    # Pattern 2: Try to extract from PCP note format
    pcp_family = _extract_family_from_pcp_format(note_content)
    if pcp_family:
        return pcp_family

    # Pattern 3: Extract from problem list
    problem_list_family = _extract_family_from_problem_list(note_content)
    if problem_list_family:
        return problem_list_family

    return ""


def _extract_family_from_pcp_format(text: str) -> str:
    """Extract family history from PCP note format."""
    # Try to import PCP extractor
    try:
        from .pcp_note_extractor import PCPNoteExtractor
        extractor = PCPNoteExtractor()
        return extractor.extract_family_history(text)
    except ImportError:
        return ""


def _extract_family_from_problem_list(text: str) -> str:
    """Extract family history from problem list format."""
    # Pattern: "Family history of cancer of colon" in problem lists
    family_conditions = []

    # Pattern 1: "Family history of..." in problem list
    fh_problem_pattern = r'Family history of\s+([^\n(]+?)(?:\s*\([^)]+\))?(?:\n|$)'
    matches = re.findall(fh_problem_pattern, text, re.IGNORECASE)
    for condition in matches:
        condition = condition.strip()
        if condition:
            family_conditions.append(condition)

    if family_conditions:
        return f"Family history of {', '.join(family_conditions)}"

    return ""
