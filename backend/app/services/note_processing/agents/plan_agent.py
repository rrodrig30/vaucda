"""
Plan Agent (Stage 2 Only)

Synthesizes treatment plan using:
- Stage 1 preliminary note
- Prior plans from historical GU notes
- Ambient listening transcript
- Calculator results
- RAG content (evidence-based guidelines)
"""

import re
from typing import List, Optional
from ..llm_helper import synthesize_with_llm
from .history_cleaners import clean_llm_commentary


def synthesize_plan(
    stage1_note: str,
    prior_plans: List[str] = None,
    ambient_transcript: Optional[str] = None,
    calculator_results: Optional[dict] = None,
    rag_content: Optional[str] = None,
    model: Optional[str] = None
) -> str:
    """
    Synthesize treatment plan for Stage 2 (post-visit).

    Args:
        stage1_note: Complete preliminary note from Stage 1
        prior_plans: List of Plan sections from prior GU notes only
        ambient_transcript: Provider-patient conversation transcript (if available)
        calculator_results: Results from 44 specialized calculators (if available)
        rag_content: Evidence-based guidelines from Neo4j RAG (if available)

    Returns:
        Synthesized treatment plan text
    """
    if not prior_plans:
        prior_plans = []

    # Collect all Plan sections from prior notes
    all_plans = [p for p in prior_plans if p and p.strip()]

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

    # Add prior plans
    if all_plans:
        context_parts.append(f"=== PRIOR TREATMENT PLANS ===")
        for i, plan in enumerate(all_plans, 1):
            context_parts.append(f"\n--- Prior Plan {i} ---\n{plan}")

    # If only prior plans and no other context, return the single plan
    if len(all_plans) == 1 and not any([stage1_note, ambient_transcript, calculator_results, rag_content]):
        return all_plans[0]

    # Build comprehensive synthesis prompt
    full_context = "\n".join(context_parts)

    instructions = f"""
You are synthesizing a comprehensive TREATMENT PLAN for a urology patient.

AVAILABLE INFORMATION:
{full_context}

TASK:
Create a comprehensive, actionable treatment plan that:
1. Integrates information from ALL available sources (Stage 1 note, prior plans, ambient conversation, calculator results, evidence-based guidelines)
2. Incorporates calculator-based recommendations and evidence-based guidelines
3. Addresses all active urologic conditions and concerns
4. Includes specific interventions, medications, procedures, and follow-up
5. Uses the most recent plan for each condition
6. Removes duplicate items
7. Maintains clear, actionable steps
8. Preserves follow-up instructions and monitoring plans
9. Incorporates patient preferences/concerns from ambient transcript (if available)

CRITICAL PLAN FORMATTING RULES (MUST FOLLOW EXACTLY):
- The PLAN section must ONLY contain problem-based plans
- Each problem must be formatted as "Problem #N: [Problem name]" followed DIRECTLY by bulleted plan items
- Use simple dash bullets (-) for ALL plan items - DO NOT use asterisks (*), plus signs (+), or any other bullet style
- DO NOT add "Plan:", "* Plan:", "Assessment:", or any other header after the problem name
- DO NOT create separate numbered lists within the PLAN section
- DO NOT create separate sections for "New Prescriptions", "Adjustments", "Follow-up", etc.
- All plan items must be organized under their respective problems
- DO NOT indent plan items with tabs or spaces beyond the dash

CORRECT FORMAT (USE THIS - MUST HAVE BLANK LINE BEFORE EVERY PROBLEM):

Problem #1: [Problem name]
- [Plan item]
- [Plan item]

Problem #2: [Problem name]
- [Plan item]
- [Plan item]

Problem #3: [Problem name]
- [Plan item]
- [Plan item]

CRITICAL BLANK LINE REQUIREMENTS (MUST FOLLOW EXACTLY):
- ALWAYS start with a blank line before Problem #1
- ALWAYS add a blank line before each subsequent Problem #2, Problem #3, etc.
- The blank line is MANDATORY - it is NOT optional
- Every single "Problem #N:" line must be preceded by an empty blank line for readability

INCORRECT FORMAT (DO NOT USE):
Problem #1: [Problem name]
* Assessment: ...
* Plan:
	+ [Plan item]

CLINICAL AWARENESS REQUIREMENTS:
- REVIEW the PSA CURVE section in the Stage 1 note above BEFORE making recommendations
- If the patient has recent PSA values in the PSA CURVE section, DO NOT recommend PSA screening - they already have PSA data
- If the Stage 1 note contains PSA values, acknowledge them in your plan
- Use ONLY data values that appear in the Stage 1 note above
- DO NOT invent or hallucinate lab values, PSA values, doses, or any numeric data
- If a medication dose or lab value is mentioned, it must match EXACTLY what is shown in the Stage 1 note

CRITICAL REQUIREMENTS:
- Provide ONLY the treatment plan text
- NO meta-commentary (no "Based on the information", no "Here is", no "The plan includes")
- NO explanations about what you included/excluded
- NO preamble or introduction
- Just the clean, clinical plan text

ZERO HALLUCINATION POLICY:
- Every numeric value you mention (PSA, creatinine, doses, schedules) must appear VERBATIM in the Stage 1 note
- If you cannot find a value in the Stage 1 note, do NOT mention it
- Double-check every number against the source data

The plan should read as a coherent, actionable treatment strategy suitable for a urology clinic note.
"""

    # Call LLM directly with comprehensive prompt
    synthesized_plan = synthesize_with_llm(
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
        r'AUTHOR:.*',
        r'Time of Start:.*',
        r'Time End:.*'
    ]

    for pattern_str in va_metadata_patterns:
        synthesized_plan = re.sub(pattern_str, '', synthesized_plan, flags=re.IGNORECASE | re.MULTILINE)

    # Clean any LLM meta-commentary
    synthesized_plan = clean_llm_commentary(synthesized_plan)

    return synthesized_plan.strip()
