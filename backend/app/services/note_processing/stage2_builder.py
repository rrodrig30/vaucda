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
- Active RAG/GraphRAG retrieval based on clinical context
- Task-specific LLM configuration
"""

from typing import List, Dict, Optional, Any, TYPE_CHECKING
import logging
import re
from .agents.assessment_agent import synthesize_assessment
from .agents.plan_agent import synthesize_plan

if TYPE_CHECKING:
    from app.services.llm_config_manager import LLMTaskConfig
from .agents.prior_ap_agent import (
    synthesize_prior_ap_context,
    format_prior_ap_for_assessment,
    format_prior_ap_for_plan
)
from .extractors import extract_assessment, extract_plan
from .patient_status_facts import (
    extract_patient_status_facts,
    format_facts_for_prompt,
    sanitize_context_against_facts,
)
from .session_manager import get_session_manager, SessionIsolatedFactVerifier
from .time_template import format_patient_header, get_time_template
from .visit_progression_analyzer import analyze_visit_progression_stage2
from .extractors.specialty_urologic_scanner import (
    scan_non_gu_notes_for_urologic_content,
    format_cross_specialty_context
)

logger = logging.getLogger(__name__)


# =============================================================================
# NOTE: RAG RETRIEVAL ARCHITECTURE
# =============================================================================
# RAG retrieval currently happens in the API layer (notes.py), NOT in this module.
# The API layer uses rag_query_builder.py for query generation, then passes
# the retrieved rag_content to build_stage2_note() as a parameter.
#
# The functions below (build_targeted_rag_queries, retrieve_active_rag_context)
# are ASYNC utilities that can be used for future active RAG implementations
# if needed. They are not currently invoked in the production flow.
# =============================================================================


async def build_targeted_rag_queries(
    stage1_note: str,
    chief_complaint: Optional[str] = None,
    max_queries: int = 3
) -> List[str]:
    """
    Build targeted RAG queries from Stage 1 note clinical content.

    NOTE: This async function is currently NOT used in production.
    RAG queries are built in notes.py using rag_query_builder.py (sync version).
    This function is available for future active RAG implementations.

    Analyzes the Stage 1 note to extract key clinical concepts for RAG retrieval.

    Args:
        stage1_note: Complete Stage 1 note
        chief_complaint: Extracted chief complaint (if already parsed)
        max_queries: Maximum number of queries to generate

    Returns:
        List of targeted query strings for RAG retrieval
    """
    queries = []

    # 1. Extract Chief Complaint for primary query
    if chief_complaint:
        cc = chief_complaint
    else:
        cc_match = re.search(r'CC:\s*(.+?)(?:\n|$)', stage1_note, re.IGNORECASE)
        cc = cc_match.group(1).strip() if cc_match else None

    if cc:
        # Create query focused on management guidelines
        cc_clean = cc.lower().replace('followup', '').replace('follow-up', '').replace('follow up', '').strip()
        if cc_clean:
            queries.append(f"{cc_clean} management guidelines AUA NCCN")

    # 2. Extract cancer diagnoses for treatment guidelines
    cancer_patterns = [
        r'(?:prostate\s+)?(?:adenocarcinoma|carcinoma)\s+(?:gleason|grade\s+group)',
        r'bladder\s+(?:cancer|carcinoma|tumor)',
        r'urothelial\s+(?:cancer|carcinoma)',
        r'renal\s+(?:cell\s+)?(?:cancer|carcinoma)',
        r'kidney\s+(?:cancer|tumor|mass)',
        r'testicular\s+(?:cancer|tumor|mass)',
    ]

    for pattern in cancer_patterns:
        match = re.search(pattern, stage1_note, re.IGNORECASE)
        if match and len(queries) < max_queries:
            cancer_type = match.group(0).strip()
            queries.append(f"{cancer_type} treatment options NCCN guidelines")
            break

    # 3. Extract BPH/LUTS for medical management
    if re.search(r'\b(?:BPH|LUTS|IPSS)\b', stage1_note, re.IGNORECASE):
        if len(queries) < max_queries:
            queries.append("BPH LUTS management AUA guidelines medical therapy")

    # 4. Extract stone disease
    if re.search(r'\b(?:kidney\s+stone|renal\s+calcul|urolithiasis|nephrolithiasis)\b', stage1_note, re.IGNORECASE):
        if len(queries) < max_queries:
            queries.append("kidney stone nephrolithiasis management AUA guidelines")

    # 5. Extract PSA surveillance queries
    if re.search(r'PSA\s+(?:surveillance|monitoring|followup)', stage1_note, re.IGNORECASE):
        if len(queries) < max_queries:
            queries.append("PSA surveillance prostate cancer monitoring guidelines")

    # 6. Extract hematuria
    if re.search(r'\bhematuria\b', stage1_note, re.IGNORECASE):
        if len(queries) < max_queries:
            queries.append("hematuria workup evaluation AUA guidelines")

    # Ensure at least one query
    if not queries:
        # Generic urology query based on note content
        queries.append("urology clinical guidelines evidence-based management")

    logger.info(f"Generated {len(queries)} targeted RAG queries")
    return queries[:max_queries]


async def retrieve_active_rag_context(
    stage1_note: str,
    rag_pipeline,
    task_config: Optional["LLMTaskConfig"] = None,
    max_queries: int = 3
) -> tuple[str, List[Dict[str, str]]]:
    """
    Actively retrieve RAG context based on clinical content in Stage 1 note.

    NOTE: This async function is currently NOT used in production.
    RAG retrieval happens in notes.py and the resulting rag_content is passed
    to build_stage2_note(). This function is available for future active RAG
    implementations that require retrieval within the stage2_builder module.

    This performs ACTIVE retrieval by:
    1. Analyzing the Stage 1 note to identify key clinical concepts
    2. Building targeted queries for each concept
    3. Retrieving relevant guidelines via RAG/GraphRAG
    4. Assembling context for Assessment & Plan synthesis

    Args:
        stage1_note: Complete Stage 1 note
        rag_pipeline: Initialized RAG pipeline instance
        task_config: LLMTaskConfig with RAG settings (use_rag, use_graphrag, rag_top_k)
        max_queries: Maximum number of queries to generate

    Returns:
        Tuple of (assembled context string, list of sources)
    """
    # Get RAG settings from task_config or use defaults
    use_rag = True
    use_graphrag = True
    rag_top_k = 5

    if task_config:
        use_rag = getattr(task_config, 'use_rag', True)
        use_graphrag = getattr(task_config, 'use_graphrag', True)
        rag_top_k = getattr(task_config, 'rag_top_k', 5)

    if not use_rag and not use_graphrag:
        logger.info("RAG/GraphRAG disabled in task config, skipping retrieval")
        return "", []

    # Generate targeted queries
    queries = await build_targeted_rag_queries(
        stage1_note=stage1_note,
        max_queries=max_queries
    )

    all_context_parts = []
    all_sources = []
    seen_doc_ids = set()
    max_context_length = 4000

    for query in queries:
        try:
            # Determine search strategy
            if use_graphrag:
                search_strategy = "graphrag"
            else:
                search_strategy = "hybrid"

            # Execute retrieval
            rag_result = await rag_pipeline.retrieve_and_augment(
                query=query,
                k=rag_top_k,
                search_strategy=search_strategy
            )

            if rag_result.has_context:
                # Add context, avoiding duplicates
                for doc in rag_result.documents:
                    if doc.doc_id not in seen_doc_ids:
                        seen_doc_ids.add(doc.doc_id)
                        all_context_parts.append(
                            f"[{doc.source}] {doc.title}\n{doc.content[:500]}"
                        )

                # Add sources
                for source in rag_result.sources:
                    if source not in all_sources:
                        all_sources.append(source)

        except Exception as e:
            logger.warning(f"RAG retrieval failed for query '{query}': {e}")
            continue

    # Assemble context with length limit
    context = "\n\n---\n\n".join(all_context_parts)
    if len(context) > max_context_length:
        context = context[:max_context_length] + "\n[Context truncated for length]"

    logger.info(f"Active RAG retrieval: {len(context)} chars from {len(all_sources)} sources")

    return context, all_sources


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
    ssn_last4: Optional[str] = None,
    task_config: Optional["LLMTaskConfig"] = None,
    patient_facts: Optional["PatientStatusFacts"] = None,
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
        rag_content: Evidence-based guidelines from Neo4j RAG (optional, for backwards compatibility)
        model: LLM model to use for synthesis (ignored if task_config provided)
        note_type: Type of note ('clinic_note', 'consult', etc.)
        patient_name: Patient full name for header
        ssn_last4: Last 4 digits of SSN for header
        task_config: LLMTaskConfig for Stage 2 LLM settings (provider, model, temperature, RAG settings)

    Returns:
        Complete clinical note with Assessment and Plan sections added
    """
    # Use task_config model if provided, otherwise use model parameter
    effective_model = task_config.model if task_config else model

    # Cystoscopy notes are built complete in Stage 1 (see build_cystoscopy_note):
    # the procedure narrative + anticipated Findings/Assessment/Plan/Disposition
    # are already generated per-patient. Stage 2 has nothing to add — pass the
    # note through unchanged.
    if (note_type or "").lower().replace(" ", "_") in (
            "cystoscopy", "cysto", "cystoscopy_note"):
        print("\n[Stage 2] Cystoscopy note — already complete from Stage 1; passthrough.")
        return stage1_note

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
            model=effective_model
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
            model=effective_model,
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

    # Step 1d: Pre-LLM defense layer.
    # Build a deterministic ground-truth verdict from the Stage 1 note,
    # then sanitize every downstream context artifact (prior assessments
    # / plans / visit progression / prior A&P context / cross-specialty
    # context) by stripping sentences that contradict the verdict. This
    # breaks the prior-LLM-hallucination feedback loop: a prior visit's
    # "completed focal therapy" confabulation cannot resurface in this
    # visit's Assessment because it gets stripped before transmission.
    print("\n[1d/6] Extracting authoritative patient status facts...")
    # Stitch raw clinician-written text from all source notes (GU + non-GU).
    # Each note's HPI / Assessment / Plan fields hold the clinician's
    # original prose where treatment status often lives ("Problem #1:
    # prostate adenocarcinoma, status post radiation therapy and ADT").
    # Passing this raw text to the fact extractor catches treatments that
    # PMH alone (often just "Prostate cancer" as a bare entry) does not
    # capture. The raw scanner is gated by strict prostate-cancer
    # co-occurrence rules, so unrelated cross-specialty mentions cannot
    # produce false-positive treatment detections.
    # identify_notes() returns each note with keys 'title', 'date',
    # 'content' — 'content' is the full raw note text from the clinician.
    # Also fall back to the per-section keys (HPI, Assessment, Plan, PMH)
    # in case downstream code populates those forms.
    _raw_for_facts_parts: List[str] = []
    for n in (gu_notes or []) + list(non_gu_notes or []):
        if not isinstance(n, dict):
            continue
        for key in ("content", "HPI", "Assessment", "Plan", "PMH"):
            v = n.get(key)
            if v:
                _raw_for_facts_parts.append(v)
    _raw_for_facts = "\n\n".join(_raw_for_facts_parts)
    # Phase 1: consume the SHARED authoritative facts from Stage 1 when
    # provided. Re-deriving here from the rendered stage1_note (LLM output)
    # let the Assessment ground on Stage-1 hallucinations and invent a
    # divergent timeline/status — the dominant Stage-2 hallucination +
    # contradiction source. Fall back to local derivation only when called
    # standalone (no shared facts passed).
    if patient_facts is not None:
        print("      Using SHARED authoritative facts from Stage 1")
    else:
        patient_facts = extract_patient_status_facts(
            stage1_note,
            raw_clinical_text=_raw_for_facts or None,
        )
    authoritative_facts = format_facts_for_prompt(patient_facts)

    # PHASE 2.1: rebuild the HPI skeleton at Stage 2 so the Assessment
    # agent sees the same structured story the HPI was rendered from.
    # Without this the Assessment can drift away from the HPI by relying
    # on raw context alone. The skeleton is the contract.
    _stage2_skeleton_text: Optional[str] = None
    try:
        from .hpi_skeleton import build_hpi_skeleton, format_skeleton_for_prompt
        # Extract demographics from the Stage 1 note's patient header
        _name_m = re.search(r"^Patient:\s*([^\n|(]+)", stage1_note, re.MULTILINE)
        _age_m = re.search(r"Age:\s*(\d+)", stage1_note)
        _sex_m = re.search(r"Sex:\s*(\w+)", stage1_note)
        _skel = build_hpi_skeleton(
            facts=patient_facts,
            raw_clinical_text=_raw_for_facts,
            patient_name=(_name_m.group(1).strip().title() if _name_m else (patient_name or "")),
            age=(_age_m.group(1) if _age_m else ""),
            sex=(_sex_m.group(1) if _sex_m else ""),
            pathology_data="",  # not directly available here; cancer_evidence covers it
            gu_notes=gu_notes,
        )
        _stage2_skeleton_text = format_skeleton_for_prompt(_skel)
        print(
            f"      Stage 2 skeleton: phase={_skel.phase}, "
            f"timeline events={len(_skel.prior_treatment_events)}, "
            f"regimen items={len(_skel.current_regimen)}"
        )
    except Exception as _e:
        logger.warning(f"Stage 2 HPI skeleton build failed (non-fatal): {_e}")
    print(f"      Cancer status:    {patient_facts.cancer_status}")
    print(f"      Treatment naive:  {patient_facts.treatment_naive}")
    print(f"      Phoenix applic.:  {patient_facts.phoenix_applicable}")
    print(f"      Biopsy count:     {patient_facts.biopsy_count} "
          f"(all-negative={patient_facts.biopsy_all_negative})")
    print(f"      ASAP present:     {patient_facts.asap_present}")
    if patient_facts.confirmed_urologic_treatments:
        print(f"      Confirmed Tx:     "
              f"{patient_facts.confirmed_urologic_treatments[:3]}")
    if patient_facts.cancer_evidence:
        print(f"      Cancer evidence: {patient_facts.cancer_evidence[:3]}")
    if patient_facts.inconsistencies:
        for inc in patient_facts.inconsistencies:
            print(f"      ⚠ INCONSISTENCY: {inc}")

    def _sanitize_one(label: str, text: str) -> str:
        if not text or not text.strip():
            return text
        cleaned, stripped = sanitize_context_against_facts(text, patient_facts)
        for s in stripped:
            print(f"      ✂ stripped from {label}: {s[:140]}")
        return cleaned

    prior_assessments = [
        _sanitize_one(f"prior_assessment_{i}", a)
        for i, a in enumerate(prior_assessments or [])
    ]
    prior_plans = [
        _sanitize_one(f"prior_plan_{i}", p)
        for i, p in enumerate(prior_plans or [])
    ]
    visit_progression = _sanitize_one("visit_progression", visit_progression)
    prior_ap_context_for_assessment = _sanitize_one(
        "prior_ap_context_for_assessment", prior_ap_context_for_assessment
    )
    prior_ap_context_for_plan = _sanitize_one(
        "prior_ap_context_for_plan", prior_ap_context_for_plan
    )
    cross_specialty_context = _sanitize_one(
        "cross_specialty_context", cross_specialty_context
    )

    # Step 2: Synthesize Assessment
    print("\n[2/6] Synthesizing Assessment (clinical impression)...")
    assessment = synthesize_assessment(
        stage1_note=stage1_note,
        prior_assessments=prior_assessments,
        ambient_transcript=ambient_transcript,
        calculator_results=calculator_results,
        rag_content=rag_content,
        model=effective_model,
        task_config=task_config,  # Pass full task_config for multi-provider LLM support
        visit_progression=visit_progression,
        cross_specialty_context=cross_specialty_context,
        prior_ap_context=prior_ap_context_for_assessment,
        authoritative_facts=authoritative_facts,
        hpi_skeleton=_stage2_skeleton_text,
    )
    print(f"      Assessment: {len(assessment) if assessment else 0} chars")

    # Deterministic fact guard on the GENERATED assessment. The sanitizer runs
    # on the input CONTEXT above, but the LLM can still emit a contradicting
    # sentence (a prostate-cancer diagnosis for an ABSENT / female patient, a
    # treatment assertion for a treatment-naive patient). Strip those here;
    # negated ("no evidence of prostate cancer") and workup ("mpMRI to evaluate")
    # mentions are preserved by the sanitizer's negation guard. Runs BEFORE the
    # Plan so the Plan is generated congruent with the cleaned Assessment.
    if patient_facts is not None and assessment:
        assessment, _asmt_dropped = sanitize_context_against_facts(assessment, patient_facts)
        if _asmt_dropped:
            logger.info("Assessment fact-guard dropped %d sentence(s): %s",
                        len(_asmt_dropped), _asmt_dropped)
            print(f"      Fact-guard: dropped {len(_asmt_dropped)} contradicting sentence(s) from Assessment")

    # Finalize: strip hallucinated scanner/metadata garbage + completeness-repair
    # so every documented cancer the patient has is addressed (compose -> ledger
    # -> repair). Safe no-op without facts / on error.
    if assessment:
        try:
            from .agents.assessment_composer import finalize_assessment
            from .llm_helper import synthesize_with_llm

            def _asmt_repair_call(_p: str) -> str:
                return synthesize_with_llm(prompt=_p, temperature=0.0,
                                           task_config=task_config, max_tokens=900)

            assessment = finalize_assessment(
                assessment, stage1_note, patient_facts, _asmt_repair_call)
        except Exception as _ae:  # noqa: BLE001
            logger.warning(f"Assessment finalize skipped: {_ae}")

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
        model=effective_model,
        task_config=task_config,  # Pass full task_config for multi-provider LLM support
        visit_progression=visit_progression,
        cross_specialty_context=cross_specialty_context,
        prior_ap_context=prior_ap_context_for_plan,
        authoritative_facts=authoritative_facts,
        # Pass the just-generated Assessment so the Plan can be congruent
        # with the recommendations the Assessment narrative makes. Without
        # this the two sections drift (e.g. Assessment says "MRI 6-12
        # months", Plan says "MRI + biopsy").
        assessment_text=assessment,
    )
    print(f"      Plan: {len(plan) if plan else 0} chars")

    # Same deterministic fact guard on the generated Plan.
    if patient_facts is not None and plan:
        plan, _plan_dropped = sanitize_context_against_facts(plan, patient_facts)
        if _plan_dropped:
            logger.info("Plan fact-guard dropped %d sentence(s): %s",
                        len(_plan_dropped), _plan_dropped)
            print(f"      Fact-guard: dropped {len(_plan_dropped)} contradicting sentence(s) from Plan")

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

    # ASCII-safety pass for VistA paste. See text_normalizer.py.
    from .text_normalizer import to_vista_ascii
    return to_vista_ascii(complete_note)


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

    final = '\n'.join(note_parts)

    # Post-processing: Format "Problem #N" as "\nPROBLEM #N" for visual separation
    import re
    final = re.sub(r'\n?Problem\s*#', '\n\nPROBLEM #', final, flags=re.IGNORECASE)
    # Clean up any triple+ newlines created above
    final = re.sub(r'\n{3,}', '\n\n', final)

    return final
