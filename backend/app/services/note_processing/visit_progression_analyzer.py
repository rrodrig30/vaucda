"""
Visit Progression Analyzer

Analyzes what was recommended at the most recent prior urology visit and
determines what has happened since, based on current clinical evidence.

This enables temporal awareness in HPI, Assessment, and Plan generation:
- Frame followup visits as evaluating RESPONSE to prior recommendations
- Identify completed, pending, and unchanged recommendations
- Prevent re-recommending already-completed procedures

Author: VAUCDA Development Team
Date: February 2026
"""

import re
from typing import Dict, List, Optional, Tuple
from .llm_helper import synthesize_with_llm
from .extractors import extract_plan, extract_assessment


# Keywords that indicate completed procedures in pathology/imaging
PROCEDURE_COMPLETION_EVIDENCE = {
    'prostate_biopsy': {
        'pathology_patterns': [
            r'prostate\s+biopsy',
            r'prostatic\s+(?:adeno)?carcinoma',
            r'Gleason\s+(?:score|grade)',
            r'Grade\s+Group\s+\d',
            r'core[s]?\s+positive',
            r'negative\s+for\s+malignancy',
        ],
        'imaging_patterns': [],
        'note_patterns': [r'biopsy\s+(?:was\s+)?(?:done|performed|completed)'],
    },
    'psma_pet': {
        'pathology_patterns': [],
        'imaging_patterns': [
            r'PSMA\s+PET',
            r'Piflufolastat',
            r'EANM\s+score',
            r'tracer\s+avid',
        ],
        'note_patterns': [r'PSMA\s+(?:was\s+)?(?:done|performed|completed)'],
    },
    'mri_prostate': {
        'pathology_patterns': [],
        'imaging_patterns': [
            r'MR(?:I)?\s+Prostate',
            r'PI-?RADS\s+\d',
            r'multiparametric\s+MRI',
        ],
        'note_patterns': [],
    },
    'cystoscopy': {
        'pathology_patterns': [
            r'bladder\s+biopsy',
            r'urothelial\s+carcinoma',
            r'TURBT',
        ],
        'imaging_patterns': [],
        'note_patterns': [r'cystoscopy\s+(?:was\s+)?(?:done|performed|completed)'],
    },
    'radiation_oncology_consult': {
        'pathology_patterns': [],
        'imaging_patterns': [],
        'note_patterns': [
            r'(?:saw|seen\s+by)\s+radiation\s+oncology',
            r'radiation\s+oncology\s+(?:consult|consultation)',
            r'(?:recommended|offered)\s+(?:brachytherapy|radiation|EBRT|IMRT)',
        ],
    },
}

# Keywords that indicate patient decisions
PATIENT_DECISION_PATTERNS = {
    'declined_radiation': [
        r'patient\s+declined\s+(?:radiation|XRT|brachytherapy|EBRT|IMRT)',
        r'declined\s+(?:radiation|XRT)\s+therapy',
        r'patient\s+refuses\s+radiation',
        r'does\s+not\s+want\s+radiation',
    ],
    'declined_surgery': [
        r'patient\s+declined\s+(?:surgery|prostatectomy|TURP|TURBT)',
        r'not\s+a\s+surgical\s+candidate',
        r'non-?surgical\s+candidate',
    ],
    'declined_adt': [
        r'patient\s+declined\s+(?:ADT|hormone\s+therapy|androgen\s+deprivation)',
    ],
    'prefers_active_surveillance': [
        r'patient\s+(?:prefers|elects|chooses)\s+active\s+surveillance',
        r'elected\s+for\s+active\s+surveillance',
    ],
}


