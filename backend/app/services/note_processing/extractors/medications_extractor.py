"""
Medications Extractor

Extracts medications from VA medication list format.
"""

import re


def extract_medications(clinical_document: str) -> str:
    """
    Extract medications from VA medication list format.

    VA medication format example:
    ===============================================================================
    Drug Name
     TAMSULOSIN HCL 0.4MG CAP
    Issue Date
     10/17/2025
    SIG
     TAKE TWO CAPSULES BY MOUTH AT BEDTIME FOR ENLARGED PROSTATE
    Facility: AUDIE L. MURPHY MEMORIAL HOSP
    ===============================================================================

    Args:
        clinical_document: Full clinical document

    Returns:
        List of medications with SIG instructions, or "" if not found
    """
    medications = []

    # Split document by separator lines
    sections = re.split(r'={70,}', clinical_document)

    for section in sections:
        if not section.strip():
            continue

        # Look for "Drug Name" header
        if 'Drug Name' not in section:
            continue

        # Extract drug name
        drug_match = re.search(r'Drug Name\s*\n\s*([^\n]+)', section, re.IGNORECASE)
        if not drug_match:
            continue
        drug_name = drug_match.group(1).strip()

        # Convert to title case (ALL CAPS only for section headings, not medication names)
        drug_name = drug_name.title()

        # Extract issue date (optional)
        date_match = re.search(r'Issue Date\s*\n\s*([^\n]+)', section, re.IGNORECASE)
        issue_date = date_match.group(1).strip() if date_match else ""

        # Extract SIG instructions
        sig_match = re.search(r'SIG\s*\n\s*(.+?)(?=\n\s*(?:Facility:|Status:|Refills:|$))', section, re.IGNORECASE | re.DOTALL)
        sig = sig_match.group(1).strip() if sig_match else ""

        # Clean up SIG: collapse multiple spaces, remove extra newlines
        if sig:
            sig = re.sub(r'\s+', ' ', sig)
            # Convert to sentence case (only first letter capitalized)
            sig = sig.capitalize()

        # Format medication entry
        if sig:
            med_entry = f"{drug_name} - {sig}"
        else:
            med_entry = drug_name

        medications.append(med_entry)

    if not medications:
        return ""

    return '\n'.join(medications)


def extract_medications_from_note(note_content: str) -> str:
    """
    Extract medications section from a clinical note (alternative format).

    Some notes may have a "MEDICATIONS:" section.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted medications text, or "" if not found
    """
    # Pattern: "MEDICATIONS:" or "Meds:" followed by content
    pattern = r'(?:MEDICATIONS|MEDS|Medications):\s*(.*?)(?=\n\s*(?:ALLERGIES:|ASSESSMENT:|PLAN:|ROS:|PE:|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        meds_text = match.group(1).strip()
        # Clean up whitespace
        meds_text = re.sub(r' +', ' ', meds_text)
        meds_text = re.sub(r'\n{3,}', '\n', meds_text)
        return meds_text

    return ""
