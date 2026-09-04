"""
Assessment Agent (Stage 2 Only)

Synthesizes assessment/impression using:
- Stage 1 preliminary note
- Prior assessments from historical GU notes
- Ambient listening transcript
- Calculator results
- RAG content (evidence-based guidelines)

Supports task-specific LLM configuration via LLMTaskConfig.
"""

import re
from typing import List, Optional, Set, TYPE_CHECKING
from ..llm_helper import synthesize_with_llm
from .history_cleaners import clean_llm_commentary
from .age_guardrail import build_age_guardrail_block

if TYPE_CHECKING:
    from app.services.llm_config_manager import LLMTaskConfig


def _extract_valid_psa_values(stage1_note: str) -> Set[str]:
    """
    Extract all valid PSA values from the PSA CURVE section.

    Returns set of PSA values as strings (to avoid floating point comparison issues).
    """
    valid_psa_values = set()

    if not stage1_note:
        return valid_psa_values

    # Find PSA CURVE section
    psa_curve_match = re.search(
        r'PSA\s+CURVE:(.*?)(?=\n\s*(?:PATHOLOGY|MEDICATIONS|ALLERGIES|===|PAST|IMAGING|$))',
        stage1_note,
        re.DOTALL | re.IGNORECASE
    )

    if psa_curve_match:
        psa_section = psa_curve_match.group(1)
        # Extract PSA values from the PSA CURVE section
        # CRITICAL: Must distinguish PSA values from timestamps (HHMM format)
        # Formats:
        #   [r] Jan 02, 2024 13:57    0.65      (HH:MM time with colon)
        #   [r] Jan 02, 2024 1357    0.65        (HHMM time without colon - legacy)
        #   Nov 06, 2025 08:08: 0.51             (colon separator before value)
        #   [r] Jan 02, 2024         0.65        (no time, padded spaces)
        for line in psa_section.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Strategy: Extract the LAST decimal number on each PSA curve line
            # The PSA value is always the last number, after the date/time
            # Pattern: match lines with [r] prefix or date format, capture last number
            # HH:MM time format: [r] Nov 06, 2025 08:08    0.51
            hhmm_match = re.search(
                r'(?:\[r\]\s+)?[A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s+\d{1,2}:\d{2}\s+(\d+\.?\d*)',
                line
            )
            if hhmm_match:
                valid_psa_values.add(hhmm_match.group(1).strip())
                continue
            # HHMM time format (legacy): [r] Nov 06, 2025 0808    0.51
            # CRITICAL: 4-digit time followed by 2+ spaces then decimal value
            hhmm_legacy_match = re.search(
                r'(?:\[r\]\s+)?[A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s+\d{4}\s{2,}(\d+\.?\d*)',
                line
            )
            if hhmm_legacy_match:
                valid_psa_values.add(hhmm_legacy_match.group(1).strip())
                continue
            # Colon separator format: Nov 06, 2025 08:08: 0.51
            colon_match = re.search(
                r'[A-Za-z]{3}\s+\d{1,2},\s+\d{4}(?:\s+\d{1,2}:\d{2})?:\s*(\d+\.?\d*)',
                line
            )
            if colon_match:
                valid_psa_values.add(colon_match.group(1).strip())
                continue
            # No time, padded spaces: [r] Nov 06, 2025         0.51
            notime_match = re.search(
                r'(?:\[r\]\s+)?[A-Za-z]{3}\s+\d{1,2},\s+\d{4}\s{5,}(\d+\.?\d*)',
                line
            )
            if notime_match:
                valid_psa_values.add(notime_match.group(1).strip())
                continue

    # Also check LABS section for PSA
    labs_match = re.search(r'PSA:\s*(\d+\.?\d*)', stage1_note, re.IGNORECASE)
    if labs_match:
        valid_psa_values.add(labs_match.group(1).strip())

    return valid_psa_values


