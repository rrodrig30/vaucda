"""
HPI (History of Present Illness) Agent

Combines HPIs from all notes with Assessments and Plans, focusing on current urologic HPI.
"""

from typing import List, Dict, Optional
from ..llm_helper import combine_sections_with_llm, synthesize_with_llm
from .history_cleaners import clean_llm_commentary
import re


def synthesize_hpi(gu_notes: List[Dict[str, str]], non_gu_notes: List[Dict[str, str]]) -> str:
    """
    Synthesize HPI from all notes.

    Note: Stage 1 only includes HPIs from previous notes. Assessment and Plan
    are NOT available as they are Stage 2 (completed after patient visit).

    Focus on creating a current UROLOGY HPI from available historical data.

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries

    Returns:
        Synthesized HPI text focused on current urologic status
    """
    # Collect HPIs from all notes
    hpi_instances = []

    # GU notes: HPIs only (Assessment/Plan are Stage 2)
    for note in gu_notes:
        if note.get("HPI"):
            hpi_instances.append(note['HPI'])

    # Non-GU notes: Only HPIs
    for note in non_gu_notes:
        if note.get("HPI"):
            hpi_instances.append(f"Non-GU HPI: {note['HPI']}")

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

    # Use LLM to synthesize comprehensive HPI
    instructions = """
Create a current, comprehensive UROLOGY HPI that synthesizes all available urologic information from the source notes into a cohesive narrative.

STRUCTURE:
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

ANTI-HALLUCINATION RULES:
- DO NOT invent procedures or treatments not mentioned in the notes
- DO NOT assume treatments based on diagnoses alone unless explicitly stated
- DO NOT add information from your general medical knowledge
- If a procedure is listed in past surgical history, you may include it
- If test results are mentioned (PSA values, imaging findings), include them

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

    return clean_llm_commentary(synthesized_hpi)


def synthesize_consult_hpi(
    consult_reason: str,
    patient_name: Optional[str] = None,
    patient_age: Optional[str] = None,
    pmh: Optional[str] = None,
    psh: Optional[str] = None,
    medications: Optional[str] = None,
    imaging: Optional[str] = None,
    pcp_note_data: Optional[Dict[str, str]] = None
) -> str:
    """
    Synthesize comprehensive HPI for consult requests.

    Creates a detailed narrative HPI by combining:
    - Patient demographics (name, age)
    - Consult reason
    - Relevant medical history (PMH, PSH)
    - Current medications (urologic focus)
    - Recent imaging findings
    - PCP note information

    Args:
        consult_reason: Brief consult request reason
        patient_name: Patient name (without titles)
        patient_age: Patient age
        pmh: Past medical history
        psh: Past surgical history
        medications: Current medications list
        imaging: Recent imaging reports
        pcp_note_data: Dict with PCP note extractions (social, family, hpi, etc.)

    Returns:
        Comprehensive narrative HPI suitable for urology consult
    """
    # Build context sections for LLM synthesis
    context_sections = []

    # Add consult reason (primary driver)
    context_sections.append(f"CONSULT REASON:\n{consult_reason}")

    # Add patient demographics
    if patient_name or patient_age:
        demo = []
        if patient_name:
            demo.append(f"Name: {patient_name}")
        if patient_age:
            demo.append(f"Age: {patient_age}")
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

STRUCTURE:
1. Opening: "[Patient name] is a [age]-year-old [male/female] with history of [key urologic conditions] who presents [consult reason]"
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

ANTI-HALLUCINATION RULES:
- DO NOT invent procedures, medications, symptoms, or findings not mentioned
- DO NOT add provider names unless stated in source
- DO NOT speculate about outcomes or effectiveness unless explicitly stated
- DO NOT include non-urologic conditions unless directly relevant to GU care
- If age is not provided, omit age reference
- If patient name is not provided, use "The patient" or "Patient"

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

    return clean_llm_commentary(synthesized_hpi)
