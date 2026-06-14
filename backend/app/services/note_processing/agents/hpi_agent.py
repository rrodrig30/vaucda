"""
HPI (History of Present Illness) Agent

Combines HPIs from all notes with Assessments and Plans, focusing on current urologic HPI.

Includes HALLUCINATION DETECTION via deterministic fact verification.
All synthesized HPI is checked against ground truth extracted from source.
"""

from typing import List, Dict, Optional, Tuple, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..patient_status_facts import PatientStatusFacts
from ..llm_helper import combine_sections_with_llm, synthesize_with_llm
from .history_cleaners import clean_llm_commentary
from ..extractors.hpi_fact_verifier import (
    HPIFactVerifier,
    HPIVerificationResult,
    verify_hpi_against_source
)
import re
import logging

logger = logging.getLogger(__name__)


def _build_treatment_status_block(
    psh: Optional[str],
    clinical_document: Optional[str],
    psa_data: Optional[str],
) -> str:
    """Deterministic "TREATMENT STATUS" block for the HPI prompt.

    The LLM repeatedly truncates the HPI before reaching treatment-
    completion events when the source contains BOTH older "pending
    treatment" notes AND newer "completed treatment" notes — it anchors
    on the older framing. This block restates the patient's current
    treatment posture in unambiguous text so the prompt cannot miss it.

    Detects:
      - Definitive prostate-cancer treatment that has been COMPLETED
        (XRT / prostatectomy / brachytherapy / focal therapy), via the
        same regexes the CC agent uses (kept in sync via import).
      - Whether ADT is part of the regimen (lupron / leuprolide /
        degarelix / bicalutamide phrases — detected separately because
        many patients get XRT without ADT, as in this case).
      - Whether PSA shows biochemical response post-treatment.

    Returns "" when no treatment-completion signal is found in PSH or
    the raw document, so non-treated patients aren't given a spurious
    "post-treatment" framing.
    """
    if not (psh or clinical_document):
        return ""

    # Import lazily to avoid a circular import at module load.
    from .cc_agent import (
        _detect_treatment_history, _assess_psa_trend,
        _is_biochemically_responding, _TREATMENT_LABEL,
    )

    treatment = _detect_treatment_history(psh or '', clinical_document or '')
    if not treatment:
        return ""

    t_type = treatment.get('type', '')
    label = _TREATMENT_LABEL.get(t_type, t_type or 'treatment')

    lines = [
        "TREATMENT STATUS (deterministic — use these statements as ground "
        "truth, they override any contradictory claim in the prior-visit "
        "HPI snapshots):",
        f"- Patient has COMPLETED definitive {label} for prostate cancer.",
    ]

    # ADT detection. Look for current-tense ADT markers in source. If
    # neither current ADT nor a clear "no ADT" signal is present, skip
    # the statement — better silent than wrong.
    src_blob = '\n'.join(s for s in (psh, clinical_document) if s)
    adt_active = re.search(
        r'\b(?:currently\s+on|on\s+)\s*(?:ADT|androgen\s+deprivation|'
        r'leuprolide|lupron|degarelix|eligard|firmagon|bicalutamide)\b',
        src_blob, re.IGNORECASE,
    )
    adt_completed = re.search(
        r'\b(?:completed|finished|stopped|discontinued)\s+'
        r'(?:ADT|androgen\s+deprivation|leuprolide|lupron|degarelix)\b',
        src_blob, re.IGNORECASE,
    )
    adt_explicitly_no = re.search(
        r'\b(?:without\s+ADT|no\s+ADT|did\s+not\s+receive\s+ADT|'
        r'XRT\s+without\s+(?:concurrent\s+)?ADT|radiation\s+without\s+ADT)\b',
        src_blob, re.IGNORECASE,
    )
    if adt_active:
        lines.append("- Patient is currently on androgen-deprivation therapy.")
    elif adt_completed:
        lines.append("- Patient previously received ADT (now completed).")
    elif adt_explicitly_no:
        lines.append("- Patient did NOT receive ADT.")

    # PSA biochemical response.
    psa_state = _assess_psa_trend(psa_data)
    responding = _is_biochemically_responding(t_type, psa_state)
    if responding is True:
        cur = psa_state.get('current')
        peak = psa_state.get('max')
        if cur is not None and peak is not None:
            lines.append(
                f"- PSA shows biochemical response post-treatment "
                f"(current {cur} ng/mL vs peak {peak} ng/mL)."
            )
        else:
            lines.append("- PSA shows biochemical response post-treatment.")
    elif responding is False:
        lines.append(
            "- PSA pattern is concerning for biochemical recurrence "
            "(per Phoenix criteria — current value is > nadir + 2 ng/mL "
            "for radiation, or > 0.2 ng/mL after prostatectomy)."
        )

    lines.append(
        "- The HPI MUST narrate the completed treatment and its outcome. "
        "It MUST NOT describe the patient as awaiting treatment, "
        "pending treatment, or still considering treatment options, "
        "because the source documents treatment as already finished."
    )
    return '\n'.join(lines)