def _validate_psa_values_in_text(text: str, valid_psa_values: Set[str]) -> str:
    """
    Validate and correct PSA values in LLM-generated text.

    Removes or corrects sentences containing hallucinated PSA values.
    """
    if not valid_psa_values:
        return text

    validated_text = text

    # Find ALL numeric values that look like PSA values in PSA-related sentences
    # This catches values like "2.8" that appear near "PSA"
    psa_sentence_pattern = r'([^.]*\bPSA\b[^.]*\.)'

    for sentence_match in re.finditer(psa_sentence_pattern, text, re.IGNORECASE):
        sentence = sentence_match.group(1)

        # Find all numeric values in this PSA sentence
        all_numbers = re.findall(r'\b(\d+\.\d+)\b', sentence)

        corrected_sentence = sentence
        has_hallucination = False

        for num_str in all_numbers:
            # Skip if this number is a valid PSA value
            if num_str in valid_psa_values:
                continue

            # Check if it's close to any valid value
            try:
                num_val = float(num_str)
            except ValueError:
                continue

            # Skip numbers that are clearly not PSA values (dates, sizes, etc.)
            if num_val > 100:  # PSA values rarely exceed 100
                continue

            # Check for hallucination
            is_hallucinated = True
            for valid_val in valid_psa_values:
                try:
                    actual = float(valid_val)
                    # Allow exact match or very close match (< 0.05)
                    if abs(num_val - actual) < 0.05:
                        is_hallucinated = False
                        break
                    # Check for 10x error
                    if abs(num_val - actual * 10) < 0.1:
                        # Replace with correct value
                        corrected_sentence = corrected_sentence.replace(num_str, valid_val)
                        is_hallucinated = False
                        break
                except ValueError:
                    continue

            if is_hallucinated and num_val < 20:  # Likely a PSA value, not a date
                has_hallucination = True
                # Try to find the closest valid value
                closest = min(valid_psa_values, key=lambda v: abs(float(v) - num_val))
                corrected_sentence = corrected_sentence.replace(num_str, closest)

        if corrected_sentence != sentence:
            validated_text = validated_text.replace(sentence, corrected_sentence)

    # Clean up multiple spaces and empty lines
    validated_text = re.sub(r' +', ' ', validated_text)
    validated_text = re.sub(r'\n\s*\n', '\n\n', validated_text)

    return validated_text.strip()


