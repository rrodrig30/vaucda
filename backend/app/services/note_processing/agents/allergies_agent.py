"""
Allergies Agent

Combines allergy information from document-level extraction and individual notes.
Prioritizes document-level extraction (which captures VA allergy tables and headers)
over individual note-level extraction.
"""

from typing import List, Dict, Optional


def synthesize_allergies(
    gu_notes: List[Dict[str, str]],
    non_gu_notes: List[Dict[str, str]],
    document_allergies: Optional[str] = None
) -> str:
    """
    Synthesize allergies from document-level extraction and individual notes.

    Priority order:
    1. Document-level extraction (from VA allergy tables, headers, ADR sections)
    2. Note-level extraction (from individual GU/non-GU notes)

    Document-level extraction is preferred because allergy data in VA documents
    often appears in dedicated sections (e.g., "ALLERGIES REMOTE AND LOCAL REVIEW"
    tables, "Allergies/ADRs:" headers) that are NOT part of any individual note.

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries
        document_allergies: Allergies extracted from full clinical document

    Returns:
        Synthesized allergy list, or "No known drug allergies (NKDA)"
    """
    # Priority 1: Document-level allergies (most comprehensive source)
    if document_allergies:
        return document_allergies

    # Priority 2: Note-level allergies
    all_allergies = []

    for note in gu_notes:
        if note.get("Allergies"):
            allergy_text = note["Allergies"].strip()
            if allergy_text and not _is_nkda(allergy_text):
                all_allergies.append(allergy_text)

    for note in non_gu_notes:
        if note.get("Allergies"):
            allergy_text = note["Allergies"].strip()
            if allergy_text and not _is_nkda(allergy_text):
                all_allergies.append(allergy_text)

    if not all_allergies:
        # Check if any note explicitly states NKDA
        for note in gu_notes + non_gu_notes:
            if note.get("Allergies") and _is_nkda(note["Allergies"]):
                return "No known drug allergies (NKDA)"
        return "No known drug allergies (NKDA)"

    # Deduplicate allergies across notes
    seen = set()
    unique_allergies = []
    for allergy_text in all_allergies:
        # Split by common delimiters
        for allergen in _split_allergens(allergy_text):
            allergen_normalized = allergen.strip().lower()
            if allergen_normalized and allergen_normalized not in seen:
                seen.add(allergen_normalized)
                unique_allergies.append(allergen.strip())

    if not unique_allergies:
        return "No known drug allergies (NKDA)"

    return ', '.join(unique_allergies)


def _is_nkda(text: str) -> bool:
    """Check if text indicates no known drug allergies."""
    text_lower = text.lower().strip()
    nkda_indicators = [
        'no known drug allergies',
        'no known allergies',
        'nkda',
        'nka',
        'none known',
        'no allergies',
    ]
    return any(indicator in text_lower for indicator in nkda_indicators)


def _split_allergens(text: str) -> list:
    """Split allergy text into individual allergens."""
    # Handle numbered lists (1. Drug1\n2. Drug2)
    import re
    lines = text.split('\n')
    allergens = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Remove numbering
        line = re.sub(r'^\d+\.\s*', '', line)
        # Split by comma
        for part in line.split(','):
            part = part.strip()
            if part:
                allergens.append(part)
    return allergens