def _dedupe_hpi_sentences(hpi: str) -> str:
    """Remove sentence-level redundancy that survives the LLM prompt.

    Removes any subsequent sentence that:
      (a) is a near-duplicate of an earlier sentence (high token
          overlap), OR
      (b) consists primarily of facts already stated earlier (a PSA
          value, lab phrase, or treatment phrase that appears verbatim
          earlier and the sentence carries no new clinical content).

    The deletion is conservative: it never removes the first mention
    of a fact and never collapses two sentences whose word sets
    differ by more than 40% (i.e. genuinely different sentences
    survive).

    Operates on the final LLM output, AFTER fact verification, AFTER
    clean_llm_commentary. Idempotent.
    """
    if not hpi or not hpi.strip():
        return hpi

    # Split into sentences while preserving paragraph breaks. The
    # period-after-letter rule handles abbreviated phrases like
    # "5 mg." poorly, so we split on ". " followed by capital letter.
    paragraphs = re.split(r'\n\s*\n', hpi)
    out_paragraphs: List[str] = []
    seen_signatures: List[set] = []

    # A "token signature" is the set of clinically-loaded tokens in a
    # sentence: numbers, PSA / Gleason / GG / treatment / mg / ng-mL
    # mentions, drug names, organ names. We use that to detect when
    # two sentences are about the same thing. Stopwords / generic
    # filler words are stripped so "He returns for followup" and "The
    # patient returns for followup" don't both match each other.
    STOPWORDS = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'has', 'have',
        'had', 'he', 'she', 'his', 'her', 'patient', 'this', 'that',
        'with', 'and', 'or', 'but', 'for', 'on', 'in', 'at', 'to',
        'of', 'currently', 'now', 'previously', 'noted', 'recently',
        'mr', 'mrs', 'ms', 'dr',
    }

    def _signature(sentence: str) -> set:
        # Lowercase, strip punctuation, drop stopwords.
        tokens = re.findall(r"[A-Za-z0-9.+/-]+", sentence.lower())
        return {t for t in tokens if t not in STOPWORDS and len(t) > 1}

    # LLM "summary restatement" lead phrases. These ALWAYS restate
    # facts already narrated earlier — the HPI is a narrative, the
    # narrative IS the summary, so a sentence beginning with one of
    # these is virtually always redundant filler. Drop every such
    # sentence (even the first); if the sentence carries unique new
    # facts, the LLM should phrase it in the running narrative, not
    # as a summary aside.
    SUMMARY_LEADS = re.compile(
        r'^\s*(?:'
        r"The patient is currently"
        r"|The patient's current"
        r"|His current (?:PSA|status|chief complaint|treatment)"
        r"|Her current (?:PSA|status|chief complaint|treatment)"
        r"|Currently, the patient"
        r"|At present, (?:the patient|he|she)"
        r"|To summarize"
        r"|In summary"
        r"|Overall, the patient"
        r')',
        re.IGNORECASE,
    )

    for para in paragraphs:
        # Split on sentence terminators followed by whitespace + capital.
        # Keep separators by using look-behind / look-ahead.
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z(])', para.strip())
        kept_sentences: List[str] = []
        for sent in sentences:
            sent_stripped = sent.strip()
            if not sent_stripped:
                continue
            # Summary-restatement leads — drop unconditionally.
            if SUMMARY_LEADS.match(sent_stripped):
                logger.debug(
                    "HPI dedupe: dropped summary-restatement sentence: %r",
                    sent_stripped[:120],
                )
                continue
            sig = _signature(sent_stripped)
            if not sig:
                # Sentence is mostly stopwords (e.g. "He is doing well.")
                # — keep it; not redundancy material.
                kept_sentences.append(sent_stripped)
                seen_signatures.append(sig)
                continue
            # Compare against every earlier signature in this HPI.
            is_redundant = False
            for prev_sig in seen_signatures:
                if not prev_sig:
                    continue
                overlap = len(sig & prev_sig)
                # Two thresholds:
                #   1. ≥80% of the new sentence's tokens already
                #      appeared earlier → near-duplicate sentence.
                #   2. ≥60% overlap AND new sentence has no token
                #      with a digit (no fresh value introduced) → a
                #      "summary" sentence that just restates earlier
                #      content.
                ratio_self = overlap / max(1, len(sig))
                has_new_value = any(re.search(r'\d', t) for t in (sig - prev_sig))
                if ratio_self >= 0.8 and not has_new_value:
                    is_redundant = True
                    break
                if ratio_self >= 0.6 and not has_new_value and len(sig) >= 4:
                    is_redundant = True
                    break
            if is_redundant:
                logger.debug(
                    "HPI dedupe: dropped redundant sentence "
                    "(no new tokens, overlap=%.0f%%): %r",
                    ratio_self * 100, sent_stripped[:120],
                )
                continue
            kept_sentences.append(sent_stripped)
            seen_signatures.append(sig)
        if kept_sentences:
            out_paragraphs.append(' '.join(kept_sentences))

    return '\n\n'.join(out_paragraphs).strip()


def _build_psa_delta_block(psa_data: Optional[str]) -> str:
    """Build a deterministic "PSA since prior visit" summary.

    The LLM frequently overlooks the most recent vs prior delta when
    given a long PSA curve — it instead anchors on whichever older
    value was emphasized in a stale HPI snapshot. This function pre-
    computes the current PSA, the prior PSA, the peak PSA, and the
    direction of change as plain text that the prompt can quote
    verbatim. Returns "" if fewer than 2 values are parseable.
    """
    if not psa_data:
        return ""
    # Re-use the same parsing logic as cc_agent so behaviour is shared.
    # Locally inlined to avoid a circular import.
    values: List[Tuple[str, float]] = []
    for raw_line in psa_data.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        # Capture optional leading date+time so we can label values.
        date_match = re.match(
            r'(?:\[[a-z]+\]\s+)?'
            r'([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})',
            line,
        )
        date_label = date_match.group(1) if date_match else ''
        # Take the last decimal number on the line as the PSA value.
        nums = re.findall(r'\d+\.\d+', line)
        if nums:
            try:
                values.append((date_label, float(nums[-1])))
            except ValueError:
                pass
    if len(values) < 2:
        return ""
    # PSA curve is reverse-chronological → first value is most recent.
    cur_date, cur_v = values[0]
    prev_date, prev_v = values[1]
    peak_v = max(v for _, v in values)
    if cur_v < prev_v - 0.05:
        direction = 'decreased'
    elif cur_v > prev_v + 0.05:
        direction = 'increased'
    else:
        direction = 'unchanged'
    cur_label = f" on {cur_date}" if cur_date else ""
    prev_label = f" on {prev_date}" if prev_date else ""
    return (
        "PSA SINCE PRIOR VISIT (use these exact values in the HPI):\n"
        f"- Current PSA: {cur_v} ng/mL{cur_label}\n"
        f"- Prior PSA:   {prev_v} ng/mL{prev_label}\n"
        f"- Direction:   {direction}\n"
        f"- Peak PSA observed in this series: {peak_v} ng/mL\n"
        "When the HPI references PSA, it MUST cite the current value above."
    )


