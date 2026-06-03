"""
Allergies Extractor

Extracts allergy information from clinical notes and VA clinical documents.

Supports multiple VA allergy documentation formats:
1. Simple header: "Allergies: DRUG1, DRUG2"
2. ADR notation: "Allergies/ADRs: DRUG1, DRUG2"
3. Remote/Local Review Table with facility-allergen pairs
4. NKA patterns: "Patient has answered NKA"
"""

import re
from typing import Set


def extract_allergies(note_content: str) -> str:
    """
    Extract allergies from a clinical note.

    Common markers: "ALLERGIES:", "Allergies:", "Adverse Reactions:",
                    "Allergies/ADRs:", "Medication Allergies:"

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted allergies text, or "" if not found
    """
    # Pattern: "ALLERGIES:" or "Adverse Reactions:" followed by content
    pattern = r'(?:ALLERGIES|Allergies|Adverse Reactions|ADRs?):\s*(.*?)(?=\n\s*(?:MEDICATIONS:|ASSESSMENT:|PLAN:|ROS:|PE:|PHYSICAL|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        allergies_text = match.group(1).strip()

        # Common "no allergies" patterns
        if re.search(r'(no\s+known|nkda|none\s+known|no\s+allergies)', allergies_text, re.IGNORECASE):
            return "No known drug allergies (NKDA)"

        # Clean up whitespace
        allergies_text = re.sub(r' +', ' ', allergies_text)
        allergies_text = re.sub(r'\n{3,}', '\n', allergies_text)

        return allergies_text

    return ""


def extract_allergies_from_document(clinical_document: str) -> str:
    """
    Extract allergies from the full VA clinical document.

    This searches for allergy data across the entire document, including:
    1. Simple "Allergies:" headers with comma-separated allergen lists
    2. "Allergies/ADRs:" headers
    3. VA "ALLERGIES REMOTE AND LOCAL REVIEW" table format
    4. "Patient has answered NKA" patterns
    5. "Medication Allergies:" headers

    Args:
        clinical_document: Full clinical document text

    Returns:
        Extracted allergy list, or "" if not found
    """
    all_allergens: Set[str] = set()

    # ======================================================================
    # Pattern 1: Simple "Allergies:" or "Allergies/ADRs:" header
    # Format: "Allergies:PARAFON FORTE, TOLMETIN"
    # Format: "Allergies/ADRs: ASPIRIN, MORPHINE"
    # ======================================================================
    simple_patterns = [
        r'Allergies(?:/ADRs?)?:\s*([A-Z][A-Z\s,/]+?)(?=\n|$)',
        r'Medication\s+Allergies?\s*:\s*([A-Z][A-Z\s,/]+?)(?=\n|$)',
    ]

    for pattern in simple_patterns:
        for match in re.finditer(pattern, clinical_document):
            allergy_text = match.group(1).strip()

            # Skip NKA/reviewed patterns
            if _is_nka_text(allergy_text):
                continue

            # Skip if it's just "Reviewed" or similar
            if allergy_text.upper().strip() in ('REVIEWED', 'REVIEW', 'SEE BELOW'):
                continue

            # Parse comma-separated allergens
            allergens = [a.strip() for a in allergy_text.split(',') if a.strip()]
            for allergen in allergens:
                # Filter out non-allergy text
                if _is_valid_allergen(allergen):
                    all_allergens.add(_normalize_allergen(allergen))

    # ======================================================================
    # Pattern 2: VA Remote/Local Allergy Review Table
    # Format:
    # ALLERGIES REMOTE AND LOCAL REVIEW:
    # FACILITY                                ALLERGY/ADR
    # --------                                -----------
    # AUDIE L. MURPHY MEMORIAL HOSP          PARAFON FORTE
    # AUDIE L. MURPHY MEMORIAL HOSP          TOLMETIN
    # ======================================================================
    table_pattern = r'ALLERGIES?\s+REMOTE\s+AND\s+LOCAL\s+REVIEW[:\s]*\n.*?FACILITY\s+ALLERGY/ADR\s*\n[-\s]+\n(.*?)(?=\n\s*(?:Remote and Local|Medications|======|\n\n))'
    table_match = re.search(table_pattern, clinical_document, re.IGNORECASE | re.DOTALL)
    if table_match:
        table_content = table_match.group(1)
        for line in table_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('-'):
                continue

            # Extract allergen from facility/allergen table row
            # The facility name is left-aligned, allergen is right portion
            # Split by multiple spaces (facility and allergen are separated by spaces)
            parts = re.split(r'\s{3,}', line)
            if len(parts) >= 2:
                allergen = parts[-1].strip()
                if allergen and _is_valid_allergen(allergen):
                    all_allergens.add(_normalize_allergen(allergen))
            elif len(parts) == 1:
                # Could be just an allergen name if format is different
                allergen = parts[0].strip()
                if allergen and _is_valid_allergen(allergen):
                    all_allergens.add(_normalize_allergen(allergen))

    # ======================================================================
    # Pattern 3: Inline allergy references
    # "Allergies that we know about: PARAFON FORTE, TOLMETIN"
    # ======================================================================
    inline_pattern = r'Allergies\s+that\s+we\s+know\s+about:\s*([^\n]+)'
    inline_match = re.search(inline_pattern, clinical_document, re.IGNORECASE)
    if inline_match:
        allergy_text = inline_match.group(1).strip()
        if not _is_nka_text(allergy_text):
            allergens = [a.strip() for a in allergy_text.split(',') if a.strip()]
            for allergen in allergens:
                if _is_valid_allergen(allergen):
                    all_allergens.add(_normalize_allergen(allergen))

    # ======================================================================
    # Pattern 4: "Allergies:" with list on next lines
    # Allergies:
    #  PENICILLIN
    #  TERAZOSIN
    # ======================================================================
    multiline_pattern = r'(?:ALLERGIES|Allergies)(?:/ADRs?)?:\s*\n((?:\s+[A-Z][A-Z\s/]+\n?)+)'
    multiline_match = re.search(multiline_pattern, clinical_document)
    if multiline_match:
        lines = multiline_match.group(1).strip().split('\n')
        for line in lines:
            allergen = line.strip()
            if allergen and _is_valid_allergen(allergen):
                all_allergens.add(_normalize_allergen(allergen))

    # ======================================================================
    # Remove false positives
    # ======================================================================
    # Remove "NO KNOWN ALLERGIES" if it got captured
    all_allergens.discard("No Known Allergies")
    all_allergens.discard("Nka")
    all_allergens.discard("Nkda")
    all_allergens.discard("Reviewed")

    # ======================================================================
    # Check for NKA if no allergens found
    # ======================================================================
    if not all_allergens:
        # Check if document explicitly states NKA
        nka_patterns = [
            r'Patient\s+has\s+answered\s+NKA',
            r'No\s+Remote\s+Allergy/ADR\s+Data\s+available',
            r'Allergies(?:/ADRs?)?:\s*(?:NKDA|NKA|No\s+Known)',
            r'No\s+known\s+(?:drug\s+)?allergies',
        ]
        for pattern in nka_patterns:
            if re.search(pattern, clinical_document, re.IGNORECASE):
                return "No known drug allergies (NKDA)"
        return ""

    # Return formatted allergen list
    sorted_allergens = sorted(all_allergens)
    return ', '.join(sorted_allergens)