def _detect_completed_procedures(
    pathology: str,
    imaging: str,
    all_notes: List[Dict[str, str]]
) -> Dict[str, Dict[str, str]]:
    """
    Detect procedures that have been completed based on clinical evidence.

    Scans pathology, imaging, and notes for evidence that specific
    procedures have been performed.

    Args:
        pathology: Pathology results text
        imaging: Imaging findings text
        all_notes: All notes (GU and non-GU)

    Returns:
        Dict of {procedure_type: {"status": "COMPLETED", "evidence": "..."}}
    """
    completed = {}

    # Combine all note content for searching
    all_note_text = "\n".join(n.get("content", "") for n in all_notes)

    for procedure, patterns in PROCEDURE_COMPLETION_EVIDENCE.items():
        evidence_found = []

        # Check pathology - collect ALL matching patterns for best evidence
        if pathology and patterns.get('pathology_patterns'):
            best_evidence = None
            for pattern in patterns['pathology_patterns']:
                if re.search(pattern, pathology, re.IGNORECASE):
                    # Extract the matching context (use DOTALL to capture across lines)
                    match = re.search(rf'.{{0,50}}{pattern}.{{0,100}}', pathology, re.IGNORECASE | re.DOTALL)
                    if match:
                        evidence_text = match.group(0).strip().replace('\n', ' ')
                        # Keep the most specific evidence (with actual clinical details)
                        if best_evidence is None or len(evidence_text) > len(best_evidence):
                            best_evidence = evidence_text
            if best_evidence:
                evidence_found.append(f"Pathology: {best_evidence}")

        # Check imaging - collect ALL matching patterns for best evidence
        if imaging and patterns.get('imaging_patterns'):
            best_evidence = None
            for pattern in patterns['imaging_patterns']:
                if re.search(pattern, imaging, re.IGNORECASE):
                    # Extract the matching context (use DOTALL to capture across lines)
                    match = re.search(rf'.{{0,30}}{pattern}.{{0,100}}', imaging, re.IGNORECASE | re.DOTALL)
                    if match:
                        evidence_text = match.group(0).strip().replace('\n', ' ')[:120]
                        # Keep the most specific evidence
                        if best_evidence is None or len(evidence_text) > len(best_evidence):
                            best_evidence = evidence_text
            if best_evidence:
                evidence_found.append(f"Imaging: {best_evidence}")

        # Check notes for explicit completion statements
        if patterns.get('note_patterns'):
            for pattern in patterns['note_patterns']:
                if re.search(pattern, all_note_text, re.IGNORECASE):
                    match = re.search(rf'.{{0,30}}{pattern}.{{0,30}}', all_note_text, re.IGNORECASE)
                    if match:
                        evidence_found.append(f"Note: {match.group(0).strip()}")
                    break

        if evidence_found:
            completed[procedure] = {
                "status": "COMPLETED",
                "evidence": "; ".join(evidence_found[:2])  # Limit to first 2 pieces of evidence
            }

    return completed


def _detect_patient_decisions(all_notes: List[Dict[str, str]]) -> Dict[str, str]:
    """
    Detect patient decisions from notes (e.g., declined radiation).

    Args:
        all_notes: All notes (GU and non-GU)

    Returns:
        Dict of {decision_type: "evidence text"}
    """
    decisions = {}

    # Combine all note content
    all_note_text = "\n".join(n.get("content", "") for n in all_notes)

    for decision_type, patterns in PATIENT_DECISION_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, all_note_text, re.IGNORECASE)
            if match:
                # Get surrounding context
                context_match = re.search(
                    rf'.{{0,40}}{pattern}.{{0,40}}',
                    all_note_text, re.IGNORECASE
                )
                decisions[decision_type] = context_match.group(0).strip() if context_match else match.group(0)
                break

    return decisions


def _build_completion_summary(
    completed_procedures: Dict[str, Dict[str, str]],
    patient_decisions: Dict[str, str]
) -> str:
    """
    Build a structured summary of completed procedures and patient decisions.

    This summary is prepended to the visit progression analysis to ensure
    the LLM knows exactly what has been done and what decisions have been made.

    Args:
        completed_procedures: Dict from _detect_completed_procedures
        patient_decisions: Dict from _detect_patient_decisions

    Returns:
        Formatted summary string
    """
    lines = []

    if completed_procedures:
        lines.append("COMPLETED PROCEDURES (DO NOT RE-RECOMMEND):")
        for procedure, info in completed_procedures.items():
            procedure_name = procedure.replace('_', ' ').title()
            lines.append(f"  - {procedure_name}: {info['evidence']}")

    if patient_decisions:
        lines.append("\nPATIENT DECISIONS (RESPECT THESE):")
        for decision_type, evidence in patient_decisions.items():
            decision_name = decision_type.replace('_', ' ').title()
            lines.append(f"  - {decision_name}: {evidence}")

    if not lines:
        return ""

    return "\n".join(lines)


