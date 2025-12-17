"""
Note Builder

Orchestrates the entire note processing pipeline:
1. Identify notes (GU and non-GU)
2. Extract data from notes
3. Extract document-level data
4. Synthesize all sections
5. Assemble final urology clinic note
"""

from pathlib import Path
from .note_identifier import identify_notes
from .agents.gu_agent import process_gu_notes
from .agents.non_gu_agent import process_non_gu_notes
from .extractors import extract_pmh, extract_medications, extract_pathology, extract_imaging
from .extractors.psh_extractor import extract_psh
from .extractors.consult_request_extractor import extract_consult_request
from .extractors.psa_extractor import extract_psa
from .extractors.lab_extractor import extract_labs, extract_stone_labs, extract_calcium_series
from .extractors.endocrine_extractor import extract_endocrine_labs
from .extractors.social_extractor import extract_social
from .extractors.family_extractor import extract_family
from .document_classifier import DocumentClassifier, extract_document_type
from .extractors.pcp_note_extractor import PCPNoteExtractor

# Import synthesis agents
from .agents.cc_agent import synthesize_cc
from .agents.hpi_agent import synthesize_hpi, synthesize_consult_hpi
from .agents.ipss_agent import synthesize_ipss
from .agents.diet_agent import synthesize_diet
from .agents.pmh_agent import synthesize_pmh
from .agents.psh_agent import synthesize_psh
from .agents.social_agent import synthesize_social
from .agents.family_agent import synthesize_family
from .agents.sexual_agent import synthesize_sexual
from .agents.psa_agent import synthesize_psa
from .agents.pathology_agent import synthesize_pathology
from .agents.medications_agent import synthesize_medications
from .agents.allergies_agent import synthesize_allergies
from .agents.lab_agents import (
    synthesize_endocrine_labs,
    synthesize_stone_labs,
    synthesize_general_labs,
    synthesize_testosterone
)
from .agents.imaging_agent import synthesize_imaging
from .agents.ros_agent import synthesize_ros
from .agents.pe_agent import synthesize_pe
# Note: Assessment and Plan are Stage 2 only (completed after patient visit)


def get_time_suffix(is_consult: bool = False) -> str:
    """
    Get the appropriate time billing suffix template.

    Args:
        is_consult: If True, returns 45-minute template; otherwise 40-minute template

    Returns:
        Time suffix template string
    """
    # Path to time suffix template file
    # __file__ is in backend/app/services/note_processing/, need to go up 5 levels to project root
    time_suffix_path = Path(__file__).parent.parent.parent.parent.parent / 'time suffix.txt'

    try:
        with open(time_suffix_path, 'r') as f:
            content = f.read()

        # Split by the separator line
        templates = content.split('++++++++++++++++++++++++++++++++++++++')

        if is_consult:
            # 45-minute version is the second template (index 1)
            if len(templates) >= 2:
                # Strip whitespace and any remaining plus signs
                template = templates[1].strip().lstrip('+').strip()
                return template
            else:
                # Fallback: try to find 45-minute section
                lines = content.split('\n')
                # Find where "Total: 45" appears and extract that section
                for i, line in enumerate(lines):
                    if 'Total:' in line and '45' in line:
                        # Go backwards to find start
                        start_idx = max(0, i - 35)  # Approximately 35 lines before
                        end_idx = min(len(lines), i + 5)  # A few lines after
                        return '\n'.join(lines[start_idx:end_idx])
        else:
            # 40-minute version is the first template (index 0)
            if len(templates) >= 1:
                # Strip whitespace and any remaining plus signs
                template = templates[0].strip().lstrip('+').strip()
                return template
            else:
                # Fallback: return first 40 lines
                lines = content.split('\n')
                return '\n'.join(lines[:40])

    except FileNotFoundError:
        # Return a basic template if file not found
        total_time = 45 if is_consult else 40
        return f"""
Time of Start:
Time End:
Time Spent in Chart prep, review, interpretation, & documentation: See Below
Total Time Spent: {total_time} minutes

Please note that I have spent >{total_time} total minutes in this visit including counseling,
coordination of care, chart review, lab interpretation, discussion of findings with the patient,
independent interpretation of data, communicating or referring to providers, formation of a
treatment plan with shared decision making, placing orders, coordinating follow-up and
documenting the encounter.
"""


