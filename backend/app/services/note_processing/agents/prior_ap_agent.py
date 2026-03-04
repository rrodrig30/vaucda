"""
Prior Assessment & Plan Agent

Extracts and synthesizes structured context from prior assessments and plans.
This context informs:
- HPI: What was previously assessed and planned
- Assessment: Clinical progression from prior visits
- Plan: Continuity with prior treatment decisions

Per rules.txt COT Analysis:
- Prior A&P provides temporal continuity
- Prevents re-recommending completed procedures
- Tracks patient decisions (accepted/declined treatments)
- Identifies resolved vs. outstanding issues
"""

import re
from typing import List, Dict, Optional, Any
from ..llm_helper import synthesize_with_llm
from .history_cleaners import clean_llm_commentary
import logging

logger = logging.getLogger(__name__)


def _extract_diagnoses_from_assessment(assessment: str) -> List[str]:
    """
    Extract key diagnoses from an assessment section.

    Looks for:
    - Cancer diagnoses with staging
    - BPH/LUTS
    - Kidney stones
    - Other urologic conditions
    """
    diagnoses = []

    if not assessment:
        return diagnoses

    assessment_lower = assessment.lower()

    # Cancer patterns
    cancer_patterns = [
        r'(prostate\s+(?:cancer|adenocarcinoma|carcinoma)(?:\s*,?\s*gleason\s*\d+\+\d+=\d+)?)',
        r'(bladder\s+(?:cancer|carcinoma|urothelial))',
        r'(renal\s+(?:cell\s+)?(?:cancer|carcinoma|mass))',
        r'(kidney\s+(?:cancer|carcinoma|mass))',
        r'(testicular\s+(?:cancer|mass|tumor))',
    ]

    for pattern in cancer_patterns:
        matches = re.findall(pattern, assessment_lower, re.IGNORECASE)
        diagnoses.extend(matches)

    # BPH/LUTS patterns
    if any(term in assessment_lower for term in ['bph', 'benign prostatic', 'luts', 'lower urinary tract']):
        if 'bph' in assessment_lower or 'benign prostatic' in assessment_lower:
            diagnoses.append('BPH')
        if 'luts' in assessment_lower or 'lower urinary tract symptoms' in assessment_lower:
            diagnoses.append('LUTS')

    # Stone disease
    if any(term in assessment_lower for term in ['kidney stone', 'renal stone', 'ureteral stone', 'nephrolithiasis', 'urolithiasis']):
        diagnoses.append('nephrolithiasis')

    # Hematuria
    if 'hematuria' in assessment_lower:
        if 'gross' in assessment_lower:
            diagnoses.append('gross hematuria')
        elif 'microscopic' in assessment_lower:
            diagnoses.append('microscopic hematuria')
        else:
            diagnoses.append('hematuria')

    # Incontinence
    if 'incontinence' in assessment_lower:
        if 'stress' in assessment_lower:
            diagnoses.append('stress urinary incontinence')
        elif 'urge' in assessment_lower:
            diagnoses.append('urge incontinence')
        else:
            diagnoses.append('urinary incontinence')

    # PSA abnormality
    if any(term in assessment_lower for term in ['elevated psa', 'rising psa', 'psa elevation']):
        diagnoses.append('elevated PSA')

    return list(set(diagnoses))


