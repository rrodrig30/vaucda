"""
Time Template Utility

Loads and parses time suffix templates for clinic notes and consult notes.
"""

import os
from typing import Dict, Optional


# Cache for time templates
_time_templates: Optional[Dict[str, str]] = None


def load_time_templates() -> Dict[str, str]:
    """
    Load time templates from time suffix.txt file.

    Returns:
        Dictionary with keys 'clinic_note' and 'consult' containing time templates
    """
    global _time_templates

    if _time_templates is not None:
        return _time_templates

    # Path to time suffix file (relative to backend directory)
    time_file_path = os.path.join(
        os.path.dirname(__file__),
        "../../../../time suffix.txt"
    )

    # Normalize path
    time_file_path = os.path.normpath(time_file_path)

    try:
        with open(time_file_path, 'r') as f:
            content = f.read()

        # Split by the separator
        parts = content.split('+++++++++++++++++++++++++++++++++++++++++')

        if len(parts) < 2:
            # Fallback if file format is unexpected
            _time_templates = {
                'clinic_note': '',
                'consult': ''
            }
            return _time_templates

        # First part is clinic note template (40 minutes)
        clinic_template = parts[0].strip()

        # Second part is consult template (45 minutes)
        consult_template = parts[1].strip()

        _time_templates = {
            'clinic_note': clinic_template,
            'consult': consult_template
        }

        return _time_templates

    except FileNotFoundError:
        # File not found - return empty templates
        _time_templates = {
            'clinic_note': '',
            'consult': ''
        }
        return _time_templates


def get_time_template(note_type: str) -> str:
    """
    Get time template for specified note type.

    Args:
        note_type: Note type in format '{specialty}_{clinic|consult}'
                   e.g., 'urology_clinic', 'urology_consult', 'hospital_medicine_consult'
                   Legacy types ('clinic_note', 'consult') are also supported.

    Returns:
        Time template string (40 minutes for clinic, 45 minutes for consult)
    """
    templates = load_time_templates()

    # Consults (any specialty) use 45-minute template
    # Clinic notes (any specialty) use 40-minute template
    if note_type.endswith('_consult') or note_type == 'consult':
        return templates.get('consult', '')
    else:
        return templates.get('clinic_note', '')


def format_patient_header(patient_name: Optional[str], ssn_last4: Optional[str]) -> str:
    """
    Format patient identification header for note.

    Args:
        patient_name: Full patient name
        ssn_last4: Last 4 digits of SSN

    Returns:
        Formatted header string
    """
    if not patient_name and not ssn_last4:
        return ""

    header_parts = []

    if patient_name:
        header_parts.append(f"Patient: {patient_name}")

    if ssn_last4:
        header_parts.append(f"SSN (Last 4): {ssn_last4}")

    header = " | ".join(header_parts)
    separator = "=" * len(header)

    return f"{separator}\n{header}\n{separator}\n\n"