def build_urology_note(clinical_document: str) -> str:
    """
    Build a comprehensive urology clinic note from a clinical document.

    This is the main entry point for the new agent-based architecture.

    Args:
        clinical_document: Full clinical document text

    Returns:
        Formatted urology clinic note
    """
    print("\n" + "="*80)
    print("BUILDING UROLOGY NOTE - New Agent-Based Architecture")
    print("="*80)

    # Step 1: Identify notes
    print("\n[1/5] Identifying notes...")
    notes_dict = identify_notes(clinical_document)
    gu_count = len(notes_dict["gu_notes"])
    non_gu_count = len(notes_dict["non_gu_notes"])
    consult_count = len(notes_dict.get("consult_requests", []))
    print(f"      Found {gu_count} GU notes, {non_gu_count} non-GU notes, and {consult_count} consult requests")

    # Determine if this is a consult
    is_consult = consult_count > 0

    # Step 2: Extract data from notes
    print("\n[2/5] Extracting data from notes...")
    gu_notes = process_gu_notes(notes_dict["gu_notes"])
    non_gu_notes = process_non_gu_notes(notes_dict["non_gu_notes"])
    print(f"      Processed {len(gu_notes)} GU note dictionaries")
    print(f"      Processed {len(non_gu_notes)} non-GU note dictionaries")

    # Step 3: Extract document-level data
    print("\n[3/5] Extracting document-level data...")

    # Initialize PCP note variables
    pcp_note_content = None
    pcp_data = None

    # NEW: For consult requests, use document classifier to extract from PCP notes
    if is_consult:
        print("      Using document classifier for consult request...")
        classifier = DocumentClassifier()
        classification = classifier.classify_document(clinical_document)

        # Extract PCP note content if present
        pcp_note_content = classifier.extract_document_segment(clinical_document, "PRIMARY_CARE_NOTE")

        if pcp_note_content:
            print(f"      Found PCP note ({len(pcp_note_content)} chars) - extracting data...")
            pcp_extractor = PCPNoteExtractor()
            pcp_data = pcp_extractor.extract_all(pcp_note_content)
            # Note: surgical history and dietary will be synthesized later

        # For consults, always extract social and family from full document
        # (they're in the consult request body, not PCP note)
        document_social = extract_social(clinical_document)
        document_family = extract_family(clinical_document)
    else:
        # For regular clinic notes, use standard extraction
        document_social = extract_social(clinical_document)
        document_family = extract_family(clinical_document)

    document_pmh = extract_pmh(clinical_document)
    document_psh = extract_psh(clinical_document)
    document_medications = extract_medications(clinical_document)
    document_pathology = extract_pathology(clinical_document)
    document_imaging = extract_imaging(clinical_document)
    document_psa = extract_psa(clinical_document)
    document_labs = extract_labs(clinical_document)
    document_stone_labs = extract_stone_labs(clinical_document)
    document_calcium = extract_calcium_series(clinical_document)
    document_endocrine = extract_endocrine_labs(clinical_document)

    print(f"      PMH: {len(document_pmh.split(chr(10)) if document_pmh else [])} diagnoses")
    print(f"      Medications: {len(document_medications.split(chr(10)) if document_medications else [])} meds")
    print(f"      Pathology: {'Found' if document_pathology else 'None'}")
    print(f"      Imaging: {'Found' if document_imaging else 'None'}")
    print(f"      PSA: {'Found' if document_psa else 'None'}")
    print(f"      Labs: {'Found' if document_labs else 'None'}")
    print(f"      Stone Labs: {'Found' if document_stone_labs else 'None'}")
    print(f"      Calcium Series: {'Found' if document_calcium else 'None'}")
    print(f"      Endocrine: {'Found' if document_endocrine else 'None'}")
    print(f"      Social: {'Found' if document_social else 'None'}")
    print(f"      Family: {'Found' if document_family else 'None'}")

    # Step 4: Synthesize all sections
    print("\n[4/5] Synthesizing sections...")

    # Extract CC and HPI from consult if present
    is_gu_consult = False
    consult_cc = None
    consult_hpi = None
    patient_name = None
    patient_ssn = None
    patient_age = None

    if is_consult:
        # Determine if this is a GU consult or non-GU consult
        consult_content = notes_dict["consult_requests"][0]["content"]
        # Check for "To Service:" line containing GU/Urology keywords
        is_gu_consult = any(keyword in consult_content.upper() for keyword in [
            "SURG GU", "GU OUTPATIENT", "UROLOGY", "URO "
        ])
        print(f"      Detected {'GU' if is_gu_consult else 'non-GU'} consult")

        # Extract CC and HPI from consult header
        consult_data = extract_consult_request(consult_content)
        if consult_data:
            consult_cc = consult_data.get("CC")
            consult_hpi = consult_data.get("HPI")
            print(f"      Extracted CC and HPI from consult request")

        # Extract patient demographics from FULL document (patient info may be in PCP notes)
        from .extractors.consult_request_extractor import ConsultRequestExtractor
        extractor = ConsultRequestExtractor()
        demographics = extractor.extract_patient_demographics(clinical_document)
        if demographics and demographics.get('patient_name'):
            patient_name = demographics.get('patient_name_formatted')
            patient_ssn = demographics.get('ssn')
            patient_age = demographics.get('age')
            print(f"      Extracted patient demographics from document")
            print(f"      Patient: {patient_name} (SSN: {patient_ssn}, Age: {patient_age})")

    # Use consult CC/HPI if available, otherwise synthesize from notes
    cc = consult_cc if consult_cc else synthesize_cc(gu_notes, non_gu_notes)
    print(f"      CC: {len(cc) if cc else 0} chars")

    # For consults, synthesize comprehensive HPI from all available data
    if is_consult and consult_hpi:
        # Use new consult HPI synthesis that incorporates all data
        hpi = synthesize_consult_hpi(
            consult_reason=consult_hpi,
            patient_name=patient_name,
            patient_age=patient_age,
            pmh=document_pmh,
            psh=None,  # Will be synthesized later
            medications=document_medications,
            imaging=document_imaging,
            pcp_note_data=pcp_data if is_consult and pcp_note_content else None
        )
    else:
        hpi = synthesize_hpi(gu_notes, non_gu_notes)
    print(f"      HPI: {len(hpi) if hpi else 0} chars")

    ipss = synthesize_ipss(gu_notes)
    print(f"      IPSS: {len(ipss) if ipss else 0} chars")

    dhx = synthesize_diet(gu_notes)
    pmh = synthesize_pmh(document_pmh, gu_notes, non_gu_notes)
    # For consults, use document-level PSH if available
    if is_consult and document_psh:
        psh = synthesize_psh([{"PSH": document_psh}], [])
    else:
        psh = synthesize_psh(gu_notes, non_gu_notes)

    # For consults, prefer document-level data (labs are in full document, not GU notes)
    if is_consult:
        social = document_social if document_social else synthesize_social(gu_notes, non_gu_notes)
        family = document_family if document_family else synthesize_family(gu_notes, non_gu_notes)
        # For consults, always prefer document-level PSA (comes from lab results)
        # Pass through PSA agent for proper formatting ([r] prefix, spacing)
        if document_psa:
            psa = synthesize_psa([{"PSA": document_psa}])
        else:
            psa = synthesize_psa(gu_notes)
        endocrine = document_endocrine if document_endocrine else synthesize_endocrine_labs(gu_notes)
        labs = document_labs if document_labs else synthesize_general_labs(gu_notes)
        # Use stone labs directly from document extraction
        stone = document_stone_labs if document_stone_labs else synthesize_stone_labs(gu_notes)
        # Don't append calcium series to general labs - it should only show if abnormal (via filtering) or in STONE LABS section
    else:
        social = synthesize_social(gu_notes, non_gu_notes)
        family = synthesize_family(gu_notes, non_gu_notes)
        psa = synthesize_psa(gu_notes)
        endocrine = synthesize_endocrine_labs(gu_notes)
        labs = synthesize_general_labs(gu_notes)
        stone = document_stone_labs if document_stone_labs else synthesize_stone_labs(gu_notes)
        # Don't append calcium series to general labs - it should only show if abnormal (via filtering) or in STONE LABS section

    sexual = synthesize_sexual(gu_notes, non_gu_notes)
    pathology = synthesize_pathology(document_pathology, gu_notes)
    testosterone = synthesize_testosterone(gu_notes)
    medications = synthesize_medications(document_medications, gu_notes)
    allergies = synthesize_allergies(gu_notes, non_gu_notes)
    imaging = synthesize_imaging(document_imaging, gu_notes)
    ros = synthesize_ros(gu_notes, non_gu_notes)
    pe = synthesize_pe(gu_notes, non_gu_notes)
    # Note: Assessment and Plan are NOT generated in Stage 1 - they are completed during/after the visit

    print(f"      Synthesized all sections")

    # Step 5: Assemble final note
    print("\n[5/5] Assembling final note...")
    final_note = assemble_note(
        cc=cc,
        hpi=hpi,
        ipss=ipss,
        dhx=dhx,
        pmh=pmh,
        psh=psh,
        social=social,
        family=family,
        sexual=sexual,
        psa=psa,
        pathology=pathology,
        testosterone=testosterone,
        medications=medications,
        allergies=allergies,
        endocrine=endocrine,
        stone=stone,
        labs=labs,
        imaging=imaging,
        ros=ros,
        pe=pe,
        is_consult=is_consult,
        is_gu_consult=is_gu_consult,
        patient_name=patient_name,
        patient_ssn=patient_ssn
        # Note: Assessment and Plan are NOT included in Stage 1 preliminary note
    )

    print(f"      Final note: {len(final_note)} characters")
    print("\n" + "="*80)
    print("NOTE BUILDING COMPLETE")
    print("="*80)

    return final_note


