"""
LLM prompt builder + lenient JSON parser for constrained HPI
generation.

The prompt:
  - Instructs the LLM to emit ONLY a JSON object matching the
    HPIDraft schema — no prose, no markdown, no commentary.
  - Embeds the schema's controlled vocabularies inline so the
    LLM knows the exact enum values.
  - Surfaces the deterministic ground truth (PSA Curve, PSH,
    PATHOLOGY, MEDICATIONS, banner) so the LLM has all the
    values it must reference.
  - When called as a retry, embeds the prior validation errors so
    the LLM can correct them precisely.

The parser:
  - Tolerates markdown code fences (```json ... ```)
  - Tolerates leading / trailing prose around the JSON object
  - Extracts the first balanced { ... } span and json.loads() it
  - Returns (draft, parse_error) — never raises
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from .hpi_fact_validator import FactValidationError, GroundTruth
from .hpi_schema import (
    PSA_DIRECTIONS,
    SEX_VALUES,
    TREATMENT_MODALITIES,
    TREATMENT_STATUSES,
    PROCEDURE_TYPES,
    VERIFIED_IN_SOURCES,
    VISIT_TYPES,
    ValidationError,
    UROLOGIC_MEDS,
)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

# Compact schema description embedded in the prompt. We do NOT dump
# the entire Python schema dict (too noisy for the LLM) — we hand-write
# a concise JSON-shape description with allowed enum values inline.

def _schema_block() -> str:
    return f"""\
Required output shape (HPIDraft JSON):

