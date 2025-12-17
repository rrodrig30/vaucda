"""
Social History Extractor

Extracts social history from clinical notes.
Enhanced to extract from PCP notes and narrative formats.
"""

import re


def extract_social(note_content: str) -> str:
    """
    Extract Social History from a clinical note.

    Common markers: "Social History:", "SOCIAL:", "Social Hx:"
    Also extracts from narrative formats in PCP notes.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted social history text, or "" if not found
    """
    social_parts = []

    # Pattern 1: Explicit "Social History:" section
    pattern = r'(?:Social History|SOCIAL|Social Hx):\s*(.*?)(?=\n\s*(?:Family History|FAMILY:|Sexual History|SEXUAL:|ROS:|PE:|PHYSICAL|EXAM:|ASSESSMENT:|PLAN:|Review of Systems|Physical Exam|MEDICATIONS:|ALLERGIES:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        social_text = match.group(1).strip()
        # Skip if it's just a boilerplate negative statement
        if social_text.lower() not in ['noncontributory', 'none', 'not available', 'no social history']:
            # Clean up whitespace
            social_text = re.sub(r' +', ' ', social_text)
            social_text = re.sub(r'\n{3,}', '\n\n', social_text)
            # Filter out healthcare maintenance content
            social_text = _filter_healthcare_maintenance(social_text)
            if social_text:
                social_parts.append(social_text)

    # Always try narrative extraction to supplement structured data
    narrative_social = _extract_social_narrative(note_content)
    if narrative_social:
        # Filter narrative extraction too
        filtered_narrative = _filter_healthcare_maintenance(narrative_social)
        if filtered_narrative:
            social_parts.append(filtered_narrative)

    # Pattern 2: Try to extract from PCP note format
    pcp_social = _extract_social_from_pcp_format(note_content)
    if pcp_social:
        # Filter PCP extraction as well
        filtered_pcp = _filter_healthcare_maintenance(pcp_social)
        if filtered_pcp:
            social_parts.append(filtered_pcp)

    if not social_parts:
        return ""

    # Combine all parts and deduplicate
    combined = '\n'.join(social_parts)
    return _deduplicate_social_text(combined)


def _extract_social_from_pcp_format(text: str) -> str:
    """Extract social history from PCP note format."""
    # Try to import PCP extractor
    try:
        from .pcp_note_extractor import PCPNoteExtractor
        extractor = PCPNoteExtractor()
        return extractor.extract_social_history(text)
    except ImportError:
        return ""


def _extract_social_narrative(text: str) -> str:
    """Extract social history from narrative mentions."""
    social_elements = []

    # Tobacco patterns
    tobacco_patterns = [
        r'(?:The patient has|Patient has)\s+never used\s+(?:other types of\s+)?tobacco',
        r'Tobacco\s*[:-]\s*(?:No|None)',
        r'(?:Former|Ex)\s+tobacco\s+user,?\s*quit\s+(?:in\s+)?(?:his|her|their)?\s*([^\n.]+)',
        r'(?:Never|Non[- ]?)smoker',
        r'Current\s+smoker,?\s*([^\n.]+)',
        r'Quit\s+(?:smoking|tobacco)\s+(?:in\s+)?(?:his|her|their)?\s*([^\n.]+)',
        r'Tob(?:acco)?:\s*([^\n]+)'
    ]

    for pattern in tobacco_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if match.groups() and match.group(1):
                social_elements.append(f"Tobacco: {match.group(1).strip()}")
            else:
                # Use the matched text
                tobacco_text = match.group(0).strip()
                if 'never' in tobacco_text.lower() or 'no' in tobacco_text.lower():
                    social_elements.append("Tobacco: Never smoker")
                else:
                    social_elements.append(tobacco_text)
            break  # Only capture one tobacco entry

    # Alcohol patterns
    alcohol_patterns = [
        r'(?:An )?alcohol screening test \(AUDIT-C\) was\s+(\w+)\s*\(score[^\)]*\)',
        r'Alcohol Screen[:\s]*([^\n]+)',
        r'AUDIT-C[:\s]*([^\n]+)',
        r'ETOH\s*[:-]?\s*([^\n]+)',
        r'(?:Reports|States)\s+consuming\s+(?:approximately\s+)?([^.]+(?:glass|drink|beer|wine)[^.]*)',
        r'Alcohol\s*[:-]\s*([^\n]+)'
    ]

    for pattern in alcohol_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            alcohol_text = match.group(1).strip()
            if alcohol_text.lower() not in ['none', 'no', 'denies']:
                social_elements.append(f"Alcohol: {alcohol_text}")
                break

    # Military service
    military_patterns = [
        r'Military Service\s*[:-]\s*([^\n]+)',
        r'(\d+\.?\d*\s+years\s+(?:in\s+)?(?:the\s+)?(?:Air Force|Navy|Army|Marines|Coast Guard)[^\n.]+)',
    ]

    for pattern in military_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            social_elements.append(f"Military: {match.group(1).strip()}")
            break

    if not social_elements:
        return ""

    return '. '.join(social_elements) + '.'


def _filter_healthcare_maintenance(text: str) -> str:
    """
    Filter out healthcare maintenance content (vaccines, screenings, etc.)
    from social history text.

    Stops extraction when healthcare maintenance markers are found.
    """
    # Stop at healthcare maintenance section markers
    healthcare_markers = [
        'Healthcare-',
        'Healthcare:',
        'Health maintenance:',
        'Living will',
        'Advance directive',
        'Shingles-',
        'Flu shot',
        'Covid',
        'Pvx 20',
        'RSV vaccine',
        'HIV-declines',
        'Hepatitis C',
        'Colonoscopy',
        'Ultrasound',
        'Sleep study',
        "Alzheimer's work-up",
        'Mammogram',
        'Pap smear'
    ]

    lines = text.split('\n')
    filtered_lines = []

    for line in lines:
        # Check if line contains healthcare maintenance content
        is_healthcare = False
        for marker in healthcare_markers:
            if marker.lower() in line.lower():
                is_healthcare = True
                break

        if is_healthcare:
            # Stop processing - don't include this line or anything after
            break

        # Also skip lines that are just structural artifacts
        if line.strip() and not line.strip() in ['Behavior - Cooperative', 'Psychological Social:']:
            filtered_lines.append(line)

    return '\n'.join(filtered_lines).strip()


def _deduplicate_social_text(text: str) -> str:
    """
    Remove duplicate phrases and sentences from social history text.

    Handles cases where the same information appears multiple times
    due to multiple extraction methods.
    """
    if not text:
        return ""

    # Split into sentences/phrases
    sentences = []
    for part in text.split('.'):
        part = part.strip()
        if part:
            sentences.append(part)

    # Remove exact duplicates while preserving order
    seen = set()
    unique_sentences = []
    for sentence in sentences:
        # Normalize for comparison (lowercase, strip whitespace)
        normalized = ' '.join(sentence.lower().split())
        if normalized not in seen:
            seen.add(normalized)
            unique_sentences.append(sentence)

    return '. '.join(unique_sentences) + '.' if unique_sentences else ""
