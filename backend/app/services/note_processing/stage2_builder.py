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
from .agents.prior_ap_agent import (
    synthesize_prior_ap_context,
    format_prior_ap_for_assessment,
    format_prior_ap_for_plan
)
from .extractors import extract_assessment, extract_plan
from .session_manager import get_session_manager, SessionIsolatedFactVerifier
from .time_template import format_patient_header, get_time_template
from .visit_progression_analyzer import analyze_visit_progression_stage2
from .extractors.specialty_urologic_scanner import (
    scan_non_gu_notes_for_urologic_content,
    format_cross_specialty_context
)

logger = logging.getLogger(__name__)


def extract_prior_assessments_and_plans(
    gu_notes: List[Dict[str, str]],
    stage1_note: Optional[str] = None
) -> tuple[List[str], List[str]]:
    """
    Extract Assessment and Plan sections from historical GU notes.

    ROOT CAUSE #2 FIX: Now filters prior plans by documented conditions to prevent
    cross-condition contamination (e.g., kidney stone plans appearing when patient
    has no kidney stones documented).

    Args:
        gu_notes: List of GU note dictionaries from identify_notes()
                  Each dict has: {"title": "...", "date": "...", "content": "..."}
        stage1_note: Stage 1 preliminary note for condition filtering (optional)

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

    # ROOT CAUSE #2 FIX: Filter prior plans by documented conditions
    # This prevents cross-condition contamination where plans for conditions
    # the patient doesn't have bleed into the generated note
    if stage1_note and prior_plans:
        try:
            from .rag_query_builder import (
                get_conditions_for_filtering,
                filter_prior_plans_by_conditions
            )

            documented_conditions = get_conditions_for_filtering(stage1_note)
            logger.info(f"Documented conditions for filtering: {documented_conditions}")

            filtered_plans = filter_prior_plans_by_conditions(prior_plans, documented_conditions)
            logger.info(f"Filtered {len(prior_plans)} prior plans to {len(filtered_plans)} relevant plans")

            prior_plans = filtered_plans
        except Exception as e:
            logger.warning(f"Failed to filter prior plans: {e}. Using unfiltered plans.")

    return prior_assessments, prior_plans


def build_stage2_note(
    stage1_note: str,
    gu_notes: List[Dict[str, str]],
    non_gu_notes: Optional[List[Dict[str, str]]] = None,
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
        non_gu_notes: List of non-GU note dictionaries for cross-specialty scanning (optional)
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
    # ROOT CAUSE #2 FIX: Pass stage1_note for condition-based filtering
    print("\n[1/6] Extracting and filtering prior assessments and plans from historical GU notes...")
    prior_assessments, prior_plans = extract_prior_assessments_and_plans(gu_notes, stage1_note)
    print(f"      Found {len(prior_assessments)} prior assessments")
    print(f"      Found {len(prior_plans)} prior plans (filtered by documented conditions)")

    # Step 1a: Synthesize Prior A&P Context for Assessment and Plan agents
    print("\n[1a/6] Synthesizing prior A&P context for temporal continuity...")
    prior_ap_context = {}
    prior_ap_context_for_assessment = ""
    prior_ap_context_for_plan = ""
    if prior_assessments or prior_plans:
        prior_ap_context = synthesize_prior_ap_context(
            prior_assessments=prior_assessments,
            prior_plans=prior_plans,
            stage1_note=stage1_note,
            model=model
        )
        prior_ap_context_for_assessment = format_prior_ap_for_assessment(prior_ap_context)
        prior_ap_context_for_plan = format_prior_ap_for_plan(prior_ap_context)
        print(f"      Prior A&P context synthesized:")
        print(f"        - Key diagnoses: {prior_ap_context.get('key_diagnoses', [])}")
        print(f"        - Prior interventions: {len(prior_ap_context.get('prior_interventions', []))} found")
        print(f"        - Patient decisions: {prior_ap_context.get('patient_decisions', {})}")
        print(f"        - Resolved issues: {len(prior_ap_context.get('resolved_issues', []))}")
        print(f"        - Outstanding issues: {len(prior_ap_context.get('outstanding_issues', []))}")
    else:
        print("      No prior A&P available - likely new patient or first GU visit")

    # Step 1b: Analyze visit progression (what changed since last visit)
    print("\n[1b/6] Analyzing visit progression...")
    visit_progression = ""
    if prior_plans:
        # Combine all notes for procedure/decision detection
        all_notes_for_detection = list(gu_notes) if gu_notes else []
        if non_gu_notes:
            all_notes_for_detection.extend(non_gu_notes)

        visit_progression = analyze_visit_progression_stage2(
            prior_plans=prior_plans,
            stage1_note=stage1_note,
            model=model,
            all_notes=all_notes_for_detection
        )
        if visit_progression:
            print(f"      Visit progression analysis: {len(visit_progression)} chars")
        else:
            print("      Could not determine visit progression")
    else:
        print("      No prior plans - skipping progression analysis (new patient?)")

    # Step 1c: Scan non-GU notes for cross-specialty urologic content
    print("\n[1c/6] Scanning non-GU notes for urologic content...")
    cross_specialty_context = ""
    if non_gu_notes:
        cross_specialty_results = scan_non_gu_notes_for_urologic_content(non_gu_notes)
        cross_specialty_context = format_cross_specialty_context(cross_specialty_results)
        if cross_specialty_results:
            specialties = set(r.get("specialty", "Unknown") for r in cross_specialty_results)
            print(f"      Found urologic content in {len(cross_specialty_results)} non-GU notes")
            print(f"      Specialties: {', '.join(specialties)}")
        else:
            print("      No urologic content found in non-GU notes")
    else:
        print("      No non-GU notes provided")

    # Step 2: Synthesize Assessment
    print("\n[2/6] Synthesizing Assessment (clinical impression)...")
    assessment = synthesize_assessment(
        stage1_note=stage1_note,
        prior_assessments=prior_assessments,
        ambient_transcript=ambient_transcript,
        calculator_results=calculator_results,
        rag_content=rag_content,
        model=model,
        visit_progression=visit_progression,
        cross_specialty_context=cross_specialty_context,
        prior_ap_context=prior_ap_context_for_assessment
    )
    print(f"      Assessment: {len(assessment) if assessment else 0} chars")

    # Step 3: Verify Assessment
    # CRITICAL: Use session-isolated verifier to prevent cross-patient data contamination
    print("\n[3/6] Verifying Assessment against source data...")
    session_mgr = get_session_manager()
    current_session = session_mgr.get_current_session()

    if current_session:
        # Use session-isolated fact verifier (stores embeddings in session)
        verifier = SessionIsolatedFactVerifier(current_session)
    else:
        # Fallback to basic verification if no session (should not happen in production)
        from .fact_verifier import FactVerifier
        verifier = FactVerifier()
        logger.warning("No active session - using non-isolated FactVerifier")

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
    print("\n[4/6] Synthesizing Plan (treatment plan)...")
    plan = synthesize_plan(
        stage1_note=stage1_note,
        prior_plans=prior_plans,
        ambient_transcript=ambient_transcript,
        calculator_results=calculator_results,
        rag_content=rag_content,
        model=model,
        visit_progression=visit_progression,
        cross_specialty_context=cross_specialty_context,
        prior_ap_context=prior_ap_context_for_plan
    )
    print(f"      Plan: {len(plan) if plan else 0} chars")

    # Step 5: Verify Plan
    print("\n[5/6] Verifying Plan against source data...")
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
    print("\n[6/6] Assembling complete clinical note (with temporal awareness and cross-specialty integration)...")
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
