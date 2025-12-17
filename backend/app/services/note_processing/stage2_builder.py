"""
Stage 2 Note Builder

Completes the clinical note AFTER the patient visit by adding:
- Assessment (clinical impression)
- Plan (treatment plan)

Stage 2 leverages:
- Stage 1 preliminary note (historical data)
- Prior assessments/plans from GU notes
- Ambient listening transcript (real-time conversation)
- Calculator results (44 specialized urologic calculators)
- RAG content (evidence-based guidelines from Neo4j)
"""

from typing import List, Dict, Optional
import logging
from .agents.assessment_agent import synthesize_assessment
from .agents.plan_agent import synthesize_plan
from .extractors import extract_assessment, extract_plan
from .fact_verifier import FactVerifier
from .time_template import format_patient_header, get_time_template

logger = logging.getLogger(__name__)


def extract_prior_assessments_and_plans(gu_notes: List[Dict[str, str]]) -> tuple[List[str], List[str]]:
    """
    Extract Assessment and Plan sections from historical GU notes.

    Args:
        gu_notes: List of GU note dictionaries from identify_notes()
                  Each dict has: {"title": "...", "date": "...", "content": "..."}

    Returns:
        Tuple of (prior_assessments, prior_plans) as lists of strings
    """
    prior_assessments = []
    prior_plans = []

    for note in gu_notes:
        note_content = note.get("content", "")

        # Extract Assessment
        assessment = extract_assessment(note_content)
        if assessment and assessment.strip():
            prior_assessments.append(assessment)

        # Extract Plan
        plan = extract_plan(note_content)
        if plan and plan.strip():
            prior_plans.append(plan)

    return prior_assessments, prior_plans


def build_stage2_note(
    stage1_note: str,
    gu_notes: List[Dict[str, str]],
    ambient_transcript: Optional[str] = None,
    calculator_results: Optional[dict] = None,
    rag_content: Optional[str] = None,
    model: Optional[str] = None,
    note_type: str = "clinic_note",
    patient_name: Optional[str] = None,
    ssn_last4: Optional[str] = None
) -> str:
    """
    Complete the clinical note by adding Assessment and Plan (Stage 2).

    This function is called AFTER the patient visit to generate the final
    comprehensive clinical note.

    Args:
        stage1_note: Complete preliminary note from Stage 1 (build_urology_note)
        gu_notes: List of GU note dictionaries (same format as Stage 1)
        ambient_transcript: Real-time provider-patient conversation transcript (optional)
        calculator_results: Results from 44 specialized calculators (optional)
        rag_content: Evidence-based guidelines from Neo4j RAG (optional)
        model: LLM model to use for synthesis
        note_type: Type of note ('clinic_note', 'consult', etc.)
        patient_name: Patient full name for header
        ssn_last4: Last 4 digits of SSN for header

    Returns:
        Complete clinical note with Assessment and Plan sections added
    """
    print("\n" + "="*80)
    print("STAGE 2: COMPLETING CLINICAL NOTE (POST-VISIT)")
    print("="*80)

    # Step 1: Extract prior assessments and plans from GU notes
    print("\n[1/3] Extracting prior assessments and plans from historical GU notes...")
    prior_assessments, prior_plans = extract_prior_assessments_and_plans(gu_notes)
    print(f"      Found {len(prior_assessments)} prior assessments")
    print(f"      Found {len(prior_plans)} prior plans")

    # Step 2: Synthesize Assessment
    print("\n[2/5] Synthesizing Assessment (clinical impression)...")
    assessment = synthesize_assessment(
        stage1_note=stage1_note,
        prior_assessments=prior_assessments,
        ambient_transcript=ambient_transcript,
        calculator_results=calculator_results,
        rag_content=rag_content,
        model=model
    )
    print(f"      Assessment: {len(assessment) if assessment else 0} chars")

    # Step 3: Verify Assessment
    print("\n[3/5] Verifying Assessment against source data...")
    verifier = FactVerifier()
    verifier.index_source_document(stage1_note)

    assessment_verification = verifier.verify_generated_text(
        generated_text=assessment,
        source_text=stage1_note
    )

    if not assessment_verification['verified']:
        logger.warning(f"Assessment verification found {assessment_verification['total_errors']} errors")
        logger.warning(f"Errors: {assessment_verification['error_details']}")
        print(f"      ⚠ Warning: {assessment_verification['total_errors']} potential errors detected")
        print(f"      Confidence: {assessment_verification['confidence_score']}%")
    else:
        print(f"      ✓ Assessment verified (confidence: {assessment_verification['confidence_score']}%)")

    # Step 4: Synthesize Plan
    print("\n[4/5] Synthesizing Plan (treatment plan)...")
    plan = synthesize_plan(
        stage1_note=stage1_note,
        prior_plans=prior_plans,
        ambient_transcript=ambient_transcript,
        calculator_results=calculator_results,
        rag_content=rag_content,
        model=model
    )
    print(f"      Plan: {len(plan) if plan else 0} chars")

    # Step 5: Verify Plan
    print("\n[5/5] Verifying Plan against source data...")
    plan_verification = verifier.verify_generated_text(
        generated_text=plan,
        source_text=stage1_note
    )

    if not plan_verification['verified']:
        logger.warning(f"Plan verification found {plan_verification['total_errors']} errors")
        logger.warning(f"Errors: {plan_verification['error_details']}")
        print(f"      ⚠ Warning: {plan_verification['total_errors']} potential errors detected")
        print(f"      Confidence: {plan_verification['confidence_score']}%")
    else:
        print(f"      ✓ Plan verified (confidence: {plan_verification['confidence_score']}%)")

    # Step 6: Assemble complete note
    print("\n[6/6] Assembling complete clinical note...")
    complete_note = assemble_complete_note(
        stage1_note=stage1_note,
        assessment=assessment,
        plan=plan,
        note_type=note_type,
        patient_name=patient_name,
        ssn_last4=ssn_last4
    )

    print(f"      Complete note: {len(complete_note)} characters")
    print("\n" + "="*80)
    print("STAGE 2 COMPLETE - FINAL CLINICAL NOTE READY")
    print("="*80)

    return complete_note


def assemble_complete_note(
    stage1_note: str,
    assessment: str,
    plan: str,
    note_type: str = "clinic_note",
    patient_name: Optional[str] = None,
    ssn_last4: Optional[str] = None
) -> str:
    """
    Combine Stage 1 note with Assessment and Plan sections.

    Adds patient identifier header at the beginning and time template at the end.

    Args:
        stage1_note: Preliminary note from Stage 1
        assessment: Synthesized assessment from Stage 2
        plan: Synthesized plan from Stage 2
        note_type: Type of note ('clinic_note', 'consult', etc.)
        patient_name: Patient full name for header
        ssn_last4: Last 4 digits of SSN for header

    Returns:
        Complete clinical note with header and time template
    """
    note_parts = []

    # Add patient identifier header at the beginning
    patient_header = format_patient_header(patient_name, ssn_last4)
    if patient_header:
        note_parts.append(patient_header)

    # Add Stage 1 note
    note_parts.append(stage1_note)

    # Add Assessment
    if assessment and assessment.strip():
        note_parts.append(f"\nASSESSMENT:\n{assessment}\n")

    # Add Plan
    if plan and plan.strip():
        note_parts.append(f"\nPLAN:\n{plan}\n")

    # Add time template at the end
    time_template = get_time_template(note_type)
    if time_template:
        note_parts.append(f"\n{time_template}")

    return '\n'.join(note_parts)
