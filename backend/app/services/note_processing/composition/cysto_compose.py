"""Cystoscopy pre-procedure header composer (v3).

The cystoscopy note is a TEMPLATE the provider completes around the procedure.
Only the header fields are composed here, from the WHOLE chart with the most
recent urology notes as the backbone: INDICATION (why THIS cystoscopy), HPI (the
relevant GU story), and one-line pertinence statements for IMAGING and PATHOLOGY
when the deterministic sections are empty. The exam findings, ASSESSMENT and
PLAN are left BLANK by design: the procedure has not happened yet, and the old
builder's "anticipated" findings and a pre-written "no bladder pathology
identified" were confabulation (CICCOTTI 10/24).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .context import ChartContext, _CHART_CAP, date_tuples, psa_values_from_curve, recent_clinician_notes
from .ap_compose import parse_json_object, _clean
from .hpi_compose import ledger_as_data

logger = logging.getLogger(__name__)
LLMCallable = Callable[[str], str]


def build_cysto_context(
    normalized_text: str,
    gu_notes: List[Dict[str, Any]],
    facts: Any,
    tables: Dict[str, str],
    procedure_context: str,
    patient_name: str,
    patient_sex: str,
    proc_date: str,
) -> ChartContext:
    from ..patient_status_facts import format_facts_for_prompt
    ctx = ChartContext()
    ctx.chart = (normalized_text or "")[:_CHART_CAP]
    ctx.patient_banner = "Patient: " + " | ".join(p for p in (
        patient_name.strip(), f"Sex: {patient_sex.upper()}" if patient_sex else "",
        f"Procedure date: {proc_date}" if proc_date else "") if p)
    ctx.visit_date = proc_date or ""
    ctx.prior_clinician_notes = recent_clinician_notes(gu_notes or [])
    ctx.tables = {k: v for k, v in (tables or {}).items() if v and v.strip()}
    if procedure_context:
        ctx.tables["PROCEDURE HISTORY (deterministic: completed vs booked)"] = procedure_context
    try:
        ctx.facts_block = ledger_as_data(format_facts_for_prompt(facts)) if facts is not None else ""
    except Exception as e:  # noqa: BLE001  — the ledger is advisory; its absence must not block a note
        logger.warning("cysto: facts block unavailable: %s", e)
        ctx.facts_block = ""
    ctx.psa_values = psa_values_from_curve(ctx.tables.get("PSA CURVE", ""))
    ctx.chart_dates = date_tuples(ctx.chart) | date_tuples(ctx.tables_text(cap=200_000))
    return ctx


def _instructions(ctx: ChartContext) -> str:
    return f"""\
You are the attending urologist preparing the HEADER of today's cystoscopy procedure note
({ctx.visit_date or 'today'}) after reading this patient's entire chart. The procedure has
NOT happened yet: you are writing WHY it is being done and the GU story behind it, not
what was seen. The findings, assessment and plan are completed by the urologist after
the procedure and must be left empty.

HOW TO READ THE CHART
- The most recent UROLOGY notes (section "MOST RECENT CLINICIAN NOTES") are the backbone:
  the reason for today's cystoscopy is almost always stated there (a planned TURP or
  other procedure this cystoscopy evaluates for, a hematuria work-up, bladder-tumor
  surveillance, LUTS refractory to medication, a stricture, a lesion on imaging).
- The AUTHORITATIVE DATA tables are verified. Every date, value, grade and drug name you
  write MUST come from them or from the chart verbatim. Never invent or infer.
- PROCEDURE HISTORY separates COMPLETED procedures from BOOKED ones: a booked procedure has
  not happened; today's cystoscopy is usually the pre-operative evaluation for it, so say
  so with its booked date. Describe a TURP or other outlet procedure as prior ONLY when it
  is listed as completed.
- The EXTRACTED FACTS block is advisory automated data; where it conflicts with a chart
  passage you can quote, the chart wins silently. Open questions are only what the
  urologist must confirm before scoping (a missing culture, an anticoagulant not yet held,
  an unclear planned procedure); never a disagreement with the extracted facts.