def synthesize_assessment(
    stage1_note: str,
    prior_assessments: List[str] = None,
    ambient_transcript: Optional[str] = None,
    calculator_results: Optional[dict] = None,
    rag_content: Optional[str] = None,
    model: Optional[str] = None,
    task_config: Optional["LLMTaskConfig"] = None,
    visit_progression: Optional[str] = None,
    cross_specialty_context: Optional[str] = None,
    prior_ap_context: Optional[str] = None,
    authoritative_facts: Optional[str] = None,
    hpi_skeleton: Optional[str] = None,
) -> str:
    """
    Synthesize clinical assessment for Stage 2 (post-visit).

    PRIOR A&P CONTEXT INTEGRATION:
    - Uses structured prior Assessment & Plan context for clinical progression
    - Provides awareness of completed procedures and patient decisions
    - Enables continuity with what was previously planned

    Args:
        stage1_note: Complete preliminary note from Stage 1
        prior_assessments: List of Assessment sections from prior GU notes only
        ambient_transcript: Provider-patient conversation transcript (if available)
        calculator_results: Results from 44 specialized calculators (if available)
        rag_content: Evidence-based guidelines from Neo4j RAG (if available)
        model: LLM model to use for synthesis
        visit_progression: Narrative of what changed since last visit (optional)
        cross_specialty_context: Urologic content from non-GU specialty notes (optional)
        prior_ap_context: Formatted prior Assessment & Plan context (optional)

    Returns:
        Synthesized assessment text (4-8 sentence narrative summary)
    """
    if not prior_assessments:
        prior_assessments = []

    # Collect all Assessment sections from prior notes
    all_assessments = [a for a in prior_assessments if a and a.strip()]

    # Build comprehensive context for LLM synthesis
    context_parts = []

    # AUTHORITATIVE GROUND TRUTH must appear FIRST so the LLM treats every
    # subsequent context block as subordinate to it. This block is built
    # deterministically by patient_status_facts and lists the verdicts
    # (cancer status, treatment-naive status, Phoenix applicability) plus
    # explicit ABSOLUTE RULES the LLM must follow.
    if authoritative_facts and authoritative_facts.strip():
        context_parts.append(authoritative_facts + "\n")

    # Age & life-expectancy guardrail. Same deterministic block the
    # Plan agent receives — the Assessment must agree with the bucket
    # so its recommendations are congruent with what the Plan will
    # write. Otherwise the Assessment says "continue PSA surveillance,
    # consider mpMRI" in an 87-year-old and the Plan dutifully repeats
    # it.
    age_guardrail = build_age_guardrail_block(stage1_note or "")
    if age_guardrail:
        context_parts.append(age_guardrail)

    # PHASE 2.1: The HPI was just rendered from this same skeleton.
    # Surface it here so the Assessment uses the same chronological view
    # and same current-regimen list — no drift between sections.
    if hpi_skeleton and hpi_skeleton.strip():
        context_parts.append(hpi_skeleton + "\n")

    # ROOT CAUSE #3 FIX: Add structured lab interpretation BEFORE Stage 1 note
    # This provides clear, unambiguous lab values to prevent LLM hallucinations
    if stage1_note:
        try:
            from ..lab_interpreter import get_structured_lab_interpretation
            structured_labs = get_structured_lab_interpretation(stage1_note)
            if structured_labs:
                context_parts.append(structured_labs + "\n")
        except ImportError:
            pass  # Continue without structured interpretation if module not available

    # Add Stage 1 note context (if provided) - THIS IS THE PRIMARY PATIENT DATA
    if stage1_note and stage1_note.strip():
        context_parts.append(f"""=== THIS PATIENT'S COMPLETE CLINICAL DATA ===

Read the ENTIRE note below carefully. Every section contains information that may be relevant to your assessment - the CC, HPI, labs, imaging, pathology, medications, social history, dietary history, family history, and all other findings. Your assessment must be based on a complete understanding of this patient's clinical picture.

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

    # Add prior assessments
    if all_assessments:
        context_parts.append(f"=== PRIOR CLINICAL ASSESSMENTS ===")
        for i, assessment in enumerate(all_assessments, 1):
            context_parts.append(f"\n--- Prior Assessment {i} ---\n{assessment}")

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
    # These are clinician-authored directives that MUST be enforced.
    user_rules = list(getattr(task_config, "user_rules", []) or []) if task_config else []
    if user_rules:
        numbered = "\n".join(f"{i+1}. {r}" for i, r in enumerate(user_rules))
        context_parts.append(
            "=== USER-DEFINED RULES (MANDATORY — MUST BE FOLLOWED) ===\n"
            "The following rules were explicitly set by the clinician for THIS deployment.\n"
            "They override default behavior. Apply every rule that is relevant to this patient.\n\n"
            f"{numbered}\n"
        )

    # If only prior assessments and no other context, return the single assessment
    if len(all_assessments) == 1 and not any([stage1_note, ambient_transcript, calculator_results, rag_content]):
        return all_assessments[0]

    # Build comprehensive synthesis prompt
    full_context = "\n".join(context_parts)

    # Extract ACTUAL PSA values from Stage 1 note to pass explicitly
    psa_values = []
    if stage1_note:
        import re
        # Extract PSA values from PSA CURVE section
        psa_curve_match = re.search(r'PSA CURVE:(.*?)(?=\n\s*(?:PATHOLOGY|MEDICATIONS|ALLERGIES|===|$))', stage1_note, re.DOTALL | re.IGNORECASE)
        if psa_curve_match:
            psa_section = psa_curve_match.group(1)
            # Extract individual PSA values with dates
            # CRITICAL: Must handle both HH:MM and HHMM time formats
            for line in psa_section.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                # HH:MM format: [r] Nov 06, 2025 08:08    0.51
                m = re.search(
                    r'\[r\]\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+\d{1,2}:\d{2}\s+(\d+\.?\d*)',
                    line
                )
                if m:
                    psa_values.append(f"{m.group(1)}: {m.group(2)}")
                    continue
                # HHMM format (legacy): [r] Nov 06, 2025 0808    0.51
                m = re.search(
                    r'\[r\]\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+\d{4}\s{2,}(\d+\.?\d*)',
                    line
                )
                if m:
                    psa_values.append(f"{m.group(1)}: {m.group(2)}")
                    continue
                # No time format: [r] Nov 06, 2025         0.51
                m = re.search(
                    r'\[r\]\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s{5,}(\d+\.?\d*)',
                    line
                )
                if m:
                    psa_values.append(f"{m.group(1)}: {m.group(2)}")

    psa_context = ""
    if psa_values:
        psa_context = f"""
ACTUAL PSA VALUES FROM THIS PATIENT'S RECORD (use ONLY these values):
{chr(10).join(psa_values[:5])}  (most recent values shown)

CRITICAL: If you mention any PSA value, it MUST match one of the values listed above EXACTLY.
"""

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
- The following calculators were selected and their results are provided: {', '.join(calc_names)}
- ONLY discuss calculator results that appear in the CLINICAL CALCULATOR RESULTS section above
- Do NOT mention any calculator that was NOT selected (no "unable to calculate", "CCI not provided", etc.)
- If a calculator was NOT selected, do NOT reference it at all in your assessment
- Incorporate the PROVIDED calculator results naturally into your clinical narrative
"""

        # Add CCI-specific instructions ONLY if CCI was selected
        if any('cci' in calc_id.lower() or 'charlson' in calc_id.lower() for calc_id in calculator_results.keys()):
            calculator_instructions += """
CCI-SPECIFIC FORMATTING:
- The Charlson Comorbidity Index (CCI) is a CLINICAL CALCULATOR SCORE, NOT a lab value
- CCI produces a numeric score (0-37) and an estimated 10-year survival percentage - these have NO UNITS
- When mentioning CCI, write it as: "Charlson Comorbidity Index score of X with an estimated 10-year survival of Y%"
- CCI comorbidities MUST match the PAST MEDICAL HISTORY - do NOT invent conditions
"""

        # Add PCPT-specific instructions ONLY if PCPT was selected
        if any('pcpt' in calc_id.lower() for calc_id in calculator_results.keys()):
            calculator_instructions += """
PCPT-SPECIFIC FORMATTING:
- Include the PCPT risk percentage in your assessment
- PCPT calculates prostate cancer risk - include this finding in your narrative
"""
    else:
        calculator_instructions = """
CALCULATOR RESULTS:
- No calculators were selected for this assessment
- Do NOT mention any calculator results or scores (no CCI, PCPT, CAPRA, etc.)
- Do NOT state "unable to calculate" or "calculator not provided" for any calculator
"""

    user_rules_directive = ""
    if user_rules:
        user_rules_directive = (
            "\nUSER-DEFINED RULES (HIGHEST PRIORITY — MANDATORY):\n"
            "Read the 'USER-DEFINED RULES' section above. Every rule listed there was set by the\n"
            "clinician and must be applied wherever clinically relevant to this patient. These\n"
            "rules take precedence over general guideline phrasing. Do NOT silently ignore them.\n"
        )

    authoritative_directive = ""
    if authoritative_facts:
        authoritative_directive = (
            "\n=== AUTHORITATIVE GROUND TRUTH ENFORCEMENT (READ THIS FIRST) ===\n"
            "The FIRST context block above (titled 'PATIENT GROUND TRUTH') was\n"
            "derived deterministically from the source documents. It is the\n"
            "single source of truth for this patient's cancer status, treatment\n"
            "history, and whether Phoenix biochemical-recurrence vocabulary is\n"
            "applicable. The ABSOLUTE RULES listed at the end of that block are\n"
            "non-negotiable. If your output contains ANY phrase forbidden by\n"
            "those rules, your answer is wrong.\n"
            "\n"
            "In particular: if TREATMENT_NAIVE is True, the patient has NEVER\n"
            "received prostate-cancer treatment. Do NOT invent any. If\n"
            "PROSTATE_CANCER_STATUS is ABSENT, the patient has NO cancer\n"
            "diagnosis. Do NOT diagnose one. Rising PSA in such a patient is a\n"
            "workup question for new disease, not biochemical recurrence.\n"
        )

    skeleton_directive = ""
    if hpi_skeleton and hpi_skeleton.strip():
        skeleton_directive = (
            "\n=== HPI SKELETON ALIGNMENT (MANDATORY) ===\n"
            "An HPI STORY SKELETON appears in the context above. The HPI section\n"
            "of this note was just rendered from that same skeleton. Your\n"
            "Assessment MUST stay aligned with it:\n"
            "  - Open by naming the disease phase the skeleton's INTRO states\n"
            "    (e.g. 'metastatic castration-resistant prostate cancer on\n"
            "    combination systemic therapy').\n"
            "  - Summarize the trajectory using only the events the skeleton\n"
            "    lists (diagnosis, treatment history, PSA trajectory, key\n"
            "    procedure findings). Do NOT introduce events the skeleton\n"
            "    does not name.\n"
            "  - Reference the CURRENT REGIMEN from the skeleton when\n"
            "    describing what the patient is doing now. Do NOT call the\n"
            "    patient 'off treatment' if the skeleton's CURRENT REGIMEN\n"
            "    has active oncology meds.\n"
            "  - Close with the phase-appropriate next step. The Plan agent\n"
            "    receives your Assessment text as the contract its Problem\n"
            "    #N items must implement, so your closing recommendation\n"
            "    sentence is what the Plan will execute. Make it explicit\n"
            "    and singular: name the interval, the next test, the\n"
            "    referral, and whether to continue / hold / escalate\n"
            "    therapy. Examples of phase-appropriate closings:\n"
            "      mCRPC: 'Continue Eligard q6mo plus abiraterone/prednisone;\n"
            "             monitor PSA q6-8 weeks; consider bone-protective\n"
            "             therapy given documented metastasis.'\n"
            "      Biochemical recurrence (post-radiation, treatment-naive\n"
            "             for salvage): 'Obtain PSMA-PET to restage; refer to\n"
            "             radiation oncology / medical oncology for salvage\n"
            "             discussion.'\n"
            "      Post-treatment surveillance with stable PSA: 'Continue PSA\n"
            "             surveillance every 6 months; mpMRI if PSA crosses\n"
            "             threshold.'\n"
            "      Treatment-naive with rising PSA: 'Repeat PSA in 3 months;\n"
            "             consider mpMRI / targeted biopsy if PSA persists.'\n"
        )

    instructions = f"""
You are synthesizing a comprehensive clinical ASSESSMENT for a urology patient.

AVAILABLE INFORMATION:
{full_context}
{psa_context}
{authoritative_directive}
{skeleton_directive}
{user_rules_directive}

TASK:
Using THIS PATIENT'S specific Chief Complaint, HPI, history, labs, imaging, medications, and surgical history from the Stage 1 note above, create a 4-8 sentence narrative assessment that summarizes the patient's current urologic clinical status.

CLINICAL REASONING REQUIREMENTS:
1. START by identifying the Chief Complaint (CC) - this is WHY the patient is here
2. Summarize what the HPI tells us about the patient's current condition
3. Reference relevant findings from their history, labs, and imaging
4. If calculator results are provided, incorporate them appropriately
5. Follow AUA guidelines and NCCN guidelines when characterizing findings
6. The assessment must reflect THIS patient's specific situation, not generic descriptions
7. AGE / LIFE-EXPECTANCY GUARDRAIL (MANDATORY): read the AGE / LIFE-
   EXPECTANCY GUARDRAIL block in AVAILABLE INFORMATION above. If the
   bucket is VERY_LIMITED or LIMITED, the Assessment's recommendations
   for PSA surveillance / mpMRI / biopsy MUST be conditioned on life
   expectancy and patient preference per the AUA language quoted in
   that block. Generic "per AUA, continue annual PSA / consider mpMRI"
   is FORBIDDEN in those buckets. The Plan agent will receive the same
   guardrail and will not write a workup the Assessment did not endorse.
8. SURVEILLANCE STATUS (for cancer patients):
   - Note the current surveillance status (e.g., "no evidence of disease on surveillance cystoscopies")
   - Mention the surveillance schedule if transitioning (e.g., "has now transitioned to q6 month surveillance")
   - Reference the most recent surveillance procedure and its findings
   - Note upcoming scheduled procedures if mentioned in the HPI
9. PRIMARY-FIRST FRAMING (MANDATORY): Lead the Assessment with the patient's
   ACTIVE PRIMARY problem — the cancer or the documented reason for THIS visit —
   never an incidental finding. An incidental adrenal nodule or simple cyst is a
   secondary clause at most, never the opening subject when a cancer is present.
   Address EVERY active problem / every cancer the patient has (a patient may
   have more than one cancer).
10. BENIGN INCIDENTALS (MANDATORY): A finding the radiology characterizes as
    BENIGN — adrenal myelolipoma, lipid-rich / washout adrenal adenoma, simple
    (Bosniak I/II) renal cyst — requires NO routine imaging follow-up if it is
    biochemically inactive. Do NOT recommend repeat/dedicated imaging,
    surveillance, or monitoring for such a benign lesion; state it is benign and
    needs no further follow-up. NEVER call a radiology-benign lesion "of
    uncertain significance".
11. NO TECHNICAL METADATA: Never put scanner/technical artifacts into the prose
    — phantom size, kVp/mAs, reconstruction/kernel params, CPT or procedure
    codes, raw reference-range numbers. Report only clinical findings.

{calculator_instructions}
TEMPORAL AWARENESS (MANDATORY for followup visits):
If VISIT PROGRESSION data is provided, read it FIRST and follow these rules STRICTLY:

1. COMPLETED PROCEDURES - If pathology results exist for a procedure:
   - The procedure IS DONE - DO NOT say it is "scheduled" or "pending"
   - Discuss the RESULTS: "biopsy revealed Gleason 4+3=7 adenocarcinoma" NOT "biopsy is planned"
   - The clinical question has MOVED ON to the next decision point

2. COMPLETED STAGING - If imaging (PSMA PET, CT, bone scan) is complete:
   - Staging IS DONE - report the findings: "PSMA PET shows disease confined to prostate" or "metastatic disease"
   - Do NOT say staging is "pending" if results are in the data

3. PATIENT DECISIONS - If patient declined a treatment:
   - ACKNOWLEDGE this: "patient declined brachytherapy"
   - Do NOT recommend what the patient already declined
   - Discuss ALTERNATIVE options

4. CLINICAL REASONING SEQUENCE:
   - Prior visit: "recommended biopsy" → Current: biopsy DONE → NOW discuss staging/treatment
   - Prior visit: "recommended staging" → Current: staging DONE → NOW discuss treatment options
   - Prior visit: "offered radiation" → Patient declined → NOW discuss ADT or other alternatives

EXAMPLE CORRECT ASSESSMENT (biopsy completed, patient declined radiation):
"Mr. X returns to discuss treatment options for his prostate cancer. He has completed his staging workup with MRI-guided prostate biopsy (Oct 2025) showing Gleason 4+3=7 Grade Group 3 adenocarcinoma in 7 of 13 cores with perineural invasion, and PSMA PET (Dec 2025) demonstrating disease confined to the prostate with EANM score 4. He was evaluated by radiation oncology and offered brachytherapy but declined further radiation therapy. Given he is not a surgical candidate due to extensive prior abdominal surgeries and has declined radiation, the discussion today focuses on systemic therapy options including androgen deprivation therapy."

EXAMPLE WRONG ASSESSMENT (ignoring completed procedures):
"Mr. X has elevated PSA and will undergo prostate biopsy for staging..." - WRONG if biopsy already done

CROSS-SPECIALTY INTEGRATION:
- If CROSS-SPECIALTY UROLOGIC FINDINGS are provided, integrate relevant findings into the clinical picture
- Hospital admissions (urosepsis, hematuria) - note the episode and its resolution/impact
- Oncology coordination (ADT requests, chemotherapy) - note current oncologic management
- Cancelled procedures - note and factor into clinical status
- Recent clearances - acknowledge if relevant to pending procedures
- ONLY integrate urologically-relevant cross-specialty content

PRIOR A&P CONTEXT INTEGRATION (when PRIOR ASSESSMENT & PLAN CONTEXT provided):
- This section contains STRUCTURED information about clinical progression
- COMPLETED PROCEDURES: These are DONE - discuss results, not schedule them
- PATIENT DECLINED: Patient has refused these treatments - do NOT recommend them again
- OUTSTANDING ISSUES: These still need to be addressed - focus assessment on these
- CLINICAL PROGRESSION: Use this narrative to frame the current visit
- Example: If prior A&P shows "patient declined radiation", your assessment should acknowledge this and discuss alternatives

DATA INTEGRITY:
- Use ONLY values that appear in the Stage 1 note
- PSA < 4.0 ng/mL is NORMAL - do not call it "elevated"
- Do NOT invent or hallucinate any numeric values

OUTPUT REQUIREMENTS:
- Provide ONLY the assessment narrative (4-8 sentences)
- NO meta-commentary, preamble, or explanations
- Just the clean, clinical assessment text
- AFFIRMATIVE ONLY: state what IS true and what WILL be done. Do NOT include
  recommendations against inapplicable tests ("PSMA PET is not indicated as the
  PSA is undetectable"), hypothetical contingencies ("should he fail to void,
  surgical options could be explored"), or patronizing/tautological rationale
  ("...as the prostate has been removed"). Omit the inapplicable rather than
  explaining why it doesn't apply. (A guideline-grounded deferral with real
  weight — e.g. deferring screening for limited life expectancy — may be stated
  once, concisely.)

The assessment should read as a coherent clinical impression that demonstrates awareness of this specific patient's presentation and history.
"""

    # Call LLM with task-specific configuration
    # task_config takes precedence - uses provider/model/temperature from user settings
    # Falls back to model parameter if task_config not provided (backwards compatibility)
    synthesized_assessment = synthesize_with_llm(
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
        r'AUTHOR:.*'
    ]

    for pattern_str in va_metadata_patterns:
        synthesized_assessment = re.sub(pattern_str, '', synthesized_assessment, flags=re.IGNORECASE | re.MULTILINE)

    # Clean any LLM meta-commentary
    synthesized_assessment = clean_llm_commentary(synthesized_assessment)

    # CRITICAL: Validate PSA values against actual PSA CURVE data
    # This prevents hallucinated PSA values (e.g., 5.8 instead of 0.58)
    if stage1_note:
        valid_psa_values = _extract_valid_psa_values(stage1_note)
        if valid_psa_values:
            synthesized_assessment = _validate_psa_values_in_text(
                synthesized_assessment, valid_psa_values
            )

    # POST-PROCESSING: Fix common LLM typos
    typo_corrections = {
        'CONTRVEST': 'CONTRAST',
        'CONTREST': 'CONTRAST',
        'CONTRST': 'CONTRAST',
        'IV CONTRVEST': 'IV CONTRAST',
    }
    for typo, correction in typo_corrections.items():
        synthesized_assessment = synthesized_assessment.replace(typo, correction)

    return synthesized_assessment.strip()