def _extract_interventions_from_plan(plan: str) -> List[Dict[str, str]]:
    """
    Extract specific interventions from a plan section.

    Returns list of dicts with:
    - intervention: The procedure/treatment name
    - status: 'recommended', 'scheduled', 'completed', 'declined'
    - details: Additional context
    """
    interventions = []

    if not plan:
        return interventions

    plan_lower = plan.lower()

    # Procedure keywords and their contexts
    procedure_patterns = [
        # Biopsies
        (r'(prostate\s+biopsy|fusion\s+biopsy|mri[/-]?guided\s+biopsy|transrectal\s+biopsy)', 'biopsy'),
        # Cystoscopy
        (r'(cystoscopy|cysto)', 'cystoscopy'),
        # TURP/TURBT
        (r'(turp|transurethral\s+resection\s+(?:of\s+)?(?:the\s+)?prostate)', 'TURP'),
        (r'(turbt|transurethral\s+resection\s+(?:of\s+)?(?:bladder\s+)?tumor)', 'TURBT'),
        # Stone procedures
        (r'(ureteroscopy|urs)', 'ureteroscopy'),
        (r'(lithotripsy|eswl)', 'lithotripsy'),
        (r'(pcnl|percutaneous\s+nephrolithotomy)', 'PCNL'),
        # Imaging
        (r'(psma\s+pet(?:/ct)?|psma\s+scan)', 'PSMA PET'),
        (r'(bone\s+scan)', 'bone scan'),
        (r'(ct\s+(?:scan|urogram))', 'CT'),
        (r'(mri|mr\s+imaging)', 'MRI'),
        # Treatments
        (r'(radiation\s+therapy|radiotherapy|external\s+beam)', 'radiation therapy'),
        (r'(brachytherapy)', 'brachytherapy'),
        (r'(prostatectomy|radical\s+prostatectomy)', 'prostatectomy'),
        (r'(adt|androgen\s+deprivation|hormone\s+therapy|lupron|leuprolide|eligard)', 'ADT'),
        (r'(active\s+surveillance)', 'active surveillance'),
    ]

    for pattern, proc_name in procedure_patterns:
        matches = re.finditer(pattern, plan_lower, re.IGNORECASE)
        for match in matches:
            # Determine status based on PROXIMITY to the procedure
            # Use a narrower window (±40 chars) to prevent context bleeding
            # from adjacent procedure mentions
            start = max(0, match.start() - 40)
            end = min(len(plan_lower), match.end() + 40)
            context = plan_lower[start:end]

            # Status keywords with their priority for this procedure
            # Priority: declined (patient decision) > completed > scheduled > recommended
            # This ensures patient decisions are properly captured
            status_keywords = {
                'declined': ['declined', 'refused', 'deferred', 'patient declined', 'patient refused'],
                'completed': ['completed', 'done', 'performed', 'underwent', 'has had'],
                'scheduled': ['scheduled', 'schedule', 'will have', 'upcoming'],
            }

            # Find the closest status keyword to the procedure
            proc_pos = match.start() - start  # Position of procedure in context
            best_status = 'recommended'
            best_distance = float('inf')

            for status_name, keywords in status_keywords.items():
                for keyword in keywords:
                    keyword_match = re.search(r'\b' + re.escape(keyword) + r'\b', context)
                    if keyword_match:
                        # Calculate distance from procedure to status keyword
                        kw_pos = (keyword_match.start() + keyword_match.end()) // 2
                        distance = abs(kw_pos - proc_pos)

                        # Declined status gets priority when close to the procedure
                        # (multiplied by 0.8 to give it an edge in ties)
                        if status_name == 'declined':
                            distance *= 0.8

                        if distance < best_distance:
                            best_distance = distance
                            best_status = status_name

            interventions.append({
                'intervention': proc_name,
                'status': best_status,
                'details': context.strip()
            })

    # Deduplicate by intervention name, keeping most significant status
    status_priority = {'completed': 4, 'declined': 3, 'scheduled': 2, 'recommended': 1}
    seen = {}
    for interv in interventions:
        name = interv['intervention']
        if name not in seen or status_priority.get(interv['status'], 0) > status_priority.get(seen[name]['status'], 0):
            seen[name] = interv

    return list(seen.values())