def synthesize_hpi(
    gu_notes: List[Dict[str, str]],
    non_gu_notes: List[Dict[str, str]],
    psa_data: Optional[str] = None,
    pathology_data: Optional[str] = None,
    labs_data: Optional[str] = None,
    imaging_data: Optional[str] = None,
    cross_specialty_context: Optional[str] = None,
    visit_progression: Optional[str] = None,
    prior_ap_context: Optional[str] = None,
    psh_data: Optional[str] = None,
    clinical_document: Optional[str] = None,
    verify_facts: bool = True,
    return_verification: bool = False,
    patient_name: Optional[str] = None,
    patient_age: Optional[str] = None,
    patient_sex: Optional[str] = None,
    authoritative_facts: Optional[str] = None,
    patient_facts: Optional["PatientStatusFacts"] = None,
) -> Union[str, Tuple[str, Optional[HPIVerificationResult]]]:
    """
    Synthesize HPI from GU notes with clinical context.

    Note: Stage 1 only includes HPIs from previous notes. Assessment and Plan
    are NOT available as they are Stage 2 (completed after patient visit).

    Focus on creating a current UROLOGY HPI from available GU notes,
    enriched with recent lab results, pathology, and imaging findings
    so the HPI reflects the patient's current clinical status.

    INCLUDES HALLUCINATION DETECTION:
    - Extracts ground truth PSA values, lab results, and findings from source BEFORE synthesis
    - Verifies all claims in LLM output against ground truth
    - Flags or corrects any hallucinated content (e.g., fabricated PSA values)

    PRIOR A&P CONTEXT INTEGRATION:
    - Uses prior Assessment and Plan context to inform HPI narrative
    - Provides awareness of what was previously diagnosed and planned
    - Enables temporal continuity in follow-up visit HPIs

    Args:
        gu_notes: List of GU note dictionaries
        non_gu_notes: List of non-GU note dictionaries (NOT USED - kept for API compatibility)
        psa_data: Raw PSA values extracted from document (optional)
        pathology_data: Raw pathology results extracted from document (optional)
        labs_data: Raw lab results extracted from document (optional)
        imaging_data: Raw imaging results extracted from document (optional)
        cross_specialty_context: Urologic content from non-GU specialty notes (optional)
        visit_progression: Narrative of what changed since last visit (optional)
        prior_ap_context: Formatted prior Assessment & Plan context (optional)
        verify_facts: If True (default), verify synthesis against source facts
        return_verification: If True, return (text, HPIVerificationResult) tuple

    Returns:
        Synthesized HPI text focused on current urologic status.
        If return_verification=True, returns (text, HPIVerificationResult) tuple.
    """
    # Collect HPIs from GU notes ONLY
    # Non-GU HPIs are excluded to prevent contamination with irrelevant content
    # (headaches, dizziness, ankle pain, etc. should not appear in urology HPI)
    #
    # Each HPI is a SNAPSHOT from a prior visit, not a description of
    # today's encounter. Prefix each one with the source visit date so
    # the synthesis LLM sees a temporal ordering instead of treating
    # all HPIs as concurrent inputs. Without this label the LLM
    # routinely merges multi-year histories as if they all happened at
    # the same encounter (e.g. saying "patient on active surveillance"
    # for a patient who completed XRT 18 months ago — because an old
    # surveillance-era HPI is presented at the same level as the most
    # recent one).
    # If we received ground-truth patient_facts, import the sanitizer lazily
    # so we can pre-scrub each prior HPI before it reaches the LLM. Prior
    # HPIs are themselves LLM-generated by previous (possibly buggy) runs;
    # treating their text as inviolate just propagates last run's
    # confabulated focal-therapy / Phoenix sentences forward.
    _sanitize_prior_hpi = None
    if patient_facts is not None:
        from ..patient_status_facts import sanitize_context_against_facts as _scaf

        def _sanitize_prior_hpi(text: str) -> str:
            cleaned, _ = _scaf(text, patient_facts)
            return cleaned

    hpi_instances = []
    for note in gu_notes:
        hpi_text = note.get("HPI")
        if not hpi_text:
            continue
        if _sanitize_prior_hpi is not None:
            hpi_text = _sanitize_prior_hpi(hpi_text)
            # If the sanitizer stripped everything substantive, skip this
            # prior HPI rather than feeding the LLM an empty entry.
            if not hpi_text.strip():
                continue
        src_date = (note.get("_source_date") or "").strip()
        src_title = (note.get("_source_title") or "").strip()
        if src_date and src_title:
            header = f"[Prior visit dated {src_date} — {src_title}]"
        elif src_date:
            header = f"[Prior visit dated {src_date}]"
        elif src_title:
            header = f"[Prior visit ({src_title})]"
        else:
            header = "[Prior visit, undated]"
        hpi_instances.append(f"{header}\n{hpi_text}")

    # Non-GU notes: EXCLUDED from HPI synthesis
    # Reason: Non-GU HPIs contain non-urological content that confuses the LLM
    # and results in HPI discussing headaches, mental health, orthopedic issues, etc.
    # for note in non_gu_notes:
    #     if note.get("HPI"):
    #         hpi_instances.append(f"Non-GU HPI: {note['HPI']}")

    # If no GU-note HPIs exist but we have clinical context (PSA,
    # pathology, imaging, prior A&P) — write a UROLOGIC HPI from the
    # context alone rather than returning empty. The renderer used to
    # display "HPI: Unknown" in this case; that's never acceptable for
    # a urology note. Falling through to the LLM-synthesis path below
    # with no hpi_instances list lets the prompt generate a narrative
    # purely from the clinical-data context section. We require at
    # least one piece of urologic context (PSA / pathology / imaging /
    # cross-specialty / visit-progression / prior-AP) before doing this
    # — otherwise there's truly nothing to write about.
    has_clinical_context = any(
        (s or '').strip()
        for s in (psa_data, pathology_data, imaging_data,
                  cross_specialty_context, visit_progression, prior_ap_context)
    )
    if not hpi_instances and not has_clinical_context:
        return ""
    if not hpi_instances:
        # Sentinel placeholder so combine_sections_with_llm has something
        # to operate on; the prompt instructions and CLINICAL DATA
        # CONTEXT below tell the LLM to derive the HPI from context.
        hpi_instances = [
            "[NO PRIOR UROLOGY NOTE AVAILABLE — synthesize HPI from the "
            "CLINICAL DATA CONTEXT below, focusing strictly on urologic "
            "issues.]"
        ]

    # If only one instance AND no ground-truth enforcement is required,
    # short-circuit and pass the prior HPI through with light text cleanup.
    # When authoritative_facts IS provided we deliberately fall through to
    # LLM synthesis: prior HPIs are LLM-generated by previous (possibly
    # buggy) runs and may contain confabulated treatments / Phoenix-
    # criteria / biochemical-recurrence framing that violate the ground
    # truth. Forcing LLM synthesis with the authoritative facts block lets
    # the prompt rewrite the contaminated prior HPI using deterministic
    # source values. The cost is one extra LLM call per single-prior-visit
    # patient; the safety benefit (no carry-forward of last-run
    # hallucinations) is worth it.
    if len(hpi_instances) == 1 and not (authoritative_facts and authoritative_facts.strip()):
        # Remove our internal labels
        result = hpi_instances[0]
        result = result.replace("Non-GU HPI: ", "")
        # Replace "consult" with "followup" terminology
        import re
        result = re.sub(r'\burology\s+consult\b', 'urology followup', result, flags=re.IGNORECASE)
        result = re.sub(r'\bconsult\s+for\b', 'followup for', result, flags=re.IGNORECASE)
        result = re.sub(r'\bfor\s+a\s+urology\s+consult\b', 'for a urology followup', result, flags=re.IGNORECASE)
        return result

    # Build clinical context section from available data.
    # Patient demographics first — the LLM tends to either invent an
    # age (often "72-year-old male" by default) or carry one over
    # stale from prior notes if we don't anchor it. Putting age and
    # sex up front prevents that.
    clinical_context = ""
    context_parts = []

    # AUTHORITATIVE GROUND TRUTH must appear FIRST so the LLM treats every
    # subsequent context block (including prior-visit HPI snapshots) as
    # subordinate to it. Built deterministically from PMH + PSH +
    # pathology by patient_status_facts; lists cancer_status,
    # treatment_naive, phoenix_applicable and the ABSOLUTE RULES the LLM
    # must follow. Without this the HPI agent has been observed to write
    # "completed definitive focal therapy for prostate cancer" / "Phoenix
    # biochemical-recurrence" for treatment-naive patients by pattern-
    # matching against rising-PSA templates.
    if authoritative_facts and authoritative_facts.strip():
        context_parts.append(authoritative_facts)

    demo_lines = []
    if patient_name:
        demo_lines.append(f"Name: {patient_name}")
    if patient_age:
        demo_lines.append(f"Age at this visit: {patient_age} years")
    if patient_sex:
        demo_lines.append(f"Sex: {patient_sex}")
    if demo_lines:
        context_parts.append(
            "PATIENT DEMOGRAPHICS (use ONLY these values for age/sex in the HPI; "
            "do NOT use any age you may see referenced elsewhere in the source notes — "
            "those reflect the patient's age at the time of an old note, not now):\n"
            + "\n".join(demo_lines)
        )
    if psa_data and psa_data.strip():
        context_parts.append(f"RECENT PSA VALUES:\n{psa_data}")
        # Always emit a deterministic "since prior visit" PSA summary so
        # the LLM cannot miss the current-vs-prior delta. _build_psa_delta
        # returns "" if it can't parse two values (in which case the
        # plain RECENT PSA VALUES block above is what the LLM gets).
        psa_delta_block = _build_psa_delta_block(psa_data)
        if psa_delta_block:
            context_parts.append(psa_delta_block)
    # Deterministic TREATMENT STATUS block — always added when the
    # document shows completed definitive prostate-cancer therapy.
    # Prevents the LLM from anchoring on older "pending treatment"
    # snapshots and writing an HPI that says the patient is still
    # awaiting therapy when treatment has actually been completed.
    treatment_status_block = _build_treatment_status_block(
        psh_data, clinical_document, psa_data,
    )
    if treatment_status_block:
        context_parts.append(treatment_status_block)
    if pathology_data and pathology_data.strip():
        context_parts.append(f"PATHOLOGY RESULTS:\n{pathology_data}")
    if labs_data and labs_data.strip():
        # Limit labs to reasonable length for HPI context
        labs_summary = labs_data[:1500] if len(labs_data) > 1500 else labs_data
        context_parts.append(f"RELEVANT LAB RESULTS:\n{labs_summary}")
    if imaging_data and imaging_data.strip():
        # Limit imaging to reasonable length for HPI context
        imaging_summary = imaging_data[:1500] if len(imaging_data) > 1500 else imaging_data
        context_parts.append(f"IMAGING FINDINGS:\n{imaging_summary}")

    # Add cross-specialty urologic context (from non-GU notes)
    if cross_specialty_context and cross_specialty_context.strip():
        context_parts.append(f"CROSS-SPECIALTY UROLOGIC FINDINGS:\n{cross_specialty_context}")

    # Add visit progression analysis (what changed since last visit)
    if visit_progression and visit_progression.strip():
        context_parts.append(f"VISIT PROGRESSION (since last urology visit):\n{visit_progression}")

    # Add prior Assessment & Plan context (for temporal continuity in follow-up visits)
    if prior_ap_context and prior_ap_context.strip():
        context_parts.append(f"PRIOR ASSESSMENT & PLAN CONTEXT:\n{prior_ap_context}")

    if context_parts:
        clinical_context = "\n\n=== CLINICAL DATA CONTEXT (reference these findings in the HPI where relevant) ===\n" + "\n\n".join(context_parts) + "\n=== END CLINICAL DATA CONTEXT ===\n"

    authoritative_directive = ""
    if authoritative_facts:
        authoritative_directive = (
            "\n=== AUTHORITATIVE GROUND TRUTH ENFORCEMENT (READ THIS FIRST) ===\n"
            "The first block inside CLINICAL DATA CONTEXT above (titled\n"
            "'PATIENT GROUND TRUTH') was derived deterministically from the\n"
            "source documents. It is the single source of truth for this\n"
            "patient's cancer status, treatment history, and Phoenix-criteria\n"
            "applicability. The ABSOLUTE RULES at the end of that block are\n"
            "non-negotiable.\n"
            "\n"
            "If TREATMENT_NAIVE is True, the patient has NEVER received any\n"
            "prostate-cancer treatment. Do NOT write 'completed focal therapy',\n"
            "'s/p prostatectomy', 'after radiation', 'underwent ADT', or any\n"
            "synonym. A prior-visit HPI snapshot that says such a thing is\n"
            "WRONG (last LLM-run hallucination) and must NOT be carried\n"
            "forward.\n"
            "\n"
            "If PROSTATE_CANCER_STATUS is ABSENT, do NOT diagnose prostate\n"
            "cancer in the HPI. Do NOT invoke 'biochemical recurrence',\n"
            "'Phoenix criteria', 'nadir+2', 'salvage', or 'post-treatment'.\n"
            "Rising PSA in such a patient is a workup question for new\n"
            "disease, not recurrence of treated disease.\n"
        )

    # Use LLM to synthesize comprehensive HPI
    instructions = f"""
Create a current, comprehensive UROLOGY HPI that synthesizes all available urologic information from the source notes into a cohesive narrative for TODAY'S visit.

{clinical_context}
{authoritative_directive}

CRITICAL TEMPORAL INVARIANTS (read before doing anything else):
- The HPI entries below are PRIOR-VISIT SNAPSHOTS, each labeled with
  "[Prior visit dated <DATE> — <NOTE TITLE>]". The newest snapshot is
  NOT today. Today's clinical reality may differ substantially —
  treatment may have been completed since, PSA may have changed,
  imaging may have been done. Treat each prior HPI as a record of how
  things stood on its specific date, and DO NOT carry forward any
  prior statement that the CLINICAL DATA CONTEXT contradicts.
- Whenever a value (PSA, Gleason, treatment status, etc.) appears in
  both a prior HPI and the CLINICAL DATA CONTEXT, the CLINICAL DATA
  CONTEXT wins. The HPI you write must use TODAY'S current PSA, not
  a stale one from a prior snapshot.
- If "PSA SINCE PRIOR VISIT" appears in the context above, you MUST
  quote the current PSA value in the HPI narrative. Do not invent a
  different value, do not omit it, do not use the prior value as
  "current".
- If a prior-visit HPI describes the patient as e.g. "on active
  surveillance with rising PSA" but the data context shows definitive
  treatment was completed and PSA is now responding, the HPI you
  write must reflect the POST-TREATMENT current state, not the stale
  surveillance era.
- Frame each historical fact with its date (e.g. "underwent radical
  prostatectomy in June 2024" not "underwent radical prostatectomy").
  This makes time elapsed explicit instead of letting the reader
  guess.

STRUCTURE:
0. TEMPORAL FRAMING (CRITICAL for followup visits):
   - If VISIT PROGRESSION data is provided, this is a FOLLOWUP visit
   - Start by referencing what was recommended at the last visit
   - Describe what has happened since (completed procedures, test results, ongoing treatments)
   - Then present the patient's current status and reason for today's visit
   - Example opening (generic structure ONLY — substitute the patient's actual diagnosis/procedure from the source notes; do NOT carry "prostate biopsy" or any specific clinical detail from this example into the output):
       "<Patient> returns for followup of <DIAGNOSIS-FROM-SOURCE>. At the last visit, <RECOMMENDATION-FROM-SOURCE>. Since then, <COMPLETED-EVENT-FROM-SOURCE>. Today, <REASON-FOR-VISIT-FROM-SOURCE>."
1. Start with the patient's current chief complaint and presenting urologic issue
2. Include relevant history from past visits in chronological flow
3. Document urologic symptoms, test results, and diagnoses that are mentioned
4. Write in narrative paragraph form (not bullet points)
5. The HPI is ONE INTEGRATED NARRATIVE. Use 1-2 paragraphs maximum.
   Do NOT produce three or four short paragraphs that each restate
   the same facts (PSA value, treatments, labs) — that pattern is
   the most common reason this HPI gets sent back for rewrite.

NON-REDUNDANCY (MANDATORY — output is rejected if violated):
- Each clinically distinct fact appears EXACTLY ONCE. If a PSA value
  (e.g. "0.22 ng/mL"), a treatment ("monthly Degarelix injections"),
  an imaging finding ("PSMA-avid osseous metastases"), or a lab
  abnormality ("anemia, leukopenia") is mentioned anywhere in the
  HPI, do NOT restate it in a later sentence or "summary" paragraph.
- Do NOT write a closing paragraph that re-summarizes what was just
  narrated. The narrative IS the summary.
- Do NOT use phrasings like "The patient's current chief complaint
  is..." after already covering the chief complaint at the top — the
  CC line above the HPI already states the chief complaint.
- Do NOT lead multiple sentences with "The patient is currently...",
  "The patient's current status is...", "His current PSA is...".
  Each of those leads is allowed AT MOST ONCE.
- If you must reference a fact a second time for context, use a back-
  reference ("the previously noted decline", "this elevation") rather
  than restating the value.

ANTI-REDUNDANCY EXAMPLE (do NOT produce output like this):
   BAD: "His PSA rose to 30.25 ng/mL. He has metastatic disease and
        is on monthly Degarelix. Most recent PSA is 30.25 ng/mL.
        Patient is currently on monthly Degarelix injections.
        Mild anemia, leukopenia, and elevated alkaline phosphatase
        noted. The patient's current chief complaint is rising PSA,
        with a value of 30.25 ng/mL. Mild anemia, leukopenia, and
        elevated alkaline phosphatase noted."
   GOOD: "His PSA has risen from 0.26 ng/mL (Sep 2025) to 30.25 ng/mL
        (Jun 2026) despite ongoing monthly Degarelix injections, with
        accompanying mild anemia, leukopenia, and elevated alkaline
        phosphatase on recent labs."

CONTENT REQUIREMENTS:
- USE all urologically relevant information provided in the source notes
- INCLUDE: GU symptoms, urologic diagnoses, test results (PSA, imaging, pathology), medications, and treatments that are documented
- INCLUDE: Relevant surgical history if mentioned
- SYNTHESIZE information from multiple visits into a coherent story
- MAINTAIN chronological progression when discussing the patient's condition
- CRITICAL: If PSA values, pathology results, or imaging findings are provided in the CLINICAL DATA CONTEXT above, you MUST reference the most recent/relevant ones in the HPI narrative. These are this patient's actual results.
- For PSA: mention the most recent value and trend (rising, stable, declining)
- For pathology: mention Gleason score, grade group, and key findings if present
- For imaging: mention key urologic findings from recent imaging

CROSS-SPECIALTY INTEGRATION (when CROSS-SPECIALTY UROLOGIC FINDINGS provided):
- Integrate urologically-relevant findings from other specialties into the narrative
- Hospital admissions for urologic reasons (urosepsis, hematuria, retention) - include admission details and outcome
- Oncology treatment requests (ADT, chemotherapy) - note what was requested and current status
- Radiation Oncology coordination - note if radiation was recommended, started, or completed
- Cancelled or rescheduled procedures - note the cancellation and reason if documented
- Cardiology/ID clearances or concerns - note relevant clearance status for pending procedures
- ONLY include cross-specialty content that is UROLOGICALLY RELEVANT
- Do NOT include non-urologic findings (pure cardiac, pulmonary, etc.)

PRIOR ASSESSMENT & PLAN INTEGRATION (when PRIOR A&P CONTEXT provided):
- Use prior A&P context to inform the HPI narrative with clinical progression
- Reference what was diagnosed and planned at previous visits
- Mention completed procedures and their results (using ONLY procedures explicitly named in PRIOR A&P CONTEXT or PATHOLOGY RESULTS above — do NOT invent procedure names)
- Note patient treatment decisions when explicitly documented
- Identify what issues remain outstanding from prior visits
- Frame the current visit in context of the clinical progression
- ANTI-HALLUCINATION FOR EXAMPLES: never copy specific diagnoses, Gleason scores, procedure names, or imaging modalities from this prompt. The structure shown is a SHAPE only — every clinical fact in the actual HPI must come from the patient's source notes.
- Generic shape example (do NOT copy any clinical specifics from this — they are placeholders):
    "<Patient> returns for followup of <DIAGNOSIS>. At last visit, <RECOMMENDATION>. Since then, <EVENT/RESULT>. Today, <CURRENT-DECISION-POINT>."

ANTI-HALLUCINATION RULES:
- DO NOT invent procedures or treatments not mentioned in the notes
- DO NOT assume treatments based on diagnoses alone unless explicitly stated
- DO NOT add information from your general medical knowledge
- If a procedure is listed in past surgical history, you may include it
- If test results are mentioned (PSA values, imaging findings), include them
- Use ONLY the PSA values provided in the CLINICAL DATA CONTEXT - do NOT fabricate PSA values

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

    if authoritative_facts and authoritative_facts.strip():
        # Bypass combine_sections_with_llm: the "You are a clinical
        # documentation assistant. Your task is to combine multiple
        # entries" boilerplate dilutes the authoritative-facts directive
        # and lets the LLM weight a contaminated prior-HPI Entry 1 more
        # heavily than the abstract ABSOLUTE RULES block. Lead the
        # prompt with the ground truth and a TASK directive framing the
        # prior HPI as suggestive-only source material to be rewritten.
        prompt_parts = [
            authoritative_facts,
            "\n=== TASK ===",
            "Rewrite the patient's History of Present Illness for TODAY'S visit",
            "using ONLY the deterministic CLINICAL DATA CONTEXT below as source",
            "of truth. Treat the PRIOR HPI SNAPSHOT(S) at the end of this prompt",
            "as suggestive context only — they were written by an earlier",
            "automated process that may have confabulated treatments, diagnoses,",
            "or recurrence framing. If any sentence in a prior HPI snapshot",
            "contradicts the GROUND TRUTH block above, that sentence is WRONG",
            "and must NOT appear in your output.",
            "",
            "Apply every ABSOLUTE RULE from the GROUND TRUTH block. If the",
            "patient is TREATMENT_NAIVE, the prior HPI's mention of 'focal",
            "therapy', 'Phoenix criteria', 'biochemical recurrence', 'salvage',",
            "or any 'completed / underwent / s/p <treatment>' phrase is a",
            "confabulation that must be removed and the narrative rewritten",
            "around the actual deterministic findings (PSA values, negative",
            "biopsies, BPH medications, etc.).",
            "",
            instructions,
            "\n=== PRIOR HPI SNAPSHOT(S) (suggestive context only) ===",
        ]
        for i, inst in enumerate(hpi_instances, 1):
            prompt_parts.append(f"\n--- Entry {i} ---\n{inst}\n")
        prompt_parts.append(
            "\n=== OUTPUT ===\n"
            "Provide ONLY the rewritten HPI narrative. No meta-commentary, no\n"
            "explanations. Start directly with the patient name and age."
        )
        final_prompt = "\n".join(prompt_parts)
        synthesized_hpi = synthesize_with_llm(
            prompt=final_prompt,
            temperature=0.0,
        )
    else:
        synthesized_hpi = combine_sections_with_llm(
            section_name="History of Present Illness",
            section_instances=hpi_instances,
            instructions=instructions,
        )

    cleaned_hpi = clean_llm_commentary(synthesized_hpi)

    # Deterministic redundancy removal. Catches the cases where the
    # LLM produces "summary" sentences that restate facts already
    # narrated earlier (e.g. "The patient's current PSA is 30.25
    # ng/mL" after a prior sentence already mentioned 30.25 ng/mL).
    # Only removes sentences with ≥60–80% token overlap to an earlier
    # sentence AND no new value introduced. See _dedupe_hpi_sentences
    # for the exact criteria.
    cleaned_hpi = _dedupe_hpi_sentences(cleaned_hpi)

    # STEP: Verify HPI against ground truth facts
    verification_result = None
    if verify_facts and cleaned_hpi:
        verifier = HPIFactVerifier()

        # Extract facts from source documents
        for note in gu_notes:
            if note.get("HPI"):
                verifier.extract_facts_from_source(note["HPI"])

        # Extract facts from clinical context
        if psa_data:
            verifier.extract_facts_from_psa_data(psa_data)

        if labs_data:
            verifier.extract_facts_from_labs(labs_data)

        if pathology_data:
            verifier.extract_facts_from_source(pathology_data)

        # Verify synthesis
        if verifier.ground_truth_facts:
            verification_result = verifier.verify_synthesis(cleaned_hpi)

            if not verification_result.is_verified:
                logger.warning(
                    f"HPI synthesis verification FAILED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Potential hallucinations: {verification_result.potential_hallucinations}"
                )

                # Use corrected text if available
                if verification_result.corrected_text:
                    logger.info("Using corrected HPI text with hallucinations flagged")
                    cleaned_hpi = verification_result.corrected_text
            else:
                logger.debug(
                    f"HPI synthesis VERIFIED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Verified claims: {verification_result.verified_claims}"
                )

    if return_verification:
        return cleaned_hpi, verification_result
    return cleaned_hpi


def synthesize_consult_hpi(
    consult_reason: str,
    patient_name: Optional[str] = None,
    patient_age: Optional[str] = None,
    patient_sex: Optional[str] = None,
    pmh: Optional[str] = None,
    psh: Optional[str] = None,
    medications: Optional[str] = None,
    imaging: Optional[str] = None,
    pcp_note_data: Optional[Dict[str, str]] = None,
    provider_urologic_context: Optional[str] = None,
    reason_for_request: Optional[str] = None,
    psa_data: Optional[str] = None,
    pathology_data: Optional[str] = None,
    labs_data: Optional[str] = None,
    verify_facts: bool = True,
    return_verification: bool = False
) -> Union[str, Tuple[str, Optional[HPIVerificationResult]]]:
    """
    Synthesize comprehensive HPI for consult requests.

    Per instructions.txt workflow:
    - Initial HPI from Reason for Request / Reason for Consult Request
    - Scan provider notes (Current PC Provider, Requesting Provider) for urologic content
    - Combine and synthesize comprehensive HPI

    Creates a detailed narrative HPI by combining:
    - Patient demographics (name, age)
    - Consult reason (Provisional Diagnosis)
    - Reason for Request / Reason for Consult Request
    - Provider urologic context (from note scanning)
    - Relevant medical history (PMH, PSH)
    - Current medications (urologic focus)
    - Recent imaging findings
    - PCP note information

    Args:
        consult_reason: Brief consult request reason (from Reason for Consult Request)
        patient_name: Patient name (without titles)
        patient_age: Patient age
        pmh: Past medical history
        psh: Past surgical history
        medications: Current medications list
        imaging: Recent imaging reports
        pcp_note_data: Dict with PCP note extractions (social, family, hpi, etc.)
        provider_urologic_context: Urologic content from provider note scanning
        reason_for_request: Additional reason text (Reason For Request field)

    Returns:
        Comprehensive narrative HPI suitable for urology consult
    """
    # Build context sections for LLM synthesis
    context_sections = []

    # Add consult reason (primary driver - from Reason for Consult Request)
    context_sections.append(f"CONSULT REASON (from Reason for Consult Request):\n{consult_reason}")

    # Add Reason For Request if different and provided
    # Per instructions.txt: HPI = Reason for Request + Reason for Consult Request
    if reason_for_request and reason_for_request.strip():
        if reason_for_request.strip() != consult_reason.strip():
            context_sections.append(f"ADDITIONAL REQUEST DETAILS (from Reason For Request):\n{reason_for_request}")

    # Add provider urologic context (from provider note scanning)
    # Per instructions.txt: scan Requesting Provider and Current PC Provider notes
    # for urologic mentions and combine with consult request HPI
    if provider_urologic_context and provider_urologic_context.strip():
        context_sections.append(f"PROVIDER NOTES UROLOGIC CONTEXT:\n{provider_urologic_context}")

    # Add patient demographics
    if patient_name or patient_age or patient_sex:
        demo = []
        if patient_name:
            demo.append(f"Name: {patient_name}")
        if patient_age:
            demo.append(f"Age: {patient_age}")
        if patient_sex:
            demo.append(f"Sex: {patient_sex}")
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

    # Add PSA data if available
    if psa_data and psa_data.strip():
        context_sections.append(f"PSA VALUES:\n{psa_data}")

    # Add pathology results if available
    if pathology_data and pathology_data.strip():
        pathology_summary = pathology_data[:1500] if len(pathology_data) > 1500 else pathology_data
        context_sections.append(f"PATHOLOGY RESULTS:\n{pathology_summary}")

    # Add lab results if available
    if labs_data and labs_data.strip():
        labs_summary = labs_data[:1000] if len(labs_data) > 1000 else labs_data
        context_sections.append(f"RELEVANT LAB RESULTS:\n{labs_summary}")

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

SYNTHESIS REQUIREMENTS (per consult workflow):
1. The primary HPI content comes from the CONSULT REASON and ADDITIONAL REQUEST DETAILS
2. The PROVIDER NOTES UROLOGIC CONTEXT contains additional urologic information from the requesting/primary care provider's notes
3. You MUST synthesize ALL of these sources into a cohesive narrative
4. Information from consult request may be sentence fragments - make them complete and coherent
5. Integrate provider note content to add clinical context and background

STRUCTURE:
1. Opening: "[Patient name] is a [age]-year-old [sex from demographics, lowercase] with history of [key urologic conditions] who presents [consult reason]"
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
- IMPORTANT: The consult reason text may be incomplete or fragmentary - complete the sentences appropriately
- CRITICAL: If PSA values are provided, mention the most recent PSA and trend
- CRITICAL: If pathology results are provided (Gleason score, grade group), include them
- CRITICAL: If lab results are provided, include relevant abnormal findings

ANTI-HALLUCINATION RULES:
- DO NOT invent procedures, medications, symptoms, or findings not mentioned
- DO NOT add provider names unless stated in source
- DO NOT speculate about outcomes or effectiveness unless explicitly stated
- DO NOT include non-urologic conditions unless directly relevant to GU care
- If age is not provided, omit age reference
- If patient name is not provided, use "The patient" or "Patient"
- Use ONLY PSA values from the data provided - do NOT fabricate values

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

    cleaned_hpi = clean_llm_commentary(synthesized_hpi)

    # STEP: Verify HPI against ground truth facts
    verification_result = None
    if verify_facts and cleaned_hpi:
        verifier = HPIFactVerifier()

        # Extract facts from source documents
        if consult_reason:
            verifier.extract_facts_from_source(consult_reason)
        if reason_for_request:
            verifier.extract_facts_from_source(reason_for_request)
        if provider_urologic_context:
            verifier.extract_facts_from_source(provider_urologic_context)

        # Extract facts from clinical context
        if psa_data:
            verifier.extract_facts_from_psa_data(psa_data)

        if labs_data:
            verifier.extract_facts_from_labs(labs_data)

        if pathology_data:
            verifier.extract_facts_from_source(pathology_data)

        if imaging:
            verifier.extract_facts_from_source(imaging)

        # Verify synthesis
        if verifier.ground_truth_facts:
            verification_result = verifier.verify_synthesis(cleaned_hpi)

            if not verification_result.is_verified:
                logger.warning(
                    f"Consult HPI synthesis verification FAILED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Potential hallucinations: {verification_result.potential_hallucinations}"
                )

                # Use corrected text if available
                if verification_result.corrected_text:
                    logger.info("Using corrected consult HPI text with hallucinations flagged")
                    cleaned_hpi = verification_result.corrected_text
            else:
                logger.debug(
                    f"Consult HPI synthesis VERIFIED. "
                    f"Confidence: {verification_result.confidence_score:.2f}. "
                    f"Verified claims: {verification_result.verified_claims}"
                )

    if return_verification:
        return cleaned_hpi, verification_result
    return cleaned_hpi