{{
  "intro": {{                                  // REQUIRED
    "name": "<full name from banner>",         // REQUIRED string
    "age": <integer from banner>,              // REQUIRED integer
    "sex": <"male" | "female">,                // REQUIRED, enum
    "visit_type": <one of: {sorted(VISIT_TYPES)}>,  // REQUIRED
    "visit_reason": "<short reason for today>"  // REQUIRED string
  }},
  "prior_diagnosis": {{                        // optional
    "primary_dx": "<diagnosis name>",
    "dx_date": "<YYYY | YYYY-MM | YYYY-MM-DD>",  // ISO format ONLY
    "gleason": "<e.g. 3+3, 3+4, 4+3, 4+4, 4+5>",
    "grade_group": <1-5>,
    "risk_category": "<very-low | low | intermediate | high | null>",
    "verified_in": <one of: {sorted(VERIFIED_IN_SOURCES)}>
  }},
  "treatment_history": [                       // optional array
    {{
      "modality": <one of: {sorted(TREATMENT_MODALITIES)}>,
      "status": <one of: {sorted(TREATMENT_STATUSES)}>,
      "date": "<YYYY | YYYY-MM | YYYY-MM-DD>",
      "verified_in": <one of: {sorted(VERIFIED_IN_SOURCES)}>,
      "narrative_note": "<optional one-clause detail>"
    }}
  ],
  "psa_trajectory": {{                         // optional but include if PSA data exists
    "current_value": <number, ng/mL>,          // MUST be from PSA CURVE
    "current_date": "<YYYY-MM-DD>",            // MUST match the value's date
    "prior_value": <number>,                   // optional, MUST be from PSA CURVE
    "prior_date": "<YYYY-MM-DD>",
    "peak_value": <number>,                    // optional, MUST be from PSA CURVE
    "peak_date": "<YYYY-MM-DD>",
    "direction": <one of: {sorted(PSA_DIRECTIONS)}>,  // REQUIRED if psa_trajectory present
    "narrative_descriptor": "<stable | rising | declining | fluctuating>"
  }},
  "procedure_findings": [                      // optional array
    {{
      "procedure_type": <one of: {sorted(PROCEDURE_TYPES)}>,
      "date": "<YYYY-MM-DD>",                  // MUST match a procedure date in source
      "finding": "<one short clause summarizing the finding>",
      "verified_in": <one of: {sorted(VERIFIED_IN_SOURCES)}>
    }}
  ],
  "current_regimen": [                         // optional array of CURRENT urologic meds
    {{
      "medication": "<generic name>",          // MUST appear in MEDICATIONS section
      "indication": "<BPH | ED | OAB | ADT | etc>",
      "verified_in": "MEDICATIONS"
    }}
  ],
  "interval_status": {{                        // optional
    "last_visit_date": "<YYYY-MM-DD>",
    "summary": "<1-2 sentences anchored to last visit date>",
    "denies": ["<symptom>", ...]
  }},
  "today_reason": "<single sentence reason for today's visit>"  // REQUIRED
}}
"""


def _ground_truth_block(gt: GroundTruth) -> str:
    """Surface the deterministic ground truth the LLM must use."""
    lines: List[str] = [
        "Authoritative ground truth (use these EXACT values — do not invent):",
        "",
        f"BANNER: name={gt.name!r}, age={gt.age}, sex={gt.sex!r}, visit_date={gt.visit_date!r}",
        "",
    ]
    # PRIMARY UROLOGIC DIAGNOSES — the authoritative diagnosis anchor. For a
    # non-prostate primary (renal mass, bladder tumor, etc.) this is what the
    # HPI must be built around; without it the HPI collapses to a prostate
    # frame or an empty stub.
    if getattr(gt, "other_gu_diagnoses", None):
        lines.append(
            "PRIMARY UROLOGIC DIAGNOSES (authoritative — set prior_diagnosis."
            "primary_dx and frame the entire HPI around the diagnosis below; "
            "each is confirmed by the cited evidence):"
        )
        for d in gt.other_gu_diagnoses:
            organ = getattr(d, "organ", "") or ""
            category = getattr(d, "category", "") or ""
            name = getattr(d, "name", "") or ""
            grade = getattr(d, "grade", "") or ""
            status = getattr(d, "status", "") or ""
            evidence = getattr(d, "evidence", "") or ""
            bits = [b for b in (
                f"organ={organ}", f"category={category}",
                (f"grade={grade}" if grade else ""),
                (f"status={status}" if status else ""),
                (f"evidence={evidence!r}" if evidence else ""),
            ) if b]
            lines.append(f"  - {name} ({', '.join(bits)})")
        lines.append(
            "  NOTE: 'indeterminate' means the lesion is NOT yet proven "
            "benign or malignant — describe it as 'of uncertain significance' "
            "/ 'indeterminate', never as confirmed cancer."
        )
        lines.append("")
    if gt.cancer_status:
        lines.append(
            f"PROSTATE_CANCER_STATUS: {gt.cancer_status}. "
            "If ABSENT, the patient does NOT have prostate cancer — do NOT "
            "state or imply a prostate-cancer or metastatic-prostate-cancer "
            "diagnosis anywhere in the HPI (an elevated PSA alone is NOT "
            "prostate cancer)."
        )
        lines.append("")
    if gt.psa_entries:
        lines.append("PSA CURVE (newest first — every PSA value you cite MUST be in this list):")
        for e in gt.psa_entries[:25]:
            lines.append(f"  {e.value} ng/mL on {e.date}")
        lines.append("")
    if gt.confirmed_treatment_modalities:
        lines.append(
            f"CONFIRMED PRIOR TREATMENTS (from PSH/pathology/timeline — only "
            f"these may be cited as 'completed' / 'ongoing'):"
        )
        for m in sorted(gt.confirmed_treatment_modalities):
            lines.append(f"  - {m}")
        lines.append("")
    elif gt.treatment_naive:
        lines.append("CONFIRMED PRIOR TREATMENTS: (none — patient is treatment-naive)")
        lines.append("")
    else:
        # Treated patient whose specific modalities didn't map to the
        # canonical vocabulary. Do NOT tell the LLM the patient is
        # treatment-naive — that is the bug that collapsed treated
        # patients to a "new patient" HPI. The timeline below carries
        # the detail.
        lines.append(
            "CONFIRMED PRIOR TREATMENTS: this patient HAS been treated "
            "(NOT treatment-naive)"
            + (f" — cancer status: {gt.cancer_status}" if gt.cancer_status else "")
            + ". Narrate the treatment course from the TREATMENT TIMELINE below."
        )
        lines.append("")
    # Treatment / diagnosis timeline assembled from the clinical record.
    # This is the primary anchor for the HPI's disease-course narrative on
    # narrative oncology inputs where structured sections are empty.
    if gt.treatment_timeline:
        lines.append(
            "TREATMENT / DIAGNOSIS TIMELINE (oldest→newest as documented; "
            "narrate the disease course from these events — do NOT omit the "
            "treatment history):"
        )
        for line in gt.treatment_timeline[:40]:
            lines.append(f"  - {line}")
        lines.append("")
    if gt.current_active_treatments:
        lines.append(
            "CURRENTLY ACTIVE TREATMENTS (the patient is presently on these):"
        )
        for t in gt.current_active_treatments[:20]:
            lines.append(f"  - {t}")
        lines.append("")
    if gt.gleason_scores or gt.grade_groups:
        lines.append("PATHOLOGY FACTS:")
        if gt.gleason_scores:
            lines.append(f"  Gleason scores in pathology: {sorted(gt.gleason_scores)}")
        if gt.grade_groups:
            lines.append(f"  Grade Groups in pathology: {sorted(gt.grade_groups)}")
        lines.append("")
    if gt.medications:
        lines.append("MEDICATIONS in MEDICATIONS section (only meds in this list may "
                     "appear in current_regimen):")
        for m in sorted(gt.medications)[:20]:
            lines.append(f"  - {m}")
        if len(gt.medications) > 20:
            lines.append(f"  ... and {len(gt.medications) - 20} more")
        lines.append("")
    if gt.procedure_dates:
        lines.append("PROCEDURE EVENTS (date → types):")
        for date in sorted(gt.procedure_dates, reverse=True)[:15]:
            types = sorted(gt.procedure_dates[date])
            lines.append(f"  {date}: {types}")
        lines.append("")
    if gt.pathology_text:
        snippet = gt.pathology_text[:500].strip()
        lines.append(f"PATHOLOGY TEXT (excerpt):\n{snippet}")
        lines.append("")
    if gt.psh_text:
        snippet = gt.psh_text[:400].strip()
        lines.append(f"PAST SURGICAL HISTORY (excerpt):\n{snippet}")
        lines.append("")
    if getattr(gt, "imaging_text", "").strip():
        snippet = gt.imaging_text[:700].strip()
        lines.append(
            "IMAGING (source excerpt — the primary evidence for a renal / "
            "bladder / adrenal lesion; summarize relevant findings):\n"
            f"{snippet}")
        lines.append("")
    # PRIOR HPI as a template + PRIOR PLAN for continuity. The LLM adapts the
    # prior HPI for today rather than regenerating from scratch, and reflects
    # the prior plan (pending workup, surveillance interval).
    if getattr(gt, "prior_hpi", "").strip():
        snippet = gt.prior_hpi.strip()[:1800]
        lines.append(
            "PRIOR HPI (most recent — USE THIS AS YOUR TEMPLATE. Preserve its "
            "accurate history and structure, update it for today's visit, and "
            "CONFIRM every diagnosis it states against the authoritative facts "
            "above; correct or drop anything not supported — especially do NOT "
            "carry forward a cancer diagnosis the facts mark ABSENT/"
            "indeterminate):\n" + snippet)
        lines.append("")
    if getattr(gt, "prior_plan", "").strip():
        snippet = gt.prior_plan.strip()[:1200]
        lines.append(
            "PRIOR ASSESSMENT/PLAN (reflect the established plan — pending "
            "studies, surveillance interval, deferred workup — in "
            "interval_status.summary and today_reason):\n" + snippet)
        lines.append("")
    return "\n".join(lines)


def _retry_feedback_block(
    schema_errors: List[ValidationError],
    fact_errors: List[FactValidationError],
) -> str:
    """When this is a retry attempt, surface the prior errors so the
    LLM can correct them precisely."""
    if not schema_errors and not fact_errors:
        return ""
    lines = ["YOUR PREVIOUS DRAFT HAD ERRORS — FIX THESE EXACTLY:", ""]
    if schema_errors:
        lines.append("Schema errors:")
        for e in schema_errors:
            line = f"  - {e.path}: [{e.code}] {e.message}"
            if e.expected is not None:
                line += f" (allowed: {e.expected})"
            if e.found is not None:
                line += f" (got: {e.found!r})"
            lines.append(line)
        lines.append("")
    if fact_errors:
        lines.append("Fact-validation errors (the value you cited is NOT in the ground truth):")
        for e in fact_errors:
            line = f"  - [{e.severity}] {e.path}: [{e.code}] {e.message}"
            if e.expected is not None:
                line += f" (allowed: {e.expected})"
            if e.found is not None:
                line += f" (got: {e.found!r})"
            lines.append(line)
        lines.append("")
        # Critical guardrail for VISIT_REASON_* errors: the LLM has been
        # observed "fixing" these by REMOVING valid treatment data
        # rather than rewriting visit_reason. Force the correct direction.
        if any(e.code.startswith("VISIT_REASON_") for e in fact_errors):
            lines.append("CRITICAL: To fix VISIT_REASON_* contradictions, "
                         "REWRITE intro.visit_reason and today_reason to "
                         "match the validated prior_diagnosis and "
                         "treatment_history. DO NOT remove or alter "
                         "treatment_history entries — those are anchored "
                         "to PSH and pathology and must stay.")
            lines.append("")
    lines.append("Re-emit the COMPLETE corrected JSON object. Do NOT explain — output JSON only.")
    return "\n".join(lines)


def build_hpi_json_prompt(
    gt: GroundTruth,
    schema_errors: Optional[List[ValidationError]] = None,
    fact_errors: Optional[List[FactValidationError]] = None,
) -> str:
    """Assemble the prompt for HPI JSON generation.

    If schema_errors / fact_errors are provided, this is a retry —
    the prompt includes the prior errors so the LLM can correct."""

    sections = [
        "You are a clinical documentation assistant producing a STRUCTURED "
        "HPI for a urology clinic note. You will emit ONLY a single JSON "
        "object conforming to the HPIDraft schema below. No prose. No "
        "explanation. No markdown code fences. The first character of "
        "your output MUST be `{` and the last MUST be `}`.",
        "",
        "VISIT CONTEXT: This is a real urology clinic visit occurring on "
        "the BANNER visit_date below. Frame the HPI as the documentation "
        "of an actual clinic encounter. Do NOT describe it as 'chart "
        "preparation', 'chart-prep', or say 'patient has not been "
        "interviewed today' — those framings are forbidden.",
        "",
        "SCOPE: This IS the urology clinic. NEVER frame any aspect of "
        "the patient's care as 'referred to urology', 'by urology', "
        "'urology consult', 'urology to evaluate', or 'urology to "
        "follow up'. We ARE the urology team — describe management "
        "in the first person plural ('we will...', 'our plan is...') "
        "or active voice ('the patient is being followed for...', "
        "'the patient is on active surveillance for...').",
        "",
        "ABSOLUTE RULES:",
        "  1. EVERY value in the JSON must come from the authoritative "
        "ground truth shown below. Do not invent values.",
        "  2. Every PSA value in psa_trajectory MUST appear in the PSA "
        "CURVE (±0.05 tolerance).",
        "  3. Every treatment in treatment_history MUST be a confirmed "
        "prior treatment OR a logically-implied active-surveillance.",
        "  4. Every medication in current_regimen MUST appear in the "
        "MEDICATIONS list.",
        "  5. Every Gleason / Grade Group cited MUST appear in PATHOLOGY.",
        "  6. The intro name/age/sex MUST match the banner exactly.",
        "  7. PSA direction MUST be consistent with values. Use a "
        "'meaningful change' threshold = max(0.1 ng/mL, 10% of prior). "
        "If current > prior by more than that threshold → 'increased'. "
        "If current < prior by more than that threshold → 'decreased'. "
        "Otherwise → 'stable'. So 0.02 vs 0.04 (delta 0.02, threshold "
        "0.1) is STABLE, not 'decreased' — clinically meaningless "
        "noise at undetectable PSA levels.",
        "  8. Dates MUST be ISO format (YYYY or YYYY-MM or YYYY-MM-DD). "
        "Do NOT use MM/DD/YYYY or 'Feb 2, 2026'.",
        "  9. If a section has no data (e.g., patient is treatment-naive), "
        "OMIT the field or set it to null. Do NOT invent placeholder content.",
        "  10. 'today_reason' AND intro.visit_reason must describe the "
        "REAL clinical reason for this clinic visit, tied to the "
        "patient's specific diagnosis, treatment status, and pertinent "
        "recent changes. CRITICAL: visit_reason/today_reason MUST agree "
        "with prior_diagnosis.risk_category AND treatment_history. "
        "Examples of CORRECT framing: "
        "'routine surveillance of low-risk prostate cancer on active "
        "surveillance' (only when risk='low' AND treatment_history is "
        "empty or active-surveillance only); "
        "'post-treatment surveillance after IMRT for high-risk prostate "
        "cancer' (when risk='high' AND treatment_history has completed "
        "radiation); "
        "'follow-up of biochemical recurrence after prostatectomy' "
        "(when treatment_history has completed prostatectomy AND PSA "
        "is rising). NEVER mix incompatible terms (e.g., 'high-risk "
        "cancer on active surveillance' for a patient s/p IMRT).",
        "  11. Populate interval_status whenever the source documents a "
        "prior urology visit. Include a 1-2-sentence summary of the "
        "interval (symptoms, treatment continuation, any changes) "
        "anchored to the last visit date, and a 'denies' list of "
        "pertinent negatives the source documents.",
        "  12. Fill prior_diagnosis whenever the patient has a known "
        "urologic diagnosis (prostate cancer, RCC, bladder cancer, BPH, "
        "stones, etc.) — not just for cancer. The renderer uses this "
        "to anchor the HPI's clinical framing. When PRIMARY UROLOGIC "
        "DIAGNOSES are listed in the ground truth, set "
        "prior_diagnosis.primary_dx to that diagnosis and build the HPI "
        "around it (e.g. a right renal mass under active surveillance).",
        "  13. TEMPLATE: When a PRIOR HPI is provided, use it as your "
        "starting template — preserve its accurate clinical history, "
        "presenting story, and interval structure, then update it for "
        "today's visit. Do NOT discard the established narrative and "
        "emit a sparse stub. BUT every diagnosis carried from the prior "
        "HPI MUST be re-confirmed against the authoritative ground truth: "
        "correct or drop any diagnosis the facts do not support (a prior "
        "note that speculated 'possible metastatic disease' does NOT make "
        "it a confirmed diagnosis).",
        "  14. CONTINUITY: When a PRIOR ASSESSMENT/PLAN is provided, "
        "reflect its active plan — pending studies (e.g. 'pending renal "
        "MRI'), surveillance interval, and deferred workup — in "
        "interval_status.summary and today_reason, so the HPI reads as a "
        "continuation of the established care, not an isolated snapshot.",
        "",
        _schema_block(),
        "",
        _ground_truth_block(gt),
        "",
        _retry_feedback_block(schema_errors or [], fact_errors or []),
        "",
        "Output the JSON object now. Do NOT wrap it in code fences. "
        "Do NOT include any text before or after the JSON.",
    ]
    return "\n".join(s for s in sections if s)


# ---------------------------------------------------------------------------
# Lenient JSON parser
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$",
                       re.IGNORECASE | re.MULTILINE)


def _try_recover_truncated(blob: str, opener_stack: List[str],
                            in_string: bool) -> Optional[str]:
    """Attempt to recover a JSON object truncated by output length cap.

    The LLM commonly emits valid JSON but is cut off before its trailing
    closers. Strategy:
      1. If we ended mid-string, close it.
      2. Strip a dangling trailing comma (truncation often leaves one).
      3. Append the missing closers in reverse nesting order using the
         opener stack so `}]}` vs `]}}` is correct.
      4. json.loads gates the result — anything that doesn't actually
         parse returns None.

    Recovery is conservative: it does NOT discard partial trailing
    tokens. If the LLM was cut off mid-key or mid-value, json.loads
    will reject the patched blob and we return None.
    """
    if not opener_stack:
        return None
    s = blob
    if in_string:
        s = s + '"'
    s = s.rstrip()
    if s.endswith(','):
        s = s[:-1]
    closers = ''.join(']' if op == '[' else '}' for op in reversed(opener_stack))
    return s + closers


def parse_hpi_json(raw: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Parse the LLM output into an HPIDraft dict.

    Returns (draft, parse_error). One of the two is non-None.

    Tolerances:
      - Markdown code fences (```json / ```)
      - Leading/trailing prose around the JSON object
      - Trailing commas (json.loads is strict; we don't fix those here —
        the LLM is instructed to emit strict JSON)
    """
    if not raw or not raw.strip():
        return None, "empty LLM output"

    text = _FENCE_RE.sub("", raw.strip()).strip()

    # Find the first '{' and the matching '}' via balanced-brace scan.
    start = text.find("{")
    if start < 0:
        return None, "no '{' found in LLM output"

    # Walk forward, tracking a stack of unmatched openers so we can
    # recover from LLM output truncation (a common failure mode — the
    # model emits valid JSON but is cut off before its trailing closers).
    opener_stack: List[str] = []
    in_string = False
    escape = False
    end = -1
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            opener_stack.append("{")
        elif c == "[":
            opener_stack.append("[")
        elif c == "}":
            if opener_stack and opener_stack[-1] == "{":
                opener_stack.pop()
            if not opener_stack:
                end = i
                break
        elif c == "]":
            if opener_stack and opener_stack[-1] == "[":
                opener_stack.pop()

    if end < 0:
        recovered = _try_recover_truncated(
            text[start:], opener_stack, in_string,
        )
        if recovered is not None:
            try:
                draft = json.loads(recovered)
                if isinstance(draft, dict):
                    return draft, None
            except json.JSONDecodeError:
                pass
        return None, "unmatched '{' in LLM output (no balanced closing brace)"

    blob = text[start:end + 1]
    try:
        draft = json.loads(blob)
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"

    if not isinstance(draft, dict):
        return None, f"top-level JSON is {type(draft).__name__}, not object"

    return draft, None
