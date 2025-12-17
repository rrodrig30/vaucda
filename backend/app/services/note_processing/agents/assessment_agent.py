"""
Assessment Agent (Stage 2 Only)

Synthesizes assessment/impression using:
- Stage 1 preliminary note
- Prior assessments from historical GU notes
- Ambient listening transcript
- Calculator results
- RAG content (evidence-based guidelines)
"""

import re
from typing import List, Optional
from ..llm_helper import synthesize_with_llm
from .history_cleaners import clean_llm_commentary


def synthesize_assessment(
    stage1_note: str,
    prior_assessments: List[str] = None,
    ambient_transcript: Optional[str] = None,
    calculator_results: Optional[dict] = None,
    rag_content: Optional[str] = None,
    model: Optional[str] = None
) -> str:
    """
    Synthesize clinical assessment for Stage 2 (post-visit).

    Args:
        stage1_note: Complete preliminary note from Stage 1
        prior_assessments: List of Assessment sections from prior GU notes only
        ambient_transcript: Provider-patient conversation transcript (if available)
        calculator_results: Results from 44 specialized calculators (if available)
        rag_content: Evidence-based guidelines from Neo4j RAG (if available)

    Returns:
        Synthesized assessment text (4-8 sentence narrative summary)
    """
    if not prior_assessments:
        prior_assessments = []

    # Collect all Assessment sections from prior notes
    all_assessments = [a for a in prior_assessments if a and a.strip()]

    # Build comprehensive context for LLM synthesis
    context_parts = []

    # Add Stage 1 note context (if provided)
    if stage1_note and stage1_note.strip():
        context_parts.append(f"=== STAGE 1 PRELIMINARY NOTE (HISTORICAL DATA) ===\n{stage1_note}\n")

    # Add ambient transcript (if available)
    if ambient_transcript and ambient_transcript.strip():
        context_parts.append(f"=== PROVIDER-PATIENT CONVERSATION (AMBIENT LISTENING) ===\n{ambient_transcript}\n")

    # Add calculator results (if available)
    if calculator_results:
        calc_summary = []
        for calc_name, calc_result in calculator_results.items():
            calc_summary.append(f"{calc_name}: {calc_result}")
        if calc_summary:
            context_parts.append(f"=== CLINICAL CALCULATOR RESULTS ===\n" + "\n".join(calc_summary) + "\n")

    # Add RAG content (if available)
    if rag_content and rag_content.strip():
        context_parts.append(f"=== EVIDENCE-BASED GUIDELINES (RAG) ===\n{rag_content}\n")

    # Add prior assessments
    if all_assessments:
        context_parts.append(f"=== PRIOR CLINICAL ASSESSMENTS ===")
        for i, assessment in enumerate(all_assessments, 1):
            context_parts.append(f"\n--- Prior Assessment {i} ---\n{assessment}")

    # If only prior assessments and no other context, return the single assessment
    if len(all_assessments) == 1 and not any([stage1_note, ambient_transcript, calculator_results, rag_content]):
        return all_assessments[0]

    # Build comprehensive synthesis prompt
    full_context = "\n".join(context_parts)

    instructions = f"""
You are synthesizing a comprehensive clinical ASSESSMENT for a urology patient.

AVAILABLE INFORMATION:
{full_context}

TASK:
Create a 4-8 sentence narrative assessment that:
1. Integrates information from ALL available sources (Stage 1 note, prior assessments, ambient conversation, calculator results, evidence-based guidelines)
2. Focuses on the CURRENT urologic clinical impression
3. Incorporates calculator results and evidence-based recommendations where applicable
4. Uses the most recent and relevant clinical information
5. Removes duplicate diagnoses/impressions
6. Maintains clinical accuracy and completeness
7. Focuses ONLY on urologically relevant conditions

CLINICAL AWARENESS REQUIREMENTS:
- REVIEW the PSA CURVE section in the Stage 1 note above - it contains all PSA values for this patient
- If the Stage 1 note contains a PSA CURVE section with values, acknowledge the PSA data in your assessment
- DO NOT say "PSA level is not provided" or "PSA level is not mentioned" if the PSA CURVE section exists
- If you reference PSA values, they must come directly from the PSA CURVE section
- Use ONLY data values that appear in the Stage 1 note above
- DO NOT invent or hallucinate lab values, PSA values, or any numeric data
- If a lab value is mentioned, it must match EXACTLY what is shown in the Stage 1 note

CRITICAL REQUIREMENTS:
- Provide ONLY the assessment narrative
- NO meta-commentary (no "Based on the information", no "Here is", no "The assessment shows")
- NO explanations about what you included/excluded
- NO preamble or introduction
- Just the clean, clinical assessment text in narrative form

ZERO HALLUCINATION POLICY:
- Every numeric value you mention (PSA, creatinine, hemoglobin, etc.) must appear VERBATIM in the Stage 1 note
- If you cannot find a value in the Stage 1 note, do NOT mention it
- Double-check every number against the source data

The assessment should read as a coherent clinical impression suitable for a urology clinic note.
"""

    # Call LLM with zero temperature for deterministic clinical assessment
    synthesized_assessment = synthesize_with_llm(
        prompt=instructions,
        model=model,
        temperature=0.0
    )

    # Filter out VA administrative metadata that LLM might include
    va_metadata_patterns = [
        r'Signed:.*',
        r'Facility:.*',
        r'URGENCY:.*',
        r'DATE OF NOTE:.*',
        r'AUTHOR:.*'
    ]

    for pattern_str in va_metadata_patterns:
        synthesized_assessment = re.sub(pattern_str, '', synthesized_assessment, flags=re.IGNORECASE | re.MULTILINE)

    # Clean any LLM meta-commentary
    synthesized_assessment = clean_llm_commentary(synthesized_assessment)

    return synthesized_assessment.strip()