def _extract_most_recent_plan(gu_notes: List[Dict[str, str]]) -> Optional[str]:
    """
    Extract the most recent Plan section from GU notes.

    GU notes are typically in reverse chronological order (most recent first).

    Args:
        gu_notes: List of GU note dictionaries from identify_notes()

    Returns:
        Most recent plan text, or None if no plans found
    """
    for note in gu_notes:
        content = note.get("content", "")
        if not content:
            continue

        # Extract plan from this note
        plan = extract_plan(content)
        if plan and plan.strip():
            return plan.strip()

    return None


def _extract_plan_recommendations(plan_text: str) -> List[Dict[str, str]]:
    """
    Parse plan text to extract individual recommendations.

    Handles Problem #N format:
    Problem #1: Elevated PSA
    - Continue active surveillance
    - Repeat PSA in 3 months

    Args:
        plan_text: Full plan section text

    Returns:
        List of {"problem": "...", "recommendations": ["...", "..."]}
    """
    recommendations = []

    # Split by Problem #N pattern
    problem_pattern = r'(?:^|\n)\s*Problem\s*#?\s*(\d+)[:\s]+([^\n]+)'
    problems = list(re.finditer(problem_pattern, plan_text, re.IGNORECASE | re.MULTILINE))

    if not problems:
        # No Problem #N structure - return whole plan as single item
        return [{"problem": "Prior Plan", "recommendations": [plan_text.strip()]}]

    for i, match in enumerate(problems):
        problem_num = match.group(1)
        problem_name = match.group(2).strip()

        # Get content between this problem and next (or end)
        start = match.end()
        end = problems[i + 1].start() if i + 1 < len(problems) else len(plan_text)
        content = plan_text[start:end].strip()

        # Extract bullet points
        bullets = []
        for line in content.split('\n'):
            line = line.strip()
            # Match bullet points (-, *, +, or numbered)
            if re.match(r'^[-*+]\s+', line):
                bullets.append(re.sub(r'^[-*+]\s+', '', line))
            elif re.match(r'^\d+[.)]\s+', line):
                bullets.append(re.sub(r'^\d+[.)]\s+', '', line))
            elif line and not re.match(r'^Problem\s*#', line, re.IGNORECASE):
                bullets.append(line)

        recommendations.append({
            "problem": f"Problem #{problem_num}: {problem_name}",
            "recommendations": bullets
        })

    return recommendations