def assemble_note(**sections) -> str:
    """
    Assemble the final note from all synthesized sections.

    Args:
        **sections: All note sections as keyword arguments
        is_consult: Boolean flag indicating if this is a consult note
        is_gu_consult: Boolean flag indicating if this is a GU consult (vs non-GU)
        patient_name: Patient name (optional)
        patient_ssn: Full SSN (optional)

    Returns:
        Formatted note following urology_prompt.txt template or consult note template
    """
    note_parts = []
    is_consult = sections.get("is_consult", False)
    is_gu_consult = sections.get("is_gu_consult", True)  # Default to GU if not specified
    patient_name = sections.get("patient_name")
    patient_ssn = sections.get("patient_ssn")

    # Patient Header (if available)
    if patient_name or patient_ssn:
        header_parts = []
        if patient_name:
            header_parts.append(patient_name)
        if patient_ssn:
            header_parts.append(patient_ssn)

        patient_header = " ".join(header_parts)
        note_parts.append(f"Patient: {patient_header}\n")

    # CC (always required)
    if sections.get("cc"):
        note_parts.append(f"CC: {sections['cc']}\n")
    else:
        note_parts.append("CC: Unknown\n")

    # HPI (always required)
    if sections.get("hpi"):
        note_parts.append(f"HPI: {sections['hpi']}\n")
    else:
        note_parts.append("HPI: Unknown\n")

    # Continue with all sections for both consults and clinic notes

    # IPSS
    if sections.get("ipss"):
        note_parts.append(f"IPSS:\n{sections['ipss']}\n")
    else:
        # Always include IPSS section for urology notes (placeholder if not documented)
        note_parts.append("IPSS: Not documented\n")

    # Dietary History
    if sections.get("dhx"):
        note_parts.append(f"DIETARY HISTORY:\n{sections['dhx']}\n")
    else:
        # Always include dietary section for urology notes
        note_parts.append("DIETARY HISTORY: Not documented\n")

    # Social History
    if sections.get("social"):
        note_parts.append(f"SOCIAL HISTORY:\n{sections['social']}\n")

    # Family History
    if sections.get("family"):
        note_parts.append(f"FAMILY HISTORY:\n{sections['family']}\n")

    # Sexual History
    if sections.get("sexual"):
        note_parts.append(f"SEXUAL HISTORY:\n{sections['sexual']}\n")

    # PMH
    if sections.get("pmh"):
        note_parts.append(f"PAST MEDICAL HISTORY:\n{sections['pmh']}\n")

    # PSH
    if sections.get("psh"):
        note_parts.append(f"PAST SURGICAL HISTORY:\n{sections['psh']}\n")

    # PSA Curve
    if sections.get("psa"):
        note_parts.append(f"PSA CURVE:\n{sections['psa']}\n")

    # Medications
    if sections.get("medications"):
        note_parts.append(f"MEDICATIONS:\n{sections['medications']}\n")

    # Allergies
    if sections.get("allergies"):
        note_parts.append(f"\nALLERGIES: {sections['allergies']}\n")

    # Pathology
    if sections.get("pathology"):
        note_parts.append(f"\n{'='*78}\nPATHOLOGY:\n{sections['pathology']}\n")
    else:
        # Always include pathology section for urology notes
        note_parts.append(f"\n{'='*78}\nPATHOLOGY: None documented\n")

    # Testosterone
    if sections.get("testosterone"):
        note_parts.append(f"\n{'='*78}\nTESTOSTERONE:\n{sections['testosterone']}\n")

    # Endocrine Labs
    if sections.get("endocrine"):
        note_parts.append(f"\n{'='*35}ENDOCRINE LABS {'='*29}\n{sections['endocrine']}\n")

    # Stone Labs - Only show if patient has history of nephrolithiasis
    if sections.get("stone"):
        # Check for kidney stone history in PMH
        pmh_text = sections.get("pmh", "").lower()
        has_stone_history = any(term in pmh_text for term in [
            "nephrolithiasis", "kidney stone", "renal calculi", "urolithiasis",
            "calculus", "stone disease", "kidney calculi", "renal stone"
        ])

        if has_stone_history:
            note_parts.append(f"\n{'='*32}STONE RELATED LABS {'='*28}\n{sections['stone']}\n")

    # General Labs (moved to after Stone Labs)
    if sections.get("labs"):
        note_parts.append(f"\n{'='*38} LABS {'='*34}\n{sections['labs']}\n")

    # Imaging
    if sections.get("imaging"):
        note_parts.append(f"\n{'='*38} IMAGING {'='*32}\n{sections['imaging']}\n")

    # ROS
    if sections.get("ros"):
        note_parts.append(f"\n{'='*77}\n{sections['ros']}\n")

    # PE
    if sections.get("pe"):
        note_parts.append(f"{sections['pe']}\n")

    # Note: Assessment and Plan are NOT included in Stage 1 preliminary note
    # They will be added by the provider during/after the patient visit (Stage 2)

    # Note: Time billing suffix is NOT included in Stage 1 preliminary note
    # It will be added in Stage 2 after Assessment and Plan (via stage2_builder.py)

    # Assemble
    final_note = '\n'.join(note_parts)

    return final_note
