"""
GU (Urology) Agent

Processes all UROLOGY notes and extracts structured data into gu_note dictionaries.
"""

from typing import List, Dict
from ..extractors import (
    extract_cc,
    extract_hpi,
    extract_ipss,
    extract_diet,
    extract_pmh_from_note,
    extract_psh,
    extract_social,
    extract_family,
    extract_sexual,
    extract_psa,
    extract_pathology_from_note,
    extract_testosterone,
    extract_medications_from_note,
    extract_allergies,
    extract_endocrine_labs,
    extract_stone_labs,
    extract_labs,
    extract_imaging_from_note,
)
# Note: Assessment and Plan are NOT extracted in Stage 1 - they are Stage 2 only


def process_gu_notes(gu_notes: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Process all GU (urology) notes and extract structured data.

    Each note is processed by all extractor functions to create a complete
    gu_note dictionary. If an extractor finds nothing, it returns "".

    Args:
        gu_notes: List of GU note dictionaries from identify_notes()
                  Each dict has: {"title": "...", "date": "...", "content": "..."}

    Returns:
        List of gu_note dictionaries, one per input note:
        [
            {
                "CC": "...",
                "HPI": "...",
                "IPSS": "...",
                "DHx": "...",
                "PMH": "...",
                "PSH": "...",
                "Social": "...",
                "Family": "...",
                "Sexual": "...",
                "PSA": "...",
                "Pathology": "...",
                "Testosterone": "...",
                "Medications": "...",
                "Allergies": "...",
                "Endocrine": "...",
                "Stone": "...",
                "Labs": "...",
                "Imaging": "...",
                "Assessment": "...",
                "Plan": ""
            },
            ...
        ]

        Note: PE and ROS are NOT extracted from notes as they use static templates
              that providers fill in during the actual patient visit.
    """
    gu_note_list = []

    for note in gu_notes:
        note_content = note["content"]

        # Extract all sections using extractor functions
        # Note: PE, ROS, Assessment, and Plan are NOT extracted in Stage 1
        #       - PE/ROS use static templates filled by provider during visit
        #       - Assessment/Plan are completed after the patient visit (Stage 2)
        gu_note = {
            "CC": extract_cc(note_content),
            "HPI": extract_hpi(note_content),
            "IPSS": extract_ipss(note_content),
            "DHx": extract_diet(note_content),
            "PMH": extract_pmh_from_note(note_content),
            "PSH": extract_psh(note_content),
            "Social": extract_social(note_content),
            "Family": extract_family(note_content),
            "Sexual": extract_sexual(note_content),
            "PSA": extract_psa(note_content),
            "Pathology": extract_pathology_from_note(note_content),
            "Testosterone": extract_testosterone(note_content),
            "Medications": extract_medications_from_note(note_content),
            "Allergies": extract_allergies(note_content),
            "Endocrine": extract_endocrine_labs(note_content),
            "Stone": extract_stone_labs(note_content),
            "Labs": extract_labs(note_content),
            "Imaging": extract_imaging_from_note(note_content)
        }

        gu_note_list.append(gu_note)

    return gu_note_list