def analyze_visit_progression(
    prior_gu_notes: List[Dict[str, str]],
    current_clinical_data: Dict[str, str],
    model: Optional[str] = None
) -> str:
    """
    Analyze what has changed since the last urology visit.

    This is used in Stage 1 (pre-visit) to provide temporal context for HPI synthesis.

    Args:
        prior_gu_notes: List of GU note dicts from identify_notes()["gu_notes"]
        current_clinical_data: Dict with current clinical evidence:
            {
                "psa": "PSA curve data",
                "pathology": "Pathology results",
                "imaging": "Imaging findings",
                "labs": "Lab results",
                "medications": "Current medications",
            }
        model: LLM model to use (default: uses system default)

    Returns:
        Concise narrative describing what has changed since last visit,
        or empty string if no prior plan found
    """
    # Extract most recent plan
    prior_plan = _extract_most_recent_plan(prior_gu_notes)

    if not prior_plan:
        return ""

    # CRITICAL: Detect completed procedures and patient decisions BEFORE LLM synthesis
    # This uses deterministic pattern matching, not LLM inference
    pathology = current_clinical_data.get("pathology", "")
    imaging = current_clinical_data.get("imaging", "")

    completed_procedures = _detect_completed_procedures(
        pathology=pathology,
        imaging=imaging,
        all_notes=prior_gu_notes
    )

    patient_decisions = _detect_patient_decisions(prior_gu_notes)

    # Build completion summary to prepend to LLM context
    completion_summary = _build_completion_summary(completed_procedures, patient_decisions)

    # Build current evidence summary
    evidence_parts = []
    if current_clinical_data.get("psa"):
        evidence_parts.append(f"CURRENT PSA DATA:\n{current_clinical_data['psa']}")
    if current_clinical_data.get("pathology"):
        evidence_parts.append(f"PATHOLOGY RESULTS:\n{current_clinical_data['pathology']}")
    if current_clinical_data.get("imaging"):
        # Limit imaging to recent findings
        imaging_text = current_clinical_data['imaging']
        if len(imaging_text) > 2000:
            imaging_text = imaging_text[:2000] + "..."
        evidence_parts.append(f"IMAGING FINDINGS:\n{imaging_text}")
    if current_clinical_data.get("labs"):
        # Limit labs
        labs = current_clinical_data['labs']
        if len(labs) > 1500:
            labs = labs[:1500] + "..."
        evidence_parts.append(f"LAB RESULTS:\n{labs}")
    if current_clinical_data.get("medications"):
        evidence_parts.append(f"CURRENT MEDICATIONS:\n{current_clinical_data['medications']}")

    current_evidence = "\n\n".join(evidence_parts) if evidence_parts else "No current clinical data available."

    # Build LLM prompt with completion summary
    completion_context = ""
    if completion_summary:
        completion_context = f"""
=== DETERMINISTIC COMPLETION DETECTION (VERIFIED) ===
{completion_summary}
===================================================

The above procedures/decisions have been VERIFIED through pattern matching in the clinical data.
These are FACTS, not interpretations. Your narrative MUST acknowledge these completed items.

"""

    prompt = f"""You are analyzing what has happened since a patient's last urology visit.

{completion_context}PRIOR UROLOGY PLAN (from last visit):
{prior_plan}

CURRENT CLINICAL EVIDENCE:
{current_evidence}

TASK:
Write a CONCISE clinical narrative (3-5 sentences) summarizing what has changed since the last visit.

CRITICAL REQUIREMENTS:
1. If COMPLETED PROCEDURES are listed above, your narrative MUST state they are complete
2. If PATIENT DECISIONS are listed above (e.g., "declined radiation"), your narrative MUST mention this
3. Do NOT recommend procedures that are already COMPLETED
4. Do NOT ignore patient decisions (e.g., if patient declined radiation, acknowledge this)

OUTPUT FORMAT:
Write a brief clinical narrative (3-5 sentences) suitable for inclusion in an HPI.
- Start with "At the prior visit, the plan included..."
- Describe what has happened since (completed items with results)
- Mention any patient decisions (declined treatments, preferences)
- Note any pending recommendations
- Use clinical language appropriate for a medical note

Example with completed procedure and patient decision:
"At the prior visit (Nov 2025), the plan included prostate biopsy and radiation oncology consultation. The patient has since undergone MRI-guided prostate biopsy (Oct 2025) which revealed Gleason 4+3=7 adenocarcinoma with perineural invasion. Staging PSMA PET (Dec 2025) showed disease confined to the prostate with no metastases. The patient was evaluated by radiation oncology but declined brachytherapy. Today's visit is to discuss alternative treatment options."

Provide ONLY the narrative. No headers, no bullet points, no meta-commentary."""

    # Call LLM with temperature 0.0 for deterministic output
    result = synthesize_with_llm(
        prompt=prompt,
        model=model,
        temperature=0.0
    )

    # Clean up result
    result = result.strip()

    # Remove any meta-commentary the LLM might add
    if result.lower().startswith("here is") or result.lower().startswith("based on"):
        # Find first sentence that starts with "At" or a clinical statement
        sentences = result.split('. ')
        for i, sentence in enumerate(sentences):
            if sentence.strip().startswith("At ") or "prior visit" in sentence.lower():
                result = '. '.join(sentences[i:])
                break

    return result


