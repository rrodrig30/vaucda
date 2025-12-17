"""
Past Medical History (PMH) Extractor

Extracts PMH from VA ALL PROBLEMS LIST format.
"""

import re


def extract_pmh(clinical_document: str) -> str:
    """
    Extract Past Medical History from VA ALL PROBLEMS LIST format.

    VA format example:
    ===============================================================================
    Provider Narrative
     Benign prostatic hyperplasia (SCT 266569009) (ICD-10-CM D29.1)
    Date of Onset

    Date Modified
     04/04/2023
    Exposures

    Facility: AUDIE L. MURPHY MEMORIAL HOSP
    ===============================================================================

    This function extracts diagnosis lines from each problem block.

    Args:
        clinical_document: Full clinical document (not just a note)

    Returns:
        List of diagnoses separated by newlines, or "" if not found
    """
    diagnoses = []
    diagnosis_base_names = {}  # Track base names to avoid duplicates

    # Split document by separator lines
    sections = re.split(r'={70,}', clinical_document)

    for section in sections:
        if not section.strip():
            continue

        # Look for "Provider Narrative" header
        if 'Provider Narrative' not in section:
            continue

        # Extract the diagnosis line
        # It's typically the first non-header line after "Provider Narrative"
        # Pattern: starts with optional whitespace, contains diagnosis text,
        # and has either (SCT ...) or (ICD-10-CM ...) or (ICD-9-CM ...)
        diagnosis_match = re.search(
            r'Provider Narrative\s*\n\s*([^\n]+(?:SCT|ICD-10-CM|ICD-9-CM)[^\n]+)',
            section,
            re.IGNORECASE
        )

        if diagnosis_match:
            diagnosis = diagnosis_match.group(1).strip()
            diagnosis_lower = diagnosis.lower()

            # Filter out non-medical administrative entries
            # Skip entries with ICD-9-CM 799.9 (unspecified/unknown cause - often administrative)
            if 'ICD-9-CM 799.9' in diagnosis:
                continue

            # Enhanced administrative/non-medical entry filtering
            non_medical_keywords = [
                'provider', 'pmhp', 'safety plan', 'drs allen', 'cigarroa',
                'dietary history', 'unemployed', 'health maintenance',
                'employment', 'vocational', 'housing', 'education',
                'administrative', 'appointment', 'referral', 'encounter',
                'followup', 'follow up', 'follow-up'
            ]

            # Also filter out Z-codes that are administrative/social (ICD-10-CM Z codes)
            non_medical_z_codes = [
                'Z71.3',  # Dietary counseling
                'Z56.0',  # Unemployment
                'V65.9',  # Health maintenance (ICD-9)
                'Z00.',   # General examination
                'Z01.',   # Special examinations
            ]

            # Skip if contains non-medical keywords
            if any(keyword in diagnosis_lower for keyword in non_medical_keywords):
                continue

            # Skip if contains non-medical Z-codes
            if any(zcode in diagnosis for zcode in non_medical_z_codes):
                continue

            # Extract base diagnosis name (text before first parenthesis)
            base_name_match = re.match(r'^([^(]+)', diagnosis)
            if base_name_match:
                base_name = base_name_match.group(1).strip().lower()
                # Remove trailing * and whitespace
                base_name = base_name.rstrip('*').strip()

                # Clean up common variations
                # e.g., "Disorder due to type 1 diabetes mellitus" vs "Diabetes mellitus"
                # Keep the more specific one (longer)

                # Check for duplicates based on base name
                is_duplicate = False
                for existing_base in list(diagnosis_base_names.keys()):
                    # Check if this is a duplicate or variation
                    if base_name == existing_base:
                        # Exact duplicate - prefer ICD-10-CM over ICD-9-CM
                        # Prefer entries with SCT codes over those without
                        existing_diagnosis = diagnosis_base_names[existing_base]

                        # Scoring system: ICD-10-CM=2, SCT=3, ICD-9-CM=1
                        new_score = 0
                        if 'ICD-10-CM' in diagnosis:
                            new_score += 2
                        if 'SCT' in diagnosis:
                            new_score += 3
                        if 'ICD-9-CM' in diagnosis:
                            new_score += 1

                        existing_score = 0
                        if 'ICD-10-CM' in existing_diagnosis:
                            existing_score += 2
                        if 'SCT' in existing_diagnosis:
                            existing_score += 3
                        if 'ICD-9-CM' in existing_diagnosis:
                            existing_score += 1

                        if new_score > existing_score:
                            # Replace with better-coded version
                            idx = diagnoses.index(existing_diagnosis)
                            diagnoses[idx] = diagnosis
                            diagnosis_base_names[base_name] = diagnosis

                        is_duplicate = True
                        break

                    # Check if one is a substring of the other (similar diagnoses)
                    elif base_name in existing_base or existing_base in base_name:
                        # Keep the more specific (longer) one
                        if len(base_name) > len(existing_base):
                            # New one is more specific
                            existing_diagnosis = diagnosis_base_names[existing_base]
                            idx = diagnoses.index(existing_diagnosis)
                            diagnoses[idx] = diagnosis
                            del diagnosis_base_names[existing_base]
                            diagnosis_base_names[base_name] = diagnosis
                        # Otherwise keep existing (more specific)
                        is_duplicate = True
                        break

                if not is_duplicate:
                    diagnoses.append(diagnosis)
                    diagnosis_base_names[base_name] = diagnosis

    if not diagnoses:
        return ""

    # Return as numbered list
    return '\n'.join(diagnoses)


def extract_pmh_from_note(note_content: str) -> str:
    """
    Extract PMH section from a clinical note (alternative format).

    Some notes may have a "PMH:" or "Past Medical History:" section
    instead of the ALL PROBLEMS LIST format.

    Args:
        note_content: Full text of a clinical note

    Returns:
        Extracted PMH text, or "" if not found
    """
    # Pattern: "PMH:" or "Past Medical History:" followed by content
    # Until next major section
    # CRITICAL: Include PAST SURGICAL HISTORY as stop marker
    pattern = r'(?:PMH|PAST MEDICAL HISTORY):\s*(.*?)(?=\n\s*(?:PSH:|PAST SURGICAL HISTORY:|ROS:|PE:|PHYSICAL|EXAM:|ASSESSMENT:|PLAN:|Past Surgical|Review of Systems|Physical Exam|MEDICATIONS:|ALLERGIES:|Social History|SOCIAL:|FAMILY|SEXUAL|PSA|PATHOLOGY|------|^\s*[A-Z][A-Z\s]+:(?!\w))|$)'

    match = re.search(pattern, note_content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    if match:
        pmh_text = match.group(1).strip()

        # Parse numbered list format
        # Example: "1. Diagnosis\n2. Another diagnosis"
        lines = pmh_text.split('\n')
        diagnoses = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Remove leading numbers and periods
            clean_line = re.sub(r'^\d+\.\s*', '', line)
            if clean_line:
                diagnoses.append(clean_line)

        # Return raw diagnoses (agent will number them)
        return '\n'.join(diagnoses) if diagnoses else pmh_text

    return ""