WRITE
- "indication": ONE line naming why THIS cystoscopy is being done, in the clinician's own
  terms (e.g. "Pre-operative evaluation for planned TURP for BPH/LUTS refractory to
  tamsulosin and alfuzosin; worsening urgency, frequency and nocturia"). Lead with the
  real reason; a renal or adrenal lesion that is not the reason for scoping never leads.
- "hpi": one concise NARRATIVE paragraph (flowing prose, 4-9 sentences) of the relevant GU
  history: age and the presenting problem; prior lower-urinary-tract and outlet procedures
  with dates (TURP, urethroplasty, prosthesis surgery, prior TURBTs with their pathology);
  the presenting symptoms as documented (LUTS with IPSS if scored, hematuria, dysuria,
  retention); relevant medications tried and failed; tobacco or other risk factors when
  documented; the most recent pertinent imaging with date and finding; the pre-procedure
  urine culture result; anticoagulant or antiplatelet therapy and whether and when it was
  held; and the medical comorbidities that matter for the procedure (diabetes,
  cardiac/stroke history, anticoagulation). Bladder cancer wording only when pathology
  documents malignancy; a benign or negative result is stated as benign; an unbiopsied
  lesion is "a lesion of uncertain significance".
- "imaging_pertinence": ONE line used only when the IMAGING table is empty: either "None
  pertinent to the current GU complaint on review" or the pertinent study, date and finding.
- "pathology_pertinence": ONE line used only when the PATHOLOGY table is empty: either
  "None pertinent to the current GU complaint" or the pertinent specimen, date and result.
- "culture": ONE line with the most recent urine culture result and date, or "No urine
  culture on file for the pre-procedure urinalysis".
- "open_questions": items the urologist must confirm before the procedure.

Return ONLY a JSON object:
{{"indication": "...", "hpi": "...", "imaging_pertinence": "...", "pathology_pertinence": "...",
  "culture": "...", "open_questions": ["..."]}}"""


def build_prompt(ctx: ChartContext) -> str:
    parts = [_instructions(ctx), ""]
    if ctx.patient_banner:
        parts += ["=== PATIENT ===", ctx.patient_banner, ""]
    if ctx.prior_clinician_notes:
        parts += ["=== MOST RECENT CLINICIAN NOTES (newest first; the backbone) ===", ctx.prior_clinician_notes, ""]
    tables = ctx.tables_text(headers=tuple(ctx.tables.keys()))
    if tables:
        parts += ["=== AUTHORITATIVE DATA (deterministic tables) ===", tables, ""]
    if ctx.facts_block:
        parts += ["=== EXTRACTED FACTS (advisory data; the chart wins on conflict) ===", ctx.facts_block, ""]
    parts += ["=== FULL CHART (normalized) ===", ctx.chart, "", "Write the JSON now:"]
    return "\n".join(parts)


def compose_cysto_header(ctx: ChartContext, llm_call: LLMCallable, max_retry: int = 1) -> Tuple[Dict[str, str], Dict[str, Any]]:
    """Return (fields, audit). Raises RuntimeError when nothing usable comes back
    (no fallback by design)."""
    prompt = build_prompt(ctx)
    audit: Dict[str, Any] = {"attempts": 0, "prompt_chars": len(prompt)}
    obj = None
    for attempt in range(max_retry + 1):
        audit["attempts"] = attempt + 1
        raw = (llm_call(prompt) or "").strip()
        audit["raw_chars"] = len(raw)
        obj = parse_json_object(raw)
        if obj and len(_clean(obj.get("hpi"))) >= 120 and _clean(obj.get("indication")):
            break
        logger.warning("cysto composer: unusable output on attempt %d (%d chars)", attempt + 1, len(raw))
        obj = None
    if not obj:
        raise RuntimeError("composition v3: the cystoscopy header composer produced no usable JSON after retries")
    fields = {k: _clean(obj.get(k)) for k in ("indication", "hpi", "imaging_pertinence", "pathology_pertinence", "culture")}
    fields["hpi"] = re.sub(r"\s+", " ", (obj.get("hpi") or "")).strip()
    oq = [_clean(q) for q in (obj.get("open_questions") or [])]
    audit["open_questions"] = [q for q in oq if q and not re.search(
        r"(?i)extracted facts|verified facts|facts? (?:ledger|list|block)|deterministic|phase label", q)][:6]
    return fields, audit
