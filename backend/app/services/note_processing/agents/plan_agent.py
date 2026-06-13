"""
Plan Agent (Stage 2 Only)

Synthesizes treatment plan using:
- Stage 1 preliminary note
- Prior plans from historical GU notes
- Ambient listening transcript
- Calculator results
- RAG content (evidence-based guidelines)

Supports task-specific LLM configuration via LLMTaskConfig.
"""

import re
from typing import List, Optional, TYPE_CHECKING
from ..llm_helper import synthesize_with_llm
from .history_cleaners import clean_llm_commentary

if TYPE_CHECKING:
    from app.services.llm_config_manager import LLMTaskConfig


def synthesize_plan(
    stage1_note: str,
    prior_plans: List[str] = None,
    ambient_transcript: Optional[str] = None,
    calculator_results: Optional[dict] = None,
    rag_content: Optional[str] = None,
    model: Optional[str] = None,
    task_config: Optional["LLMTaskConfig"] = None,
    visit_progression: Optional[str] = None,
    cross_specialty_context: Optional[str] = None,
    prior_ap_context: Optional[str] = None
) -> str:
    """
    Synthesize treatment plan for Stage 2 (post-visit).

    PRIOR A&P CONTEXT INTEGRATION:
    - Uses structured prior Assessment & Plan context for treatment continuity
    - Respects patient decisions (does NOT re-recommend declined treatments)
    - Builds on completed procedures and outstanding issues
    - Provides clinical progression awareness

    Args:
        stage1_note: Complete preliminary note from Stage 1
        prior_plans: List of Plan sections from prior GU notes only
        ambient_transcript: Provider-patient conversation transcript (if available)
        calculator_results: Results from 44 specialized calculators (if available)
        rag_content: Evidence-based guidelines from Neo4j RAG (if available)
        model: LLM model to use for synthesis
        visit_progression: Narrative of what changed since last visit (optional)
        cross_specialty_context: Urologic content from non-GU specialty notes (optional)
        prior_ap_context: Formatted prior Assessment & Plan context (optional)

    Returns:
        Synthesized treatment plan text
    """
    if not prior_plans:
        prior_plans = []

    # Collect all Plan sections from prior notes
    all_plans = [p for p in prior_plans if p and p.strip()]

    # Build comprehensive context for LLM synthesis
    context_parts = []

    # Add Stage 1 note context (if provided) - THIS IS THE PRIMARY PATIENT DATA
    if stage1_note and stage1_note.strip():
        context_parts.append(f"""=== THIS PATIENT'S COMPLETE CLINICAL DATA ===

Read the ENTIRE note below carefully. Every section contains information that may be relevant to your plan - the CC, HPI, labs, imaging, pathology, medications, social history, dietary history, family history, and all other findings. Your plan must be based on a complete understanding of this patient's clinical picture.

{stage1_note}
""")

    # Add ambient transcript (if available)
    if ambient_transcript and ambient_transcript.strip():
        context_parts.append(f"=== PROVIDER-PATIENT CONVERSATION (AMBIENT LISTENING) ===\n{ambient_transcript}\n")

    # Add calculator results (if available)
    if calculator_results:
        calc_summary = []
        for calc_name, calc_result in calculator_results.items():
            # Format calculator result properly - use formatted_output if available
            if isinstance(calc_result, dict):
                if 'formatted_output' in calc_result:
                    calc_summary.append(calc_result['formatted_output'])
                elif 'interpretation' in calc_result:
                    calc_summary.append(f"{calc_result.get('calculator_name', calc_name)}: {calc_result['interpretation']}")
                else:
                    calc_summary.append(f"{calc_name}: {calc_result.get('result', str(calc_result))}")
            else:
                calc_summary.append(f"{calc_name}: {calc_result}")
        if calc_summary:
            context_parts.append(f"=== CLINICAL CALCULATOR RESULTS ===\n" + "\n\n".join(calc_summary) + "\n")

    # Add RAG content (if available)
    if rag_content and rag_content.strip():
        context_parts.append(f"=== EVIDENCE-BASED GUIDELINES (RAG) ===\n{rag_content}\n")

    # Add prior plans
    if all_plans:
        context_parts.append(f"=== PRIOR TREATMENT PLANS ===")
        for i, plan in enumerate(all_plans, 1):
            context_parts.append(f"\n--- Prior Plan {i} ---\n{plan}")

    # Add visit progression context (what changed since last visit)
    if visit_progression and visit_progression.strip():
        context_parts.append(f"=== VISIT PROGRESSION (SINCE LAST VISIT) ===\n{visit_progression}\n")

    # Add cross-specialty urologic context
    if cross_specialty_context and cross_specialty_context.strip():
        context_parts.append(f"=== CROSS-SPECIALTY UROLOGIC FINDINGS ===\n{cross_specialty_context}\n")

    # Add prior Assessment & Plan structured context
    if prior_ap_context and prior_ap_context.strip():
        context_parts.append(f"=== PRIOR ASSESSMENT & PLAN CONTEXT ===\n{prior_ap_context}\n")

    # Add user-defined rules (from Settings → Assessment & Plan Rules).
    # Plan-shaped directives (e.g. "When ordering TRUS Bx, also order rectal swab",
    # "No follow-up sooner than 90 days unless urgent") apply most strongly here.
    user_rules = list(getattr(task_config, "user_rules", []) or []) if task_config else []
    if user_rules:
        numbered = "\n".join(f"{i+1}. {r}" for i, r in enumerate(user_rules))
        context_parts.append(
            "=== USER-DEFINED RULES (MANDATORY — MUST BE FOLLOWED) ===\n"
            "The following rules were explicitly set by the clinician for THIS deployment.\n"
            "They override default guideline phrasing and any prior-visit habits.\n"
            "Apply every rule that is clinically relevant to this patient's plan.\n\n"
            f"{numbered}\n"
        )

    # If only prior plans and no other context, return the single plan
    if len(all_plans) == 1 and not any([stage1_note, ambient_transcript, calculator_results, rag_content]):
        return all_plans[0]

    # Build comprehensive synthesis prompt
    full_context = "\n".join(context_parts)

    # Build calculator-specific instructions based on WHAT WAS ACTUALLY SELECTED
    calculator_instructions = ""
    if calculator_results:
        calc_names = []
        for calc_id, calc_result in calculator_results.items():
            if isinstance(calc_result, dict):
                calc_names.append(calc_result.get('calculator_name', calc_id))
            else:
                calc_names.append(calc_id)

        calculator_instructions = f"""
CALCULATOR RESULTS AWARENESS (CRITICAL):
- The following calculators were selected and results are provided: {', '.join(calc_names)}
- ONLY incorporate calculator results that appear in the CLINICAL CALCULATOR RESULTS section above
- Do NOT mention any calculator that was NOT selected (no "unable to calculate", "CCI not available", etc.)
- If a calculator was NOT selected, do NOT reference it at all in your plan
"""

        # Add CCI-specific instructions ONLY if CCI was selected
        if any('cci' in calc_id.lower() or 'charlson' in calc_id.lower() for calc_id in calculator_results.keys()):
            calculator_instructions += """
CCI-SPECIFIC REQUIREMENTS:
- Only reference conditions that ACTUALLY appear in PAST MEDICAL HISTORY
- Do NOT invent conditions like CHF, COPD, diabetes, CKD unless they are documented in PMH
- The CCI score must be based on VERIFIED diagnoses from the patient's actual medical history
- CCI is a RISK STRATIFICATION TOOL, not a condition to be treated - do NOT create a "Problem #N: Charlson Comorbidity Index"
"""
    else:
        calculator_instructions = """
CALCULATOR RESULTS:
- No calculators were selected for this plan
- Do NOT mention any calculator results or scores (no CCI, PCPT, CAPRA, etc.)
- Do NOT state "unable to calculate" or "calculator not provided" for any calculator
"""

    user_rules_directive = ""
    if user_rules:
        user_rules_directive = (
            "\nUSER-DEFINED RULES (HIGHEST PRIORITY — MANDATORY):\n"
            "Read the 'USER-DEFINED RULES' section above. Every rule listed there was set by the\n"
            "clinician and is a HARD CONSTRAINT on this plan. Examples of how to apply:\n"
            "  - If a rule says 'when ordering TRUS biopsy, also order X', and your plan includes\n"
            "    a TRUS biopsy, you MUST add bullet items ordering X in that same problem block.\n"
            "  - If a rule says 'no follow-up sooner than N days unless urgent', any follow-up\n"
            "    interval you write must be >= N days unless the clinical picture is urgent and\n"
            "    you explicitly note the urgency.\n"
            "Apply every rule that is relevant. Do NOT silently ignore them.\n"
        )

    instructions = f"""
You are synthesizing a comprehensive TREATMENT PLAN for a urology patient.

AVAILABLE INFORMATION:
{full_context}
{user_rules_directive}

CRITICAL - READ THE CHIEF COMPLAINT FIRST (MANDATORY):
Look at the "CC:" line in the Stage 1 note. The Chief Complaint is the PRIMARY reason for this visit.
Problem #1 in your output MUST address this Chief Complaint.

PROBLEM SELECTION RULES:
- Problem #1 MUST match the Chief Complaint from the "CC:" line
- ONLY create problems for conditions the patient ACTUALLY HAS (documented in HPI, PMH, or Assessment)
- Do NOT create problems for conditions the patient does NOT have
- Do NOT add hypothetical problems ("if the patient had X, we would...")
- If a condition is not mentioned in the patient's history, do NOT include it as a problem

TASK:
Using THIS PATIENT'S specific history, labs, imaging, medications, surgical history, and other findings from the Stage 1 note above, create urology-focused plans addressing each of the patient's active problems.

CLINICAL REASONING REQUIREMENTS:
1. For EACH problem, consider what is unique about THIS patient:
   - What surgeries have they already had for this condition?
   - What medications are they already on?
   - What do their labs and imaging show?
   - What treatments have been tried and failed?
2. Tailor recommendations to THIS patient's circumstances - do NOT give generic guideline recommendations that ignore the patient's history
3. Follow AUA guidelines and NCCN guidelines when appropriate
4. If no guidelines are available, follow best urology practices
5. If the patient has already had definitive treatment (e.g., TURP for BPH), focus on post-treatment management, not initial treatment options

PLAN REQUIREMENTS:
1. STARTS with Problem #1 addressing the Chief Complaint
2. Integrates information from ALL available sources (Stage 1 note, prior plans, ambient conversation, calculator results)
3. Addresses all active urologic conditions with patient-specific recommendations
4. Includes specific interventions, medications, procedures, and follow-up
5. Incorporates patient preferences/concerns from ambient transcript (if available)
6. SURVEILLANCE SCHEDULE RECOGNITION (CRITICAL):
   - Look for surveillance schedules in the HPI or Assessment (e.g., "q3 month cysto for 2 years, then q6 month until 5 years")
   - Calculate and include the NEXT scheduled procedure date based on the last procedure date
   - For bladder cancer: Include next cystoscopy date and next upper tract imaging (CT urogram) date per NCCN guidelines
   - For prostate cancer: Include next PSA date and any scheduled imaging
   - Include scheduled procedure dates in the plan (e.g., "Next cystoscopy scheduled for March 2026")
   - If a CT urogram or other imaging is due per guidelines, include it with target month/year

PROBLEM ORDERING (MANDATORY):
- Problem #1: ALWAYS the Chief Complaint from the "CC:" line
- Problem #2-N: Other urologic issues in order of clinical importance
- Non-urologic problems (hypertension, diabetes) should be listed LAST or omitted

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

DATA INTEGRITY REQUIREMENTS:
- Use ONLY data values that appear in the Stage 1 note above
- Every numeric value (PSA, creatinine, doses) must appear VERBATIM in the Stage 1 note
- If you cannot find a value in the Stage 1 note, do NOT mention it
- PSA < 4.0 ng/mL is NORMAL - do not call it "Elevated PSA"

{calculator_instructions}
TEMPORAL AWARENESS (MANDATORY - READ CAREFULLY):
If VISIT PROGRESSION data is provided, read it FIRST. The plan MUST progress from the prior visit.

ABSOLUTE RULES - VIOLATIONS ARE CLINICAL ERRORS:

1. NEVER RE-RECOMMEND COMPLETED PROCEDURES:
   - If PATHOLOGY RESULTS exist for prostate biopsy → biopsy is DONE → discuss TREATMENT, not more biopsy
   - If PSMA PET results exist → staging is DONE → discuss TREATMENT OPTIONS based on staging
   - If MRI results exist → imaging is DONE → do NOT order another MRI unless specifically indicated

2. RESPECT PATIENT DECISIONS:
   - If patient "declined radiation" → DO NOT recommend radiation therapy
   - If patient "declined surgery" → DO NOT recommend prostatectomy
   - Instead, recommend ALTERNATIVE treatments the patient has not declined

3. IDENTIFY THE CURRENT DECISION POINT:
   Ask: "What was recommended last visit, and what happened?"
   - Biopsy recommended → Biopsy DONE → NOW: discuss treatment options
   - Staging recommended → Staging DONE → NOW: select treatment approach
   - Radiation offered → Patient declined → NOW: discuss ADT or other alternatives
   - Treatment started → NOW: monitor response

4. PROGRESSION EXAMPLES:

   WRONG (repeating prior visit):
   "Problem #1: Prostate cancer
   - Schedule fusion biopsy to complete staging"
   → This is WRONG if biopsy pathology already exists in the data!

   CORRECT (progressing from prior visit):
   "Problem #1: Prostate adenocarcinoma, Gleason 4+3=7, PSMA-localized
   - Discussed treatment options given biopsy showing GG3 disease
   - Patient is not a surgical candidate (prior abdominal surgeries)
   - Patient declined radiation therapy (offered brachytherapy, declined)
   - Recommend androgen deprivation therapy with leuprolide acetate
   - Will add bicalutamide for initial testosterone flare prevention
   - Schedule DEXA scan for baseline bone density before ADT"

5. HOW TO CHECK IF A PROCEDURE IS DONE:
   - Look at PATHOLOGY RESULTS section: if prostate biopsy results exist → biopsy is DONE
   - Look at IMAGING section: if PSMA PET results exist → staging is DONE
   - Look at VISIT PROGRESSION section: it explicitly states what is COMPLETED

CROSS-SPECIALTY INTEGRATION:
- If CROSS-SPECIALTY UROLOGIC FINDINGS are provided, address urologically-relevant items in your plan:
  - Radiation Oncology ADT requests: If ADT is requested, include ADT administration in plan (Lupron, Eligard, etc.)
  - Cancelled procedures: Note the cancellation and reschedule or adjust plan accordingly
  - Hospital admissions: Address post-discharge urologic followup (e.g., "followup after urosepsis admission")
  - Oncology coordination: Include any urologic components of oncologic care
  - Cardiology clearance: Note if clearance obtained for pending procedures
  - ID recommendations: Include antibiotic prophylaxis or infection management as applicable
- ONLY address cross-specialty items that have urologic implications

PRIOR A&P CONTEXT INTEGRATION (when PRIOR ASSESSMENT & PLAN CONTEXT provided):
- This section contains CRITICAL information about treatment continuity
- PRIOR VISIT PLAN: What was recommended last time - check what has been completed
- PATIENT DECLINED: These treatments were REFUSED by the patient - do NOT re-recommend them
  - If patient declined radiation → recommend ADT or other alternatives, NOT radiation
  - If patient declined surgery → recommend non-surgical options
- COMPLETED PROCEDURES: These are DONE - do not schedule them again
  - If biopsy completed → discuss results and next steps, not more biopsies
  - If staging completed → discuss treatment options, not more staging
- OUTSTANDING ISSUES: These still need to be addressed - focus plan on these
- Your plan should PROGRESS from the prior visit, not repeat it
- Example: If prior plan was "complete staging", and staging is now done, plan should be "discuss treatment options based on staging results"

CONTEXT AWARENESS:
- This is a UROLOGY CLINIC NOTE - do NOT recommend "referral to urology" (patient is already here)
- Do NOT recommend tests/imaging that have already been completed (check IMAGING section)
- Do NOT recommend procedures when contraindicated by current labs (e.g., cystoscopy with active UTI)

OUTPUT REQUIREMENTS:
- Provide ONLY the treatment plan text
- NO meta-commentary, preamble, or explanations
- Just the clean, clinical plan text

The plan should read as a coherent, actionable treatment strategy that reflects THIS patient's specific clinical situation.
"""

    # Call LLM with task-specific configuration
    # task_config takes precedence - uses provider/model/temperature from user settings
    # Falls back to model parameter if task_config not provided (backwards compatibility)
    synthesized_plan = synthesize_with_llm(
        prompt=instructions,
        model=model,
        temperature=0.0,
        task_config=task_config
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

    # POST-PROCESSING: Fix common LLM typos
    typo_corrections = {
        'CONTRVEST': 'CONTRAST',
        'CONTREST': 'CONTRAST',
        'CONTRST': 'CONTRAST',
        'IV CONTRVEST': 'IV CONTRAST',
    }
    for typo, correction in typo_corrections.items():
        synthesized_plan = synthesized_plan.replace(typo, correction)

    # POST-PROCESSING: Remove inappropriate urologist referral recommendations
    # This IS a urology clinic note - patient is already seeing a urologist
    urology_referral_patterns = [
        r'-\s*Consider\s+referral\s+to\s+urolog(?:y|ist)[^\n]*\n?',
        r'-\s*Refer(?:ral)?\s+to\s+urolog(?:y|ist)[^\n]*\n?',
        r'-\s*Consider\s+urolog(?:y|ist)\s+(?:consultation|referral|specialist)[^\n]*\n?',
        r'-\s*Recommend\s+urolog(?:y|ist)\s+(?:evaluation|consultation)[^\n]*\n?',
    ]
    for pattern in urology_referral_patterns:
        synthesized_plan = re.sub(pattern, '', synthesized_plan, flags=re.IGNORECASE)

    # POST-PROCESSING: Fix duplicate word patterns (e.g., "Surveillance Surveillance")
    synthesized_plan = re.sub(r'\b(\w+)\s+\1\b', r'\1', synthesized_plan, flags=re.IGNORECASE)

    # POST-PROCESSING: Fix "Elevated PSA" problem when PSA is normal
    # Check if all PSA values in stage1_note are < 4.0
    if stage1_note:
        psa_values = []
        psa_curve_match = re.search(
            r'PSA\s+CURVE:(.*?)(?=\n\s*(?:PATHOLOGY|MEDICATIONS|ALLERGIES|===|PAST|IMAGING|$))',
            stage1_note, re.DOTALL | re.IGNORECASE
        )
        if psa_curve_match:
            psa_section = psa_curve_match.group(1)
            # CRITICAL: Must distinguish PSA values from timestamps (HHMM format)
            # and handle H suffix for values > 4.0
            # Formats:
            #   [r] Jan 02, 2024 13:57    0.65      (HH:MM time with colon)
            #   [r] Jan 02, 2024 1357    0.65        (HHMM time without colon - legacy)
            #   [r] Jan 02, 2024         0.65        (no time, padded spaces)
            #   [r] Jan 02, 2024 13:57    5.23 H     (H suffix for values > 4.0)
            for line in psa_section.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                # HH:MM format: [r] Nov 06, 2025 08:08    0.51
                m = re.search(
                    r'(?:\[r\]\s+)?[A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+(\d+\.?\d*)',
                    line
                )
                if m:
                    try:
                        psa_values.append(float(m.group(1)))
                    except ValueError:
                        pass
                    continue
                # HHMM format (legacy): [r] Nov 06, 2025 0808    0.51
                m = re.search(
                    r'(?:\[r\]\s+)?[A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s+\d{4}\s{2,}(\d+\.?\d*)',
                    line
                )
                if m:
                    try:
                        psa_values.append(float(m.group(1)))
                    except ValueError:
                        pass
                    continue
                # No time, padded spaces: [r] Nov 06, 2025         0.51
                m = re.search(
                    r'(?:\[r\]\s+)?[A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s{5,}(\d+\.?\d*)',
                    line
                )
                if m:
                    try:
                        psa_values.append(float(m.group(1)))
                    except ValueError:
                        pass

        # If all PSA values are < 4.0, rename "Elevated PSA" to "PSA Surveillance"
        if psa_values and all(psa < 4.0 for psa in psa_values):
            # Replace "Problem #N: Elevated PSA" with "Problem #N: PSA Surveillance"
            synthesized_plan = re.sub(
                r'(Problem\s*#\d+:\s*)Elevated\s+PSA',
                r'\1PSA Surveillance',
                synthesized_plan,
                flags=re.IGNORECASE
            )

    return synthesized_plan.strip()
