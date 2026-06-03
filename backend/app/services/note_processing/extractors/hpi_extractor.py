"""
History of Present Illness (HPI) Extractor

Extracts the HPI section from a clinical note.
Enhanced to capture post-surgical context and follow-up visit content.
"""

import re


def extract_hpi(note_content: str) -> str:
    """
    Extract History of Present Illness from a clinical note.

    The HPI typically appears after "HPI:" marker and continues until
    the next major section (PMH, PSH, ROS, etc.).

    This extractor has multiple fallback patterns:
    1. Explicit "HPI:" section
    2. "Present Illness:" section (common in VA progress notes)
    3. "Reason For Request:" section (common in consult requests)
    4. Chief Complaint + following narrative (for follow-up notes)
    5. Post-surgical status extraction (s/p, completed surgery)

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted HPI text, or "" if not found
    """
    # Pattern 1a: Explicit "HISTORY OF PRESENT ILLNESS:" section (common in VA notes)
    # Common next sections: IPSS table (+---), PMH, PSH, ROS, PE, PHYSICAL, EXAM, ASSESSMENT, etc.
    full_hpi_pattern = r'HISTORY\s+OF\s+PRESENT\s+ILLNESS:\s*(.*?)(?=\n\s*(?:\+---|\+====|IPSS:|PMH:|PSH:|ROS:|PE:|PHYSICAL EXAM:|EXAM:|ASSESSMENT:|PLAN:|DIETARY HISTORY:|SOCIAL HISTORY:|FAMILY HISTORY:|SEXUAL HISTORY:|Past Medical History|Past Surgical History|Review of Systems|Physical Exam|MEDICATIONS:|ALLERGIES:|Social History|======|PSA:|LABS:|IMAGING:))'

    match = re.search(full_hpi_pattern, note_content, re.IGNORECASE | re.DOTALL)
    if match:
        hpi_text = _clean_hpi_text(match.group(1))
        if hpi_text and len(hpi_text) > 20:  # Ensure substantial content
            # Append post-surgical context if present
            post_surg = _extract_post_surgical_context(note_content)
            if post_surg:
                hpi_text = hpi_text + "\n\n" + post_surg
            return hpi_text

    # Pattern 1b: Explicit "HPI:" section
    # Common next sections: IPSS table (+---), PMH, PSH, ROS, PE, PHYSICAL, EXAM, ASSESSMENT, etc.
    pattern = r'HPI:\s*(.*?)(?=\n\s*(?:\+---|\+====|IPSS:|PMH:|PSH:|ROS:|PE:|PHYSICAL EXAM:|EXAM:|ASSESSMENT:|PLAN:|DIETARY HISTORY:|SOCIAL HISTORY:|FAMILY HISTORY:|SEXUAL HISTORY:|Past Medical History|Past Surgical History|Review of Systems|Physical Exam|MEDICATIONS:|ALLERGIES:|Social History|======))'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL)
    if match:
        hpi_text = _clean_hpi_text(match.group(1))
        if hpi_text and len(hpi_text) > 20:  # Ensure substantial content
            # Append post-surgical context if present
            post_surg = _extract_post_surgical_context(note_content)
            if post_surg:
                hpi_text = hpi_text + "\n\n" + post_surg
            return hpi_text

    # Pattern 2: "Present Illness:" section (VA progress notes)
    # Format: "Present Illness: 66YO MALE PRESENTS FOR..."
    present_illness_pattern = r'Present Illness:\s*(.*?)(?=\n\s*(?:ROS:|Review of Systems|PCM:|PSYCH:|SERVICE|Active Problem|DISCLAIMER|ALLERGIES|Assessment:|======))'
    match = re.search(present_illness_pattern, note_content, re.IGNORECASE | re.DOTALL)
    if match:
        hpi_text = _clean_hpi_text(match.group(1))
        if hpi_text and len(hpi_text) > 20:
            return hpi_text

    # Pattern 3: "Reason For Request:" section (consult requests)
    # This is typically the consult reason which can serve as HPI basis
    reason_pattern = r'Reason\s+For\s+Request:\s*(.*?)(?=\n\s*(?:Inter-facility|Status:|Last Action|======))'
    match = re.search(reason_pattern, note_content, re.IGNORECASE | re.DOTALL)
    if match:
        reason_text = _clean_hpi_text(match.group(1))
        if reason_text and len(reason_text) > 10:
            return reason_text

    # Pattern 4: Chief Complaint + following clinical narrative (for follow-up notes)
    # This is common in follow-up notes that don't have explicit HPI section
    # Format: "CHIEF COMPLAINT: left renal CCRC\n\n53 yo male vet..."
    cc_narrative_pattern = r'(?:CHIEF COMPLAINT:|CC:)\s*([^\n]+)\n\n((?:\d+\s*(?:yo|year)\s*(?:old\s*)?(?:male|female)[^\n]*\n(?:[^\n]*\n){0,10}?))'
    match = re.search(cc_narrative_pattern, note_content, re.IGNORECASE | re.DOTALL)
    if match:
        cc = match.group(1).strip()
        narrative = match.group(2).strip()
        combined = f"{cc}\n\n{narrative}"
        hpi_text = _clean_hpi_text(combined)
        if hpi_text and len(hpi_text) > 30:
            return hpi_text

    # Pattern 5: Extract post-surgical follow-up content
    # Look for notes that are clearly post-surgical follow-ups
    post_surg = _extract_post_surgical_context(note_content)
    if post_surg and len(post_surg) > 50:
        return post_surg

    # Pattern 6: Chief Complaint context (CC: or Chief Complaint:)
    cc_pattern = r'(?:CC|Chief Complaint):\s*(.*?)(?=\n\s*(?:HPI|HISTORY|ROS|======))'
    match = re.search(cc_pattern, note_content, re.IGNORECASE | re.DOTALL)
    if match:
        cc_text = _clean_hpi_text(match.group(1))
        if cc_text and len(cc_text) > 5:
            return cc_text

    # Not found
    return ""