def _is_nka_text(text: str) -> bool:
    """Check if text indicates no known allergies."""
    nka_indicators = [
        'no known', 'nkda', 'nka', 'none known', 'no allergies',
        'patient has answered nka', 'no remote allergy'
    ]
    text_lower = text.lower().strip()
    return any(indicator in text_lower for indicator in nka_indicators)


def _is_valid_allergen(text: str) -> bool:
    """Check if text is a valid allergen name (not a header, separator, etc.)."""
    text = text.strip()
    if not text or len(text) < 2:
        return False

    # Skip headers, separators, and common non-allergen text
    skip_patterns = [
        r'^-+$', r'^=+$', r'^\*+$',
        r'^FACILITY', r'^ALLERGY', r'^--------',
        r'^Remote\s+and\s+Local', r'^reactions?\s+confirmed',
        r'^Patient\s+has\s+answered', r'^No\s+Remote',
        r'^Reviewed$', r'^Review$', r'^See\s+Below',
        r'^NO\s+KNOWN', r'^NKDA$', r'^NKA$',
    ]

    for pattern in skip_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return False

    return True


def _normalize_allergen(allergen: str) -> str:
    """Normalize allergen name to title case."""
    allergen = allergen.strip()

    # Handle special cases that should stay uppercase
    upper_keep = ['ACE', 'ASA', 'NSAID', 'NSAIDS', 'HCL', 'HCI']

    words = allergen.split()
    normalized = []
    for word in words:
        if word.upper() in upper_keep:
            normalized.append(word.upper())
        else:
            normalized.append(word.capitalize())

    return ' '.join(normalized)
