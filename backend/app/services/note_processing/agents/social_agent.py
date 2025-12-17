"""
Social History Agent

Combines social histories from all notes.
"""

import re
from typing import List, Dict
from ..llm_helper import combine_sections_with_llm
from .history_cleaners import clean_llm_commentary


def _infer_gender_from_notes(gu_notes: List[Dict[str, str]], non_gu_notes: List[Dict[str, str]]) -> str:
    """
    Infer patient gender from note content.

    Returns:
        "male", "female", or "unknown"
    """
    # Collect all note content to search for gender clues
    all_content = []

    for note in gu_notes:
        for key, value in note.items():
            if value and isinstance(value, str):
                all_content.append(value)

    for note in non_gu_notes:
        for key, value in note.items():
            if value and isinstance(value, str):
                all_content.append(value)

    combined_text = " ".join(all_content)

    # Look for explicit gender markers
    male_markers = [r'\bMr\b', r'\bmale\b', r'\b[Hh]e\s+(?:is|was|has|had)\b', r'\b[Hh]is\b']
    female_markers = [r'\bMrs\b', r'\bMs\b', r'\bMiss\b', r'\bfemale\b', r'\b[Ss]he\s+(?:is|was|has|had)\b', r'\b[Hh]er\b']

    male_count = sum(len(re.findall(pattern, combined_text, re.IGNORECASE)) for pattern in male_markers)
    female_count = sum(len(re.findall(pattern, combined_text, re.IGNORECASE)) for pattern in female_markers)

    if male_count > female_count:
        return "male"
    elif female_count > male_count:
        return "female"
    else:
        return "unknown"


def _fix_pronouns(text: str, gender: str) -> str:
    """
    Fix gender-neutral pronouns to match patient gender.

    Args:
        text: Social history text
        gender: "male", "female", or "unknown"

    Returns:
        Text with corrected pronouns
    """
    if gender == "unknown":
        return text

    if gender == "male":
        # Replace "They are" with "He is"
        text = re.sub(r'\bThey\s+are\b', 'He is', text)
        text = re.sub(r'\bthey\s+are\b', 'he is', text)
        # Replace "their" with "his"
        text = re.sub(r'\btheir\b', 'his', text)
        text = re.sub(r'\bTheir\b', 'His', text)
    elif gender == "female":
        # Replace "They are" with "She is"
        text = re.sub(r'\bThey\s+are\b', 'She is', text)
        text = re.sub(r'\bthey\s+are\b', 'she is', text)
        # Replace "their" with "her"
        text = re.sub(r'\btheir\b', 'her', text)
        text = re.sub(r'\bTheir\b', 'Her', text)

    return text


def synthesize_social(gu_notes: List[Dict[str, str]], non_gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize social history from all notes.

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries

    Returns:
        Combined social history
    """
    all_social = []

    for note in gu_notes:
        if note.get("Social"):
            all_social.append(note["Social"])

    for note in non_gu_notes:
        if note.get("Social"):
            all_social.append(note["Social"])

    if not all_social:
        return ""

    # Infer gender for pronoun correction
    gender = _infer_gender_from_notes(gu_notes, non_gu_notes)

    if len(all_social) == 1:
        # Still filter even if there's only one entry
        single_entry = all_social[0]
        # Apply filtering to remove healthcare maintenance content
        from ..extractors.social_extractor import _filter_healthcare_maintenance, _deduplicate_social_text
        filtered = _filter_healthcare_maintenance(single_entry)
        result = _deduplicate_social_text(filtered) if filtered else single_entry
        # Fix pronouns based on inferred gender
        return _fix_pronouns(result, gender)

    instructions = """Combine these social history entries into a single, clean summary.

INCLUDE ONLY:
- Tobacco use (current/former/never, quit date if applicable)
- Alcohol use (frequency, amount)
- Occupation and work history
- Military service
- Living situation

EXCLUDE ALL of the following (DO NOT include any of this content):
- Healthcare maintenance items (vaccines, flu shots, colonoscopy, etc.)
- Advance directives or living wills
- Medical imaging reports (ultrasounds, CT scans, etc.)
- Screening test results
- Any content about "Shingles", "Covid", "RSV vaccine", "Hepatitis C", etc.
- Any phrases like "Living will", "Ultrasound thyroid", "Sleep study", etc.
- Any content after the phrase "Healthcare-" or "Health maintenance"

Remove all duplicate phrases and sentences.
Write in clear, professional medical prose (not bullet points).
Be concise - 2-3 sentences maximum.

CRITICAL: Provide ONLY the factual summary. NO meta-commentary."""

    result = combine_sections_with_llm("Social History", all_social, instructions)
    result = clean_llm_commentary(result)
    # Fix pronouns based on inferred gender
    return _fix_pronouns(result, gender)