def synthesize_prior_ap_context(
    prior_assessments: List[str],
    prior_plans: List[str],
    stage1_note: Optional[str] = None,
    patient_age: Optional[str] = None,
    patient_sex: Optional[str] = None,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synthesize structured context from prior assessments and plans.

    This provides temporal awareness to HPI, Assessment, and Plan agents:
    - What was diagnosed previously
    - What treatments were recommended/performed
    - What decisions patient made
    - What is outstanding vs resolved

    Args:
        prior_assessments: List of Assessment sections from prior GU notes
        prior_plans: List of Plan sections from prior GU notes
        stage1_note: Current Stage 1 note for context
        patient_age: Patient age for context
        patient_sex: Patient sex for context
        model: LLM model to use for synthesis

    Returns:
        Dict with structured context:
        - key_diagnoses: List of primary urologic diagnoses
        - prior_interventions: List of procedures/treatments with status
        - patient_decisions: Dict of treatment decisions (accepted/declined)
        - resolved_issues: List of issues that have been addressed
        - outstanding_issues: List of issues requiring follow-up
        - clinical_progression: Narrative summary of clinical progression
        - last_plan_summary: Summary of most recent plan
    """
    result = {
        'key_diagnoses': [],
        'prior_interventions': [],
        'patient_decisions': {},
        'resolved_issues': [],
        'outstanding_issues': [],
        'clinical_progression': '',
        'last_plan_summary': ''
    }

    if not prior_assessments and not prior_plans:
        return result

    # Extract diagnoses from all assessments
    all_diagnoses = []
    for assessment in prior_assessments:
        diagnoses = _extract_diagnoses_from_assessment(assessment)
        all_diagnoses.extend(diagnoses)
    result['key_diagnoses'] = list(set(all_diagnoses))

    # Extract interventions from all plans
    all_interventions = []
    for plan in prior_plans:
        interventions = _extract_interventions_from_plan(plan)
        all_interventions.extend(interventions)

    # Consolidate interventions
    intervention_map = {}
    for interv in all_interventions:
        name = interv['intervention']
        if name not in intervention_map:
            intervention_map[name] = interv
        else:
            # Keep the most definitive status
            status_priority = {'completed': 4, 'declined': 3, 'scheduled': 2, 'recommended': 1}
            if status_priority.get(interv['status'], 0) > status_priority.get(intervention_map[name]['status'], 0):
                intervention_map[name] = interv

    result['prior_interventions'] = list(intervention_map.values())

    # Identify patient decisions
    for interv in result['prior_interventions']:
        if interv['status'] == 'declined':
            result['patient_decisions'][interv['intervention']] = 'declined'
        elif interv['status'] == 'completed':
            result['patient_decisions'][interv['intervention']] = 'completed'

    # Use LLM to synthesize clinical progression narrative
    if (prior_assessments or prior_plans) and len(prior_assessments) + len(prior_plans) > 1:
        context_parts = []

        if prior_assessments:
            context_parts.append("=== PRIOR ASSESSMENTS (chronological) ===")
            for i, assessment in enumerate(prior_assessments, 1):
                context_parts.append(f"\n--- Assessment {i} ---\n{assessment[:1500]}")

        if prior_plans:
            context_parts.append("\n=== PRIOR PLANS (chronological) ===")
            for i, plan in enumerate(prior_plans, 1):
                context_parts.append(f"\n--- Plan {i} ---\n{plan[:1500]}")

        full_context = "\n".join(context_parts)

        progression_prompt = f"""Analyze these prior assessments and plans to extract clinical progression.

{full_context}

TASK: Create a concise clinical progression summary for the HPI/Assessment/Plan agents.

OUTPUT FORMAT (provide ONLY these sections, no other text):

CLINICAL PROGRESSION:
[2-3 sentence narrative describing how the patient's condition has evolved across visits]

RESOLVED ISSUES:
[Bullet list of issues that have been adequately addressed or completed]

OUTSTANDING ISSUES:
[Bullet list of issues still requiring follow-up or decision]

LAST VISIT RECOMMENDATIONS:
[Brief summary of what was recommended at the most recent visit]

PATIENT DECISIONS:
[Any documented patient decisions about treatments - accepted or declined]

CRITICAL: Use ONLY information from the provided assessments and plans. Do NOT invent or assume anything.
"""

        try:
            progression_response = synthesize_with_llm(
                prompt=progression_prompt,
                model=model,
                temperature=0.0
            )

            progression_response = clean_llm_commentary(progression_response)

            # Parse the structured response
            sections = {
                'CLINICAL PROGRESSION:': 'clinical_progression',
                'RESOLVED ISSUES:': 'resolved_issues',
                'OUTSTANDING ISSUES:': 'outstanding_issues',
                'LAST VISIT RECOMMENDATIONS:': 'last_plan_summary',
                'PATIENT DECISIONS:': '_decisions'
            }

            current_section = None
            current_content = []

            for line in progression_response.split('\n'):
                line_stripped = line.strip()

                # Check if this is a section header
                found_section = False
                for header, key in sections.items():
                    if line_stripped.upper().startswith(header.upper().rstrip(':')):
                        # Save previous section
                        if current_section:
                            content = '\n'.join(current_content).strip()
                            if current_section in ['resolved_issues', 'outstanding_issues']:
                                # Parse as list
                                items = [item.lstrip('- •*').strip() for item in content.split('\n') if item.strip() and item.strip() not in ['None', 'N/A', '-']]
                                result[current_section] = items
                            elif current_section == '_decisions':
                                # Parse decisions
                                for item in content.split('\n'):
                                    item = item.lstrip('- •*').strip()
                                    if 'declined' in item.lower():
                                        # Extract what was declined
                                        for proc in ['radiation', 'surgery', 'brachytherapy', 'ADT', 'prostatectomy']:
                                            if proc.lower() in item.lower():
                                                result['patient_decisions'][proc] = 'declined'
                                    elif 'accepted' in item.lower() or 'agreed' in item.lower():
                                        for proc in ['radiation', 'surgery', 'brachytherapy', 'ADT', 'prostatectomy', 'active surveillance']:
                                            if proc.lower() in item.lower():
                                                result['patient_decisions'][proc] = 'accepted'
                            else:
                                result[current_section] = content

                        current_section = key
                        current_content = []
                        # Check if content is on same line as header
                        remainder = line_stripped[len(header):].strip()
                        if remainder:
                            current_content.append(remainder)
                        found_section = True
                        break

                if not found_section and current_section:
                    current_content.append(line)

            # Don't forget the last section
            if current_section and current_content:
                content = '\n'.join(current_content).strip()
                if current_section in ['resolved_issues', 'outstanding_issues']:
                    items = [item.lstrip('- •*').strip() for item in content.split('\n') if item.strip() and item.strip() not in ['None', 'N/A', '-']]
                    result[current_section] = items
                elif current_section == '_decisions':
                    pass  # Already handled above
                else:
                    result[current_section] = content

        except Exception as e:
            logger.warning(f"Failed to synthesize prior A&P context: {e}")
            # ENHANCED FALLBACK: Preserve patient decisions and completed procedures
            # even when LLM synthesis fails - critical for anti-re-recommendation logic
            if prior_plans:
                result['last_plan_summary'] = prior_plans[-1][:500] if prior_plans[-1] else ''

                # Extract patient decisions from raw plans using regex
                # This ensures declined/completed status persists through errors
                all_plans_text = ' '.join(prior_plans).lower()

                # Check for declined treatments
                declined_patterns = [
                    (r'patient\s+declined\s+radiation', 'radiation therapy'),
                    (r'patient\s+declined\s+brachytherapy', 'brachytherapy'),
                    (r'patient\s+declined\s+surgery', 'surgery'),
                    (r'patient\s+declined\s+prostatectomy', 'prostatectomy'),
                    (r'declined\s+radiation\s+therapy', 'radiation therapy'),
                    (r'patient\s+refused\s+radiation', 'radiation therapy'),
                    (r'patient\s+deferred\s+radiation', 'radiation therapy'),
                ]
                for pattern, treatment in declined_patterns:
                    if re.search(pattern, all_plans_text, re.IGNORECASE):
                        result['patient_decisions'][treatment] = 'declined'
                        logger.info(f"Fallback: Detected patient declined {treatment}")

                # Check for completed procedures
                completed_patterns = [
                    (r'completed\s+(?:mri[/-]?guided\s+)?(?:prostate\s+)?biopsy', 'biopsy'),
                    (r'biopsy\s+(?:was\s+)?(?:performed|completed|done)', 'biopsy'),
                    (r'psma\s+pet\s+(?:completed|performed|done)', 'PSMA PET'),
                    (r'staging\s+(?:completed|done|workup\s+complete)', 'staging workup'),
                    (r'underwent\s+turp', 'TURP'),
                    (r'underwent\s+turbt', 'TURBT'),
                ]
                for pattern, procedure in completed_patterns:
                    if re.search(pattern, all_plans_text, re.IGNORECASE):
                        result['patient_decisions'][procedure] = 'completed'
                        # Also add to prior_interventions for consistency
                        result['prior_interventions'].append({
                            'intervention': procedure,
                            'status': 'completed',
                            'details': 'Extracted from fallback analysis'
                        })
                        logger.info(f"Fallback: Detected completed {procedure}")

    elif prior_plans:
        # Single plan - just use it as the last plan summary
        result['last_plan_summary'] = prior_plans[-1][:500] if prior_plans[-1] else ''

    return result


def format_prior_ap_for_hpi(prior_ap_context: Dict[str, Any]) -> str:
    """
    Format prior A&P context for inclusion in HPI synthesis.

    Creates a narrative-friendly summary that the HPI agent can use.
    """
    if not prior_ap_context or not any([
        prior_ap_context.get('key_diagnoses'),
        prior_ap_context.get('clinical_progression'),
        prior_ap_context.get('last_plan_summary')
    ]):
        return ""

    parts = []

    if prior_ap_context.get('clinical_progression'):
        parts.append(f"CLINICAL PROGRESSION FROM PRIOR VISITS:\n{prior_ap_context['clinical_progression']}")

    if prior_ap_context.get('key_diagnoses'):
        parts.append(f"ESTABLISHED DIAGNOSES: {', '.join(prior_ap_context['key_diagnoses'])}")

    if prior_ap_context.get('patient_decisions'):
        decisions = []
        for treatment, decision in prior_ap_context['patient_decisions'].items():
            decisions.append(f"{treatment}: {decision}")
        if decisions:
            parts.append(f"PATIENT TREATMENT DECISIONS: {'; '.join(decisions)}")

    if prior_ap_context.get('outstanding_issues'):
        parts.append(f"OUTSTANDING ISSUES: {'; '.join(prior_ap_context['outstanding_issues'])}")

    return '\n'.join(parts)


def format_prior_ap_for_assessment(prior_ap_context: Dict[str, Any]) -> str:
    """
    Format prior A&P context for inclusion in Assessment synthesis.

    Emphasizes progression and current status.
    """
    if not prior_ap_context:
        return ""

    parts = []

    if prior_ap_context.get('clinical_progression'):
        parts.append(f"CLINICAL PROGRESSION:\n{prior_ap_context['clinical_progression']}")

    if prior_ap_context.get('prior_interventions'):
        completed = [i['intervention'] for i in prior_ap_context['prior_interventions'] if i['status'] == 'completed']
        if completed:
            parts.append(f"COMPLETED PROCEDURES: {', '.join(completed)}")

    if prior_ap_context.get('resolved_issues'):
        parts.append(f"RESOLVED: {'; '.join(prior_ap_context['resolved_issues'])}")

    if prior_ap_context.get('outstanding_issues'):
        parts.append(f"OUTSTANDING: {'; '.join(prior_ap_context['outstanding_issues'])}")

    return '\n'.join(parts)


def format_prior_ap_for_plan(prior_ap_context: Dict[str, Any]) -> str:
    """
    Format prior A&P context for inclusion in Plan synthesis.

    Emphasizes what was recommended, what patient decided, what is still needed.
    """
    if not prior_ap_context:
        return ""

    parts = []

    if prior_ap_context.get('last_plan_summary'):
        parts.append(f"PRIOR VISIT PLAN:\n{prior_ap_context['last_plan_summary']}")

    if prior_ap_context.get('patient_decisions'):
        declined = [t for t, d in prior_ap_context['patient_decisions'].items() if d == 'declined']
        if declined:
            parts.append(f"PATIENT DECLINED: {', '.join(declined)} - do NOT re-recommend")

        accepted = [t for t, d in prior_ap_context['patient_decisions'].items() if d in ['accepted', 'completed']]
        if accepted:
            parts.append(f"PATIENT ACCEPTED/COMPLETED: {', '.join(accepted)}")

    if prior_ap_context.get('prior_interventions'):
        completed = [i['intervention'] for i in prior_ap_context['prior_interventions'] if i['status'] == 'completed']
        if completed:
            parts.append(f"COMPLETED PROCEDURES (do not re-recommend): {', '.join(completed)}")

    if prior_ap_context.get('outstanding_issues'):
        parts.append(f"OUTSTANDING ISSUES TO ADDRESS: {'; '.join(prior_ap_context['outstanding_issues'])}")

    return '\n'.join(parts)
