"""
HPI (History of Present Illness) Agent

Combines HPIs from all notes with Assessments and Plans, focusing on current urologic HPI.

Includes HALLUCINATION DETECTION via deterministic fact verification.
All synthesized HPI is checked against ground truth extracted from source.
"""

from typing import List, Dict, Optional, Tuple, Union
from ..llm_helper import combine_sections_with_llm, synthesize_with_llm
from .history_cleaners import clean_llm_commentary
from ..extractors.hpi_fact_verifier import (
    HPIFactVerifier,
    HPIVerificationResult,
    verify_hpi_against_source
)
import re
import logging

logger = logging.getLogger(__name__)


def synthesize_hpi(
    gu_notes: List[Dict[str, str]],
    non_gu_notes: List[Dict[str, str]],
    psa_data: Optional[str] = None,
    pathology_data: Optional[str] = None,
    labs_data: Optional[str] = None,
    imaging_data: Optional[str] = None,
    cross_specialty_context: Optional[str] = None,
    visit_progression: Optional[str] = None,
    prior_ap_context: Optional[str] = None,
    verify_facts: bool = True,
    return_verification: bool = False
) -> Union[str, Tuple[str, Optional[HPIVerificationResult]]]:
    """
    Synthesize HPI from GU notes with clinical context.

    Note: Stage 1 only includes HPIs from previous notes. Assessment and Plan
    are NOT available as they are Stage 2 (completed after patient visit).

    Focus on creating a current UROLOGY HPI from available GU notes,
    enriched with recent lab results, pathology, and imaging findings
    so the HPI reflects the patient's current clinical status.

    INCLUDES HALLUCINATION DETECTION:
    - Extracts ground truth PSA values, lab results, and findings from source BEFORE synthesis
    - Verifies all claims in LLM output against ground truth
    - Flags or corrects any hallucinated content (e.g., fabricated PSA values)

    PRIOR A&P CONTEXT INTEGRATION:
    - Uses prior Assessment and Plan context to inform HPI narrative
    - Provides awareness of what was previously diagnosed and planned
    - Enables temporal continuity in follow-up visit HPIs

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries (NOT USED - kept for API compatibility)
        psa_data: Raw PSA values extracted from document (optional)
        pathology_data: Raw pathology results extracted from document (optional)
        labs_data: Raw lab results extracted from document (optional)
        imaging_data: Raw imaging results extracted from document (optional)
        cross_specialty_context: Urologic content from non-GU specialty notes (optional)
        visit_progression: Narrative of what changed since last visit (optional)
        prior_ap_context: Formatted prior Assessment & Plan context (optional)
        verify_facts: If True (default), verify synthesis against source facts
        return_verification: If True, return (text, HPIVerificationResult) tuple

    Returns:
        Synthesized HPI text focused on current urologic status.
        If return_verification=True, returns (text, HPIVerificationResult) tuple.
    """
    # Collect HPIs from GU notes ONLY
    # Non-GU HPIs are excluded to prevent contamination with irrelevant content
    # (headaches, dizziness, ankle pain, etc. should not appear in urology HPI)
    hpi_instances = []

    # GU notes: HPIs only (Assessment/Plan are Stage 2)
    for note in gu_notes:
        if note.get("HPI"):
            hpi_instances.append(note['HPI'])

    # Non-GU notes: EXCLUDED from HPI synthesis
    # Reason: Non-GU HPIs contain non-urological content that confuses the LLM
    # and results in HPI discussing headaches, mental health, orthopedic issues, etc.
    # for note in non_gu_notes:
    #     if note.get("HPI"):
    #         hpi_instances.append(f"Non-GU HPI: {note['HPI']}")

    if not hpi_instances:
        return ""

    # If only one instance, clean it up
    if len(hpi_instances) == 1:
        # Remove our internal labels
        result = hpi_instances[0]
        result = result.replace("Non-GU HPI: ", "")
        # Replace "consult" with "followup" terminology
        import re
        result = re.sub(r'\burology\s+consult\b', 'urology followup', result, flags=re.IGNORECASE)
        result = re.sub(r'\bconsult\s+for\b', 'followup for', result, flags=re.IGNORECASE)
        result = re.sub(r'\bfor\s+a\s+urology\s+consult\b', 'for a urology followup', result, flags=re.IGNORECASE)
        return result

    # Build clinical context section from available data
    clinical_context = ""
    context_parts = []
    if psa_data and psa_data.strip():
        context_parts.append(f"RECENT PSA VALUES:\n{psa_data}")
    if pathology_data and pathology_data.strip():
        context_parts.append(f"PATHOLOGY RESULTS:\n{pathology_data}")
    if labs_data and labs_data.strip():
        # Limit labs to reasonable length for HPI context
        labs_summary = labs_data[:1500] if len(labs_data) > 1500 else labs_data
        context_parts.append(f"RELEVANT LAB RESULTS:\n{labs_summary}")
    if imaging_data and imaging_data.strip():
        # Limit imaging to reasonable length for HPI context
        imaging_summary = imaging_data[:1500] if len(imaging_data) > 1500 else imaging_data
        context_parts.append(f"IMAGING FINDINGS:\n{imaging_summary}")

    # Add cross-specialty urologic context (from non-GU notes)
    if cross_specialty_context and cross_specialty_context.strip():
        context_parts.append(f"CROSS-SPECIALTY UROLOGIC FINDINGS:\n{cross_specialty_context}")

    # Add visit progression analysis (what changed since last visit)
    if visit_progression and visit_progression.strip():
        context_parts.append(f"VISIT PROGRESSION (since last urology visit):\n{visit_progression}")

    # Add prior Assessment & Plan context (for temporal continuity in follow-up visits)
    if prior_ap_context and prior_ap_context.strip():
        context_parts.append(f"PRIOR ASSESSMENT & PLAN CONTEXT:\n{prior_ap_context}")

    if context_parts:
        clinical_context = "\n\n=== CLINICAL DATA CONTEXT (reference these findings in the HPI where relevant) ===\n" + "\n\n".join(context_parts) + "\n=== END CLINICAL DATA CONTEXT ===\n"

    # Use LLM to synthesize comprehensive HPI
    instructions = f"""
Create a current, comprehensive UROLOGY HPI that synthesizes all available urologic information from the source notes into a cohesive narrative.

{clinical_context}

STRUCTURE:
0. TEMPORAL FRAMING (CRITICAL for followup visits):
   - If VISIT PROGRESSION data is provided, this is a FOLLOWUP visit
   - Start by referencing what was recommended at the last visit
   - Describe what has happened since (completed procedures, test results, ongoing treatments)
   - Then present the patient's current status and reason for today's visit
   - Example opening: "Mr. X returns for followup after prostate biopsy which revealed..."
1. Start with the patient's current chief complaint and presenting urologic issue
2. Include relevant history from past visits in chronological flow
3. Document urologic symptoms, test results, and diagnoses that are mentioned
4. Write in narrative paragraph form (not bullet points)

CONTENT REQUIREMENTS:
- USE all urologically relevant information provided in the source notes
- INCLUDE: GU symptoms, urologic diagnoses, test results (PSA, imaging, pathology), medications, and treatments that are documented
- INCLUDE: Relevant surgical history if mentioned
- SYNTHESIZE information from multiple visits into a coherent story
- MAINTAIN chronological progression when discussing the patient's condition
- CRITICAL: If PSA values, pathology results, or imaging findings are provided in the CLINICAL DATA CONTEXT above, you MUST reference the most recent/relevant ones in the HPI narrative. These are this patient's actual results.
- For PSA: mention the most recent value and trend (rising, stable, declining)
- For pathology: mention Gleason score, grade group, and key findings if present
- For imaging: mention key urologic findings from recent imaging

CROSS-SPECIALTY INTEGRATION (when CROSS-SPECIALTY UROLOGIC FINDINGS provided):
- Integrate urologically-relevant findings from other specialties into the narrative
- Hospital admissions for urologic reasons (urosepsis, hematuria, retention) - include admission details and outcome
- Oncology treatment requests (ADT, chemotherapy) - note what was requested and current status
- Radiation Oncology coordination - note if radiation was recommended, started, or completed
- Cancelled or rescheduled procedures - note the cancellation and reason if documented
- Cardiology/ID clearances or concerns - note relevant clearance status for pending procedures
- ONLY include cross-specialty content that is UROLOGICALLY RELEVANT
- Do NOT include non-urologic findings (pure cardiac, pulmonary, etc.)

PRIOR ASSESSMENT & PLAN INTEGRATION (when PRIOR A&P CONTEXT provided):
- Use prior A&P context to inform the HPI narrative with clinical progression
- Reference what was diagnosed and planned at previous visits
- Mention completed procedures and their results (e.g., "biopsy completed showing...")
- Note patient treatment decisions (e.g., "patient declined radiation therapy")
- Identify what issues remain outstanding from prior visits
- Frame the current visit in context of the clinical progression
- Example: "Mr. X returns for followup of prostate cancer Gleason 4+3=7 diagnosed on biopsy in October 2025. At last visit, staging workup was recommended. PSMA PET completed December 2025 showed disease confined to prostate. He was evaluated by radiation oncology and declined brachytherapy. Today he presents to discuss systemic therapy options."

ANTI-HALLUCINATION RULES:
- DO NOT invent procedures or treatments not mentioned in the notes
- DO NOT assume treatments based on diagnoses alone unless explicitly stated
- DO NOT add information from your general medical knowledge
- If a procedure is listed in past surgical history, you may include it
- If test results are mentioned (PSA values, imaging findings), include them
- Use ONLY the PSA values provided in the CLINICAL DATA CONTEXT - do NOT fabricate PSA values

EXCLUDE:
- Non-urologic health issues (cardiac, pulmonary, orthopedic, etc.) unless directly relevant to urologic care
- Administrative details and metadata
- Verbatim repetition - synthesize instead

IMPORTANT TERMINOLOGY:
- Replace "urology consult" with "urology followup" (this is a followup visit, not a new consult)
- Replace "consult for" with "followup for"
- Replace "for a urology consult" with "for a urology followup"
- This is a FOLLOWUP visit, not an initial consultation

IMPORTANT: If the source notes contain urologic consultation details, history, symptoms, or findings, you MUST use that information to create the HPI. Do NOT say "no information available" if urologic data exists in the source notes.

Provide ONLY the clinical narrative HPI. NO meta-commentary, NO explanations like "Based on the notes" or "Here is the HPI". Just the narrative itself, starting directly with the patient presentation.
"""

    synthesized_hpi = combine_sections_with_llm(
        section_name="History of Present Illness",
        section_instances=hpi_instances,
        instructions=instructions
    )

    cleaned_hpi = clean_llm_commentary(synthesized_hpi)

    # STEP: Verify HPI against ground truth facts
    verification_result = None
    if verify_facts and cleaned_hpi:
        verifier = HPIFactVerifier()

        # Extract facts from source documents
        for note in gu_notes:
            if note.get("HPI"):
                verifier.extract_facts_from_source(note["HPI"])

        # Extract facts from clinical context
        if psa_data:
            verifier.extract_facts_from_psa_data(psa_data)

        if labs_data:
            verifier.extract_facts_from_labs(labs_data)

        if pathology_data:
            verifier.extract_facts_from_source(pathology_data)

        # Verify synthesis
        if verifier.ground_truth_facts:
            verification_result = verifier.verify_synthesis(cleaned_hpi)

            if not verification_result.is_verified:
                logger.warning(
                    f"HPI synthesis verification FAILED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Potential hallucinations: {verification_result.potential_hallucinations}"
                )

                # Use corrected text if available
                if verification_result.corrected_text:
                    logger.info("Using corrected HPI text with hallucinations flagged")
                    cleaned_hpi = verification_result.corrected_text
            else:
                logger.debug(
                    f"HPI synthesis VERIFIED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Verified claims: {verification_result.verified_claims}"
                )

    if return_verification:
        return cleaned_hpi, verification_result
    return cleaned_hpi