def analyze_visit_progression_stage2(
    prior_plans: List[str],
    stage1_note: str,
    model: Optional[str] = None,
    all_notes: List[Dict[str, str]] = None
) -> str:
    """
    Analyze visit progression for Stage 2 (Assessment/Plan generation).

    This provides more detailed context using the complete Stage 1 note.

    Args:
        prior_plans: List of prior plan texts (already extracted)
        stage1_note: Complete Stage 1 preliminary note
        model: LLM model to use
        all_notes: All notes for procedure/decision detection (optional)

    Returns:
        Detailed narrative of visit progression for Assessment/Plan agents
    """
    if not prior_plans:
        return ""

    # Use most recent prior plan
    prior_plan = prior_plans[0] if prior_plans else ""

    if not prior_plan:
        return ""

    # Extract pathology and imaging from stage1_note for completion detection
    pathology = ""
    imaging = ""

    pathology_match = re.search(
        r'PATHOLOGY\s+RESULTS?:?(.*?)(?=\n\s*(?:MEDICATIONS|ALLERGIES|===|LABS|IMAGING|GENERAL\s+ROS|$))',
        stage1_note, re.DOTALL | re.IGNORECASE
    )
    if pathology_match:
        pathology = pathology_match.group(1).strip()

    imaging_match = re.search(
        r'(?:===+\s*IMAGING\s*===+|IMAGING:?)(.*?)(?=\n\s*(?:===|GENERAL\s+ROS|PHYSICAL|$))',
        stage1_note, re.DOTALL | re.IGNORECASE
    )
    if imaging_match:
        imaging = imaging_match.group(1).strip()

    # Detect completed procedures and patient decisions
    notes_for_detection = all_notes if all_notes else []
    completed_procedures = _detect_completed_procedures(
        pathology=pathology,
        imaging=imaging,
        all_notes=notes_for_detection
    )

    patient_decisions = _detect_patient_decisions(notes_for_detection)

    # Build completion summary
    completion_summary = _build_completion_summary(completed_procedures, patient_decisions)

    # Build completion context for prompt
    completion_context = ""
    if completion_summary:
        completion_context = f"""
=== VERIFIED COMPLETION STATUS (DETERMINISTIC DETECTION) ===
{completion_summary}
============================================================

CRITICAL: The above items have been VERIFIED through pattern matching.
- COMPLETED PROCEDURES must NOT be re-recommended in the Plan
- PATIENT DECISIONS must be respected (do NOT recommend what patient declined)
- The Assessment and Plan must PROGRESS from this point, not repeat the prior visit

"""

    # Build LLM prompt with completion context
    prompt = f"""You are analyzing what has happened since a patient's last urology visit to inform the Assessment and Plan for today's visit.

{completion_context}PRIOR UROLOGY PLAN (from last visit):
{prior_plan}

CURRENT PATIENT DATA (from today's preliminary note):
{stage1_note}

TASK:
Write a structured summary that explicitly tells the Assessment and Plan agents:
1. What procedures are COMPLETE (with specific results)
2. What patient decisions have been made (declined treatments, etc.)
3. What the current decision point is (what needs to be decided TODAY)

CRITICAL REQUIREMENTS:
1. If prostate biopsy is COMPLETE, state the Gleason score and findings
2. If PSMA PET is COMPLETE, state whether disease is localized or metastatic
3. If patient DECLINED a treatment, explicitly state this
4. Identify what decision needs to be made TODAY (not what was decided before)

OUTPUT FORMAT:
Write a clinical summary (5-8 sentences) structured as follows:
"The prior visit plan addressed [problems]. Since then: [COMPLETED procedures with specific results]. [Patient DECLINED specific treatments if applicable]. The patient has now completed staging workup showing [staging summary]. Today's visit is to [specific decision point - e.g., 'discuss treatment options given he has declined radiation and is not a surgical candidate']."

ANTI-HALLUCINATION RULES:
- ONLY state findings that are documented in the current data
- If biopsy shows cancer, state the actual Gleason score from the data
- If imaging shows findings, state the actual findings from the data
- Do NOT invent or assume anything not in the evidence

Provide ONLY the clinical summary. No headers, no meta-commentary."""

    # Call LLM with temperature 0.0
    result = synthesize_with_llm(
        prompt=prompt,
        model=model,
        temperature=0.0
    )

    return result.strip()


def get_prior_plan_summary(gu_notes: List[Dict[str, str]]) -> str:
    """
    Get a brief summary of the most recent prior plan for quick reference.

    Used when full progression analysis is not needed.

    Args:
        gu_notes: List of GU note dicts

    Returns:
        Brief summary of prior plan, or empty string
    """
    prior_plan = _extract_most_recent_plan(gu_notes)

    if not prior_plan:
        return ""

    # Extract just the problem names
    recommendations = _extract_plan_recommendations(prior_plan)

    if not recommendations:
        return ""

    problems = [rec["problem"] for rec in recommendations]
    return "Prior visit addressed: " + "; ".join(problems)