def _extract_post_surgical_context(note_content: str) -> str:
    """
    Extract post-surgical context from clinical notes.

    Looks for:
    - "s/p [procedure] on [date]" patterns
    - "Pt opted for [procedure]... completed [date]"
    - Final pathology results from surgery
    - Post-surgical status mentions

    Args:
        note_content: Full text of clinical note

    Returns:
        Post-surgical context text, or "" if not found
    """
    post_surg_elements = []

    # Pattern 1: "s/p [procedure] on [date]" - common in impressions
    sp_pattern = r'(?:pt\s+is\s+|is\s+)?s/p\s+([^.]+(?:nephrectomy|prostatectomy|cystectomy|TURP|TURBT)[^.]*?)(?:\.|$)'
    for match in re.finditer(sp_pattern, note_content, re.IGNORECASE):
        sp_text = match.group(1).strip()
        # Format nicely
        sp_text = f"Status post {sp_text}"
        if sp_text not in post_surg_elements:
            post_surg_elements.append(sp_text)

    # Pattern 2: "Pt opted for [procedure]... completed [date]"
    opted_pattern = r'(?:Pt|Patient)\s+opted\s+for\s+(?:a\s+)?([^.]+(?:nephrectomy|prostatectomy|cystectomy)[^.]*?)\.\s*(?:This\s+was\s+)?[Cc]ompleted\s+(\d{1,2}/\d{1,2}/\d{2,4})'
    for match in re.finditer(opted_pattern, note_content, re.IGNORECASE | re.DOTALL):
        procedure = match.group(1).strip()
        date = match.group(2)
        text = f"Patient underwent {procedure}, completed on {date}."
        if text not in post_surg_elements:
            post_surg_elements.append(text)

    # Pattern 3: Final pathology results
    final_path_pattern = r'Final\s+path(?:ology)?\s*(\d{1,2}/\d{1,2}/\d{2,4}):\s*\n?(.*?)(?=\n\n|\n[A-Z][A-Z]+:)'
    for match in re.finditer(final_path_pattern, note_content, re.IGNORECASE | re.DOTALL):
        date = match.group(1)
        findings = match.group(2).strip()
        if findings:
            # Clean up findings
            findings = re.sub(r'\n', ' ', findings)
            findings = re.sub(r'\s+', ' ', findings)
            text = f"Final surgical pathology ({date}): {findings}"
            if text not in post_surg_elements:
                post_surg_elements.append(text)

    # Pattern 4: Post-surgical recovery comments
    recovery_pattern = r'(?:He|She|Patient)\s+(?:has\s+)?recovered\s+well[^.]*\.'
    match = re.search(recovery_pattern, note_content, re.IGNORECASE)
    if match:
        text = match.group(0).strip()
        if text not in post_surg_elements:
            post_surg_elements.append(text)

    # Pattern 5: Denies symptoms post-surgery
    denies_pattern = r'(?:He|She|Patient)\s+denies\s+(?:interim\s+)?(?:gross\s+)?(?:hematuria|dysuria|weight\s+loss|flank\s+pain)[^.]*\.'
    match = re.search(denies_pattern, note_content, re.IGNORECASE)
    if match:
        text = match.group(0).strip()
        if text not in post_surg_elements:
            post_surg_elements.append(text)

    if post_surg_elements:
        return ' '.join(post_surg_elements)
    return ""


def _clean_hpi_text(text: str) -> str:
    """Clean and normalize HPI text."""
    if not text:
        return ""

    text = text.strip()

    # Clean up: normalize whitespace but preserve paragraph breaks
    # Replace multiple spaces with single space
    text = re.sub(r' +', ' ', text)
    # Replace 3+ newlines with 2 (preserve paragraph breaks)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text


def extract_consult_context(note_content: str) -> dict:
    """
    Extract additional context for HPI synthesis from consult requests.

    Returns dictionary with:
    - consult_reason: Reason for consult request
    - provisional_diagnosis: Provisional/working diagnosis
    - cc: Chief complaint
    - present_illness: Present illness from any progress note
    """
    context = {
        'consult_reason': '',
        'provisional_diagnosis': '',
        'cc': '',
        'present_illness': ''
    }

    # Extract consult reason
    reason_match = re.search(
        r'Reason\s+For\s+Request:\s*(.*?)(?=\n\s*(?:Inter-facility|Status:|Last Action|====))',
        note_content, re.IGNORECASE | re.DOTALL
    )
    if reason_match:
        context['consult_reason'] = _clean_hpi_text(reason_match.group(1))

    # Extract provisional diagnosis
    diag_match = re.search(
        r'Provisional Diagnosis:\s*([^\n]+)',
        note_content, re.IGNORECASE
    )
    if diag_match:
        context['provisional_diagnosis'] = diag_match.group(1).strip()

    # Extract CC if present
    cc_match = re.search(
        r'(?:CC|Chief Complaint):\s*([^\n]+)',
        note_content, re.IGNORECASE
    )
    if cc_match:
        context['cc'] = cc_match.group(1).strip()

    # Extract Present Illness from progress notes
    pi_match = re.search(
        r'Present Illness:\s*(.*?)(?=\n\s*(?:ROS:|Review of Systems|PCM:|Active Problem|====))',
        note_content, re.IGNORECASE | re.DOTALL
    )
    if pi_match:
        context['present_illness'] = _clean_hpi_text(pi_match.group(1))

    return context