def synthesize_consult_hpi(
    consult_reason: str,
    patient_name: Optional[str] = None,
    patient_age: Optional[str] = None,
    patient_sex: Optional[str] = None,
    pmh: Optional[str] = None,
    psh: Optional[str] = None,
    medications: Optional[str] = None,
    imaging: Optional[str] = None,
    pcp_note_data: Optional[Dict[str, str]] = None,
    provider_urologic_context: Optional[str] = None,
    reason_for_request: Optional[str] = None,
    psa_data: Optional[str] = None,
    pathology_data: Optional[str] = None,
    labs_data: Optional[str] = None,
    verify_facts: bool = True,
    return_verification: bool = False
) -> Union[str, Tuple[str, Optional[HPIVerificationResult]]]:
    """
    Synthesize comprehensive HPI for consult requests.

    Per instructions.txt workflow:
    - Initial HPI from Reason for Request / Reason for Consult Request
    - Scan provider notes (Current PC Provider, Requesting Provider) for urologic content
    - Combine and synthesize comprehensive HPI

    Creates a detailed narrative HPI by combining:
    - Patient demographics (name, age)
    - Consult reason (Provisional Diagnosis)
    - Reason for Request / Reason for Consult Request
    - Provider urologic context (from note scanning)
    - Relevant medical history (PMH, PSH)
    - Current medications (urologic focus)
    - Recent imaging findings
    - PCP note information

    Args:
        consult_reason: Brief consult request reason (from Reason for Consult Request)
        patient_name: Patient name (without titles)
        patient_age: Patient age
        pmh: Past medical history
        psh: Past surgical history
        medications: Current medications list
        imaging: Recent imaging reports
        pcp_note_data: Dict with PCP note extractions (social, family, hpi, etc.)
        provider_urologic_context: Urologic content from provider note scanning
        reason_for_request: Additional reason text (Reason For Request field)

    Returns:
        Comprehensive narrative HPI suitable for urology consult
    """
    # Build context sections for LLM synthesis
    context_sections = []

    # Add consult reason (primary driver - from Reason for Consult Request)
    context_sections.append(f"CONSULT REASON (from Reason for Consult Request):\n{consult_reason}")

    # Add Reason For Request if different and provided
    # Per instructions.txt: HPI = Reason for Request + Reason for Consult Request
    if reason_for_request and reason_for_request.strip():
        if reason_for_request.strip() != consult_reason.strip():
            context_sections.append(f"ADDITIONAL REQUEST DETAILS (from Reason For Request):\n{reason_for_request}")

    # Add provider urologic context (from provider note scanning)
    # Per instructions.txt: scan Requesting Provider and Current PC Provider notes
    # for urologic mentions and combine with consult request HPI
    if provider_urologic_context and provider_urologic_context.strip():
        context_sections.append(f"PROVIDER NOTES UROLOGIC CONTEXT:\n{provider_urologic_context}")

    # Add patient demographics
    if patient_name or patient_age or patient_sex:
        demo = []
        if patient_name:
            demo.append(f"Name: {patient_name}")
        if patient_age:
            demo.append(f"Age: {patient_age}")
        if patient_sex:
            demo.append(f"Sex: {patient_sex}")
        context_sections.append(f"PATIENT DEMOGRAPHICS:\n{', '.join(demo)}")

    # Add PMH (focus on urologic conditions)
    if pmh:
        # Extract urologic conditions
        urologic_keywords = [
            'kidney', 'renal', 'stone', 'calculi', 'nephrolithiasis',
            'prostate', 'bph', 'benign prostatic',
            'bladder', 'urinary', 'hematuria', 'incontinence',
            'uti', 'ureter', 'hydronephrosis',
            'psa', 'cancer', 'carcinoma',
            'erectile', 'testosterone', 'hypogonadism'
        ]

        pmh_lines = [line.strip() for line in pmh.split('\n') if line.strip()]
        urologic_pmh = []
        for line in pmh_lines:
            if any(kw in line.lower() for kw in urologic_keywords):
                urologic_pmh.append(line)

        if urologic_pmh:
            context_sections.append(f"RELEVANT MEDICAL HISTORY:\n" + '\n'.join(urologic_pmh[:10]))  # Limit to top 10

    # Add PSH (focus on urologic procedures)
    if psh:
        urologic_proc_keywords = [
            'ureteroscopy', 'lithotripsy', 'turp', 'turbt',
            'prostatectomy', 'cystoscopy', 'nephrectomy',
            'kidney', 'bladder', 'prostate', 'ureter',
            'stone', 'calculus', 'stent'
        ]

        psh_lines = [line.strip() for line in psh.split('\n') if line.strip()]
        urologic_psh = []
        for line in psh_lines:
            if any(kw in line.lower() for kw in urologic_proc_keywords):
                urologic_psh.append(line)

        if urologic_psh:
            context_sections.append(f"RELEVANT SURGICAL HISTORY:\n" + '\n'.join(urologic_psh))

    # Add medications (focus on urologic meds)
    if medications:
        urologic_meds = [
            'tamsulosin', 'flomax', 'finasteride', 'proscar',
            'dutasteride', 'avodart', 'alfuzosin', 'silodosin',
            'testosterone', 'androgel', 'tadalafil', 'cialis',
            'sildenafil', 'viagra', 'oxybutynin', 'tolterodine',
            'solifenacin', 'mirabegron', 'trospium'
        ]

        med_lines = [line.strip() for line in medications.split('\n') if line.strip()]
        urologic_medication_list = []
        for line in med_lines:
            if any(med in line.lower() for med in urologic_meds):
                urologic_medication_list.append(line)

        if urologic_medication_list:
            context_sections.append(f"UROLOGIC MEDICATIONS:\n" + '\n'.join(urologic_medication_list))

    # Add imaging
    if imaging:
        # Limit imaging to reasonable length
        imaging_summary = imaging[:1000] if len(imaging) > 1000 else imaging
        context_sections.append(f"RECENT IMAGING:\n{imaging_summary}")

    # Add PSA data if available
    if psa_data and psa_data.strip():
        context_sections.append(f"PSA VALUES:\n{psa_data}")

    # Add pathology results if available
    if pathology_data and pathology_data.strip():
        pathology_summary = pathology_data[:1500] if len(pathology_data) > 1500 else pathology_data
        context_sections.append(f"PATHOLOGY RESULTS:\n{pathology_summary}")

    # Add lab results if available
    if labs_data and labs_data.strip():
        labs_summary = labs_data[:1000] if len(labs_data) > 1000 else labs_data
        context_sections.append(f"RELEVANT LAB RESULTS:\n{labs_summary}")

    # Add PCP note details if available
    if pcp_note_data:
        if pcp_note_data.get('hpi'):
            context_sections.append(f"PCP NOTE HPI:\n{pcp_note_data['hpi']}")

    # Combine all context
    full_context = '\n\n'.join(context_sections)

    # Build prompt for LLM synthesis
    prompt = f"""You are a clinical documentation assistant creating a History of Present Illness (HPI) for a urology consult.

Create a comprehensive, narrative HPI based on the following information:

{full_context}

SYNTHESIS REQUIREMENTS (per consult workflow):
1. The primary HPI content comes from the CONSULT REASON and ADDITIONAL REQUEST DETAILS
2. The PROVIDER NOTES UROLOGIC CONTEXT contains additional urologic information from the requesting/primary care provider's notes
3. You MUST synthesize ALL of these sources into a cohesive narrative
4. Information from consult request may be sentence fragments - make them complete and coherent
5. Integrate provider note content to add clinical context and background

STRUCTURE:
1. Opening: "[Patient name] is a [age]-year-old [sex from demographics, lowercase] with history of [key urologic conditions] who presents [consult reason]"
2. Detail relevant urologic history chronologically
3. Include recent procedures and their timing/outcomes if mentioned
4. Note current urologic medications and their effectiveness if stated
5. Include pertinent imaging findings if available
6. End with relevant symptoms or clinical concerns

CONTENT REQUIREMENTS:
- USE ONLY information provided in the source data above
- Focus on UROLOGIC conditions and history
- Integrate all provided sections into a cohesive narrative
- Write in third person, past tense for history, present tense for current status
- Use complete sentences in paragraph form (not bullet points)
- Include specific dates, values, and findings when provided
- Mention previous providers if noted in consult reason
- IMPORTANT: The consult reason text may be incomplete or fragmentary - complete the sentences appropriately
- CRITICAL: If PSA values are provided, mention the most recent PSA and trend
- CRITICAL: If pathology results are provided (Gleason score, grade group), include them
- CRITICAL: If lab results are provided, include relevant abnormal findings

ANTI-HALLUCINATION RULES:
- DO NOT invent procedures, medications, symptoms, or findings not mentioned
- DO NOT add provider names unless stated in source
- DO NOT speculate about outcomes or effectiveness unless explicitly stated
- DO NOT include non-urologic conditions unless directly relevant to GU care
- If age is not provided, omit age reference
- If patient name is not provided, use "The patient" or "Patient"
- Use ONLY PSA values from the data provided - do NOT fabricate values

FORMATTING:
- Write 2-3 paragraphs maximum
- First paragraph: patient intro, primary urologic conditions, and consult reason
- Second paragraph (if needed): detailed history, procedures, imaging findings
- Keep concise but comprehensive (target 200-400 words)

EXAMPLE OPENING:
"Mr. Kile is a 74-year-old male with history of recurrent kidney stones and BPH who presents today as a new VA urology patient. He previously followed with a civilian urologist but no longer has outside insurance."

Provide ONLY the narrative HPI. NO meta-commentary, NO explanations. Just the clinical narrative.
"""

    # Call LLM directly with zero temperature for deterministic synthesis
    synthesized_hpi = synthesize_with_llm(
        prompt=prompt,
        temperature=0.0
    )

    cleaned_hpi = clean_llm_commentary(synthesized_hpi)

    # STEP: Verify HPI against ground truth facts
    verification_result = None
    if verify_facts and cleaned_hpi:
        verifier = HPIFactVerifier()

        # Extract facts from source documents
        if consult_reason:
            verifier.extract_facts_from_source(consult_reason)
        if reason_for_request:
            verifier.extract_facts_from_source(reason_for_request)
        if provider_urologic_context:
            verifier.extract_facts_from_source(provider_urologic_context)

        # Extract facts from clinical context
        if psa_data:
            verifier.extract_facts_from_psa_data(psa_data)

        if labs_data:
            verifier.extract_facts_from_labs(labs_data)

        if pathology_data:
            verifier.extract_facts_from_source(pathology_data)

        if imaging:
            verifier.extract_facts_from_source(imaging)

        # Verify synthesis
        if verifier.ground_truth_facts:
            verification_result = verifier.verify_synthesis(cleaned_hpi)

            if not verification_result.is_verified:
                logger.warning(
                    f"Consult HPI synthesis verification FAILED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Potential hallucinations: {verification_result.potential_hallucinations}"
                )

                # Use corrected text if available
                if verification_result.corrected_text:
                    logger.info("Using corrected consult HPI text with hallucinations flagged")
                    cleaned_hpi = verification_result.corrected_text
            else:
                logger.debug(
                    f"Consult HPI synthesis VERIFIED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Verified claims: {verification_result.verified_claims}"
                )

    if return_verification:
        return cleaned_hpi, verification_result
    return cleaned_hpi
