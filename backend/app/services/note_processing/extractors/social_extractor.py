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

    CRITICAL: Section boundary enforcement - only extract from the social history
    section, not from family history or other sections.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted social history text, or "" if not found
    """
    social_parts = []
    bounded_social_section = ""

    # Pattern 1: Explicit "Social History:" section with proper boundaries
    # IMPORTANT: Stop at Family History, Past Medical History, etc. to prevent contamination
    pattern = r'(?:Social History|SOCIAL|Social Hx|Social and personal history):\s*(.*?)(?=\n\s*(?:Family History|FAMILY:|Sexual History|SEXUAL:|ROS:|PE:|PHYSICAL|EXAM:|ASSESSMENT:|PLAN:|Review of Systems|Physical Exam|MEDICATIONS:|ALLERGIES:|======|Facility:|Note Narrative|Provider Narrative|Past Medical History|PAST MEDICAL|PMH:|Active [Pp]roblems|Computerized Problem List))'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        social_text = match.group(1).strip()
        bounded_social_section = social_text  # Save for narrative extraction

        # Skip if it's just a boilerplate negative statement
        if social_text.lower() not in ['noncontributory', 'none', 'not available', 'no social history']:
            # Clean up whitespace
            social_text = re.sub(r' +', ' ', social_text)
            social_text = re.sub(r'\n{3,}', '\n\n', social_text)
            # Filter out healthcare maintenance content
            social_text = _filter_healthcare_maintenance(social_text)
            # Validate - remove family member descriptions
            social_text = _filter_family_member_content(social_text)
            if social_text:
                social_parts.append(social_text)

    # Try narrative extraction ONLY on the bounded section (not full document)
    # This prevents extracting content from Family History section
    if bounded_social_section:
        narrative_social = _extract_social_narrative(bounded_social_section)
        if narrative_social:
            # Filter narrative extraction too
            filtered_narrative = _filter_healthcare_maintenance(narrative_social)
            filtered_narrative = _filter_family_member_content(filtered_narrative)
            if filtered_narrative and filtered_narrative not in social_parts:
                social_parts.append(filtered_narrative)

    # Pattern 2: Try to extract from PCP note format
    pcp_social = _extract_social_from_pcp_format(note_content)
    if pcp_social:
        # Filter PCP extraction as well
        filtered_pcp = _filter_healthcare_maintenance(pcp_social)
        filtered_pcp = _filter_family_member_content(filtered_pcp)
        if filtered_pcp:
            social_parts.append(filtered_pcp)

    # Pattern 3: VA "Note Narrative" format where content comes AFTER the marker
    # Format: "Social and personal history finding (...)\nDate of Onset\n\nNote Narrative\n<content>"
    va_narrative_pattern = r'Social and personal history[^\n]*\n(?:Date of Onset\s*\n\s*)?Note Narrative\s*\n(.*?)(?=\n\s*(?:Exposures|H/O:|Facility:|Provider Narrative|Family History|======|$))'
    va_match = re.search(va_narrative_pattern, note_content, re.IGNORECASE | re.DOTALL)
    if va_match:
        va_social = va_match.group(1).strip()
        if va_social:
            # Apply all filters to VA format content
            va_social = re.sub(r' +', ' ', va_social)
            va_social = re.sub(r'\n{3,}', '\n\n', va_social)
            va_social = _filter_healthcare_maintenance(va_social)
            va_social = _filter_family_member_content(va_social)
            if va_social and va_social not in social_parts:
                social_parts.append(va_social)

    if not social_parts:
        return ""

    # Combine all parts and deduplicate
    combined = '\n'.join(social_parts)
    return _deduplicate_social_text(combined)


def _filter_family_member_content(text: str) -> str:
    """
    Filter out content that describes family members, not the patient.

    Removes entries like:
    - "17 yo w/ Down's" (child description)
    - "; 17 yo" (garbled text with family age)
    - References to children, spouse details

    Preserves content before family member descriptions when possible.
    """
    if not text:
        return ""

    lines = text.split('\n')
    filtered_lines = []

    # Family member indicators that should be removed
    family_patterns = [
        r'\d{1,2}\s*yo\s*w/',  # "17 yo w/" pattern
        r'w/\s*down',          # "w/ Down's" pattern
        r'piano.*cheer',       # Child activities
        r'church greeter',     # Child activities
        r'special needs',
        r'^\s*;\s*\d',         # Lines starting with "; number" (garbled)
    ]

    for line in lines:
        line_lower = line.lower()
        should_filter = False
        preserved_part = None

        for pattern in family_patterns:
            match = re.search(pattern, line_lower, re.IGNORECASE)
            if match:
                should_filter = True
                # Try to preserve content BEFORE the family member description
                # Look for semicolon separator before the match
                before_match = line[:match.start()]
                # Find the last semicolon before the family content
                semicolon_pos = before_match.rfind(';')
                if semicolon_pos > 0:
                    preserved_part = line[:semicolon_pos].strip()
                    # Clean up the preserved part
                    if preserved_part and len(preserved_part) > 5:
                        # Ensure it contains useful info, not just garbage
                        if any(word in preserved_part.lower() for word in ['tob', 'etoh', 'alcohol', 'smok', 'drink', 'retired', 'married']):
                            should_filter = False  # Don't filter, we'll use preserved
                            line = preserved_part
                break

        # Also filter out lone punctuation or very short garbage
        if line.strip() in [';', ':', ',', '.', '-', '']:
            should_filter = True

        # Filter entries that are just punctuation followed by family descriptions
        if line.strip().startswith(';') and any(term in line_lower for term in ['yo', 'year', 'down', 'piano']):
            should_filter = True

        if not should_filter:
            filtered_lines.append(line)

    result = '\n'.join(filtered_lines).strip()

    # Also clean up alcohol entries with garbage
    # Pattern: "Alcohol: ;" or "Alcohol: ; garbage"
    result = re.sub(r'Alcohol:\s*;\s*[^\n]*', '', result, flags=re.IGNORECASE)
    result = re.sub(r'Alcohol:\s*$', '', result, flags=re.IGNORECASE | re.MULTILINE)

    return result.strip()


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


def _extract_social_from_assessment(assessment_text: str) -> dict:
    """
    Extract social history mentions from Assessment & Plan text.

    Args:
        assessment_text: Text from Assessment or Plan section

    Returns:
        Dict with keys: tobacco, alcohol, occupation, military, living_situation
    """
    prior_social = {
        'tobacco': None,
        'alcohol': None,
        'occupation': None,
        'military': None,
        'living_situation': None
    }

    text_lower = assessment_text.lower()

    # Tobacco status from A&P
    tobacco_patterns = [
        (r'(?:former|ex)[\s-]*smoker', 'former smoker'),
        (r'(?:current|active)\s+smoker', 'current smoker'),
        (r'(?:never|non)[\s-]*smoker', 'never smoker'),
        (r'quit\s+(?:smoking|tobacco)', 'former smoker'),
        (r'tobacco\s+(?:use|abuse)', 'tobacco user'),
        (r'pack[\s-]*year', 'smoker'),
        (r'smoking\s+cessation', 'former smoker'),
    ]
    for pattern, status in tobacco_patterns:
        if re.search(pattern, text_lower):
            prior_social['tobacco'] = status
            break

    # Alcohol status from A&P
    alcohol_patterns = [
        (r'alcohol\s+(?:use|abuse|dependence)', 'alcohol use'),
        (r'(?:heavy|excessive)\s+(?:drink|alcohol|etoh)', 'heavy drinker'),
        (r'(?:social|occasional)\s+drink', 'social drinker'),
        (r'(?:no|denies)\s+(?:alcohol|etoh)', 'non-drinker'),
        (r'etoh\s+(?:use|abuse)', 'alcohol use'),
    ]
    for pattern, status in alcohol_patterns:
        if re.search(pattern, text_lower):
            prior_social['alcohol'] = status
            break

    # Occupation from A&P
    occupation_match = re.search(r'(?:retired|works?\s+(?:as|in)|employed|occupation)[:\s]+([^,.\n]+)', text_lower)
    if occupation_match:
        prior_social['occupation'] = occupation_match.group(1).strip()

    # Military from A&P
    military_match = re.search(r'(?:veteran|military|served\s+in)[:\s]+([^,.\n]+)', text_lower)
    if military_match:
        prior_social['military'] = military_match.group(1).strip()

    return prior_social


def _extract_social_from_current(social_text: str) -> dict:
    """
    Extract structured social history elements from current extraction.

    Args:
        social_text: Current social history extraction

    Returns:
        Dict with keys: tobacco, alcohol, occupation, military, living_situation
    """
    current_social = {
        'tobacco': None,
        'alcohol': None,
        'occupation': None,
        'military': None,
        'living_situation': None
    }

    text_lower = social_text.lower()

    # Tobacco
    tobacco_patterns = [
        (r'(?:former|ex)[\s-]*(?:smoker|tobacco)', 'former smoker'),
        (r'(?:current|active)\s+smoker', 'current smoker'),
        (r'(?:never|non)[\s-]*smoker', 'never smoker'),
        (r'quit\s+(?:smoking|tobacco)', 'former smoker'),
        (r'tobacco:\s*none', 'never smoker'),
        (r'no\s+tobacco', 'never smoker'),
        (r'denies\s+tobacco', 'never smoker'),
        (r'smok(?:es|ing)\s+(\d+)', 'current smoker'),
    ]
    for pattern, status in tobacco_patterns:
        if re.search(pattern, text_lower):
            current_social['tobacco'] = status
            break

    # Alcohol
    alcohol_patterns = [
        (r'(?:heavy|excessive)\s+(?:drink|alcohol|etoh)', 'heavy drinker'),
        (r'(?:social|occasional)\s+drink', 'social drinker'),
        (r'(?:no|none|denies)\s+(?:alcohol|etoh)', 'non-drinker'),
        (r'alcohol:\s*(?:no|none)', 'non-drinker'),
        (r'(\d+)\s+(?:drink|beer|wine|glass)', 'drinker'),
        (r'etoh\s*:\s*(\w+)', None),  # Will extract the word after ETOH:
    ]
    for pattern, status in alcohol_patterns:
        match = re.search(pattern, text_lower)
        if match:
            if status is None and match.groups():
                # Extract the word after ETOH:
                word = match.group(1)
                if word in ['no', 'none', 'denies']:
                    current_social['alcohol'] = 'non-drinker'
                else:
                    current_social['alcohol'] = f'{word} alcohol use'
            else:
                current_social['alcohol'] = status
            break

    # Occupation
    occupation_patterns = [
        r'(?:retired|works?\s+(?:as|in)|employed|occupation)[:\s]+([^,.\n]+)',
        r'(?:is\s+a\s+)(?:retired\s+)?(\w+(?:\s+\w+)?)',
    ]
    for pattern in occupation_patterns:
        match = re.search(pattern, text_lower)
        if match:
            occ = match.group(1).strip()
            if occ and len(occ) > 2 and occ not in ['a', 'an', 'the']:
                current_social['occupation'] = occ
                break

    # Military
    military_patterns = [
        r'(?:veteran|military)[:\s]+([^,.\n]+)',
        r'(\d+\.?\d*\s+years?\s+(?:in\s+)?(?:the\s+)?(?:air force|navy|army|marines|coast guard))',
        r'served\s+(?:in\s+)?(?:the\s+)?(\w+)',
    ]
    for pattern in military_patterns:
        match = re.search(pattern, text_lower)
        if match:
            current_social['military'] = match.group(1).strip()
            break

    return current_social


def flag_social_changes(current_social: str, source_document: str) -> str:
    """
    Compare current social history against prior A&P statements and flag changes.

    Per instructions: Flag any changes in social history compared to prior
    Assessment & Plan statements (e.g., tobacco status changed from "former
    smoker" to "current smoker").

    Args:
        current_social: Current extraction of social history
        source_document: Full source document containing prior A&P sections

    Returns:
        Social history text with change flags appended, or original if no changes
    """
    if not current_social or not source_document:
        return current_social

    # Extract prior A&P sections
    ap_pattern = r'(?:ASSESSMENT\s*(?:AND|&)?\s*PLAN|A/?P)[:\s]+(.*?)(?=\n\s*(?:======|Facility:|Provider:|Signed|Date:|Entry|$))'
    ap_matches = re.findall(ap_pattern, source_document, re.IGNORECASE | re.DOTALL)

    if not ap_matches:
        return current_social

    # Combine all prior A&P text
    prior_ap_text = '\n'.join(ap_matches)

    # Extract structured social from prior A&P
    prior_social = _extract_social_from_assessment(prior_ap_text)

    # Extract structured social from current
    current_social_data = _extract_social_from_current(current_social)

    # Detect changes
    changes = []

    # Check tobacco changes
    if prior_social['tobacco'] and current_social_data['tobacco']:
        prior_tob = prior_social['tobacco'].lower()
        curr_tob = current_social_data['tobacco'].lower()
        if prior_tob != curr_tob:
            # Significant change detection
            if ('former' in prior_tob and 'current' in curr_tob) or \
               ('never' in prior_tob and ('current' in curr_tob or 'former' in curr_tob)):
                changes.append(f"**TOBACCO STATUS CHANGED**: Prior A&P: '{prior_social['tobacco']}' → Current: '{current_social_data['tobacco']}'")

    # Check alcohol changes
    if prior_social['alcohol'] and current_social_data['alcohol']:
        prior_alc = prior_social['alcohol'].lower()
        curr_alc = current_social_data['alcohol'].lower()
        if prior_alc != curr_alc:
            if ('non' in prior_alc and 'heavy' in curr_alc) or \
               ('social' in prior_alc and 'heavy' in curr_alc) or \
               ('heavy' in prior_alc and 'non' in curr_alc):
                changes.append(f"**ALCOHOL STATUS CHANGED**: Prior A&P: '{prior_social['alcohol']}' → Current: '{current_social_data['alcohol']}'")

    # Check occupation changes
    if prior_social['occupation'] and current_social_data['occupation']:
        prior_occ = prior_social['occupation'].lower()
        curr_occ = current_social_data['occupation'].lower()
        if prior_occ != curr_occ and prior_occ not in curr_occ and curr_occ not in prior_occ:
            changes.append(f"**OCCUPATION CHANGED**: Prior A&P: '{prior_social['occupation']}' → Current: '{current_social_data['occupation']}'")

    if changes:
        return current_social + '\n\n' + '\n'.join(changes)

    return current_social


def extract_social_with_change_detection(note_content: str, full_document: str = None) -> str:
    """
    Extract social history with change detection against prior A&P.

    Combines extract_social() with flag_social_changes() for complete workflow.

    Args:
        note_content: Text to extract social history from
        full_document: Full source document for change comparison (optional)

    Returns:
        Social history with any change flags appended
    """
    social = extract_social(note_content)

    if not social:
        return ""

    if full_document:
        social = flag_social_changes(social, full_document)

    return social
