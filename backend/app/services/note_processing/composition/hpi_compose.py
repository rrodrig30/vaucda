"""CC + HPI composer (v3): one whole-chart pass, ledger as DATA, verifier after.

Stage 1 has no assembled note yet, so the context is built from the document-
level extractions (PSA curve, pathology, PSH, medications, imaging) plus the
identified notes (for the clinician's most recent HPI/A/P verbatim) and the
ADT scheduler verdict. The fact ledger is included as advisory data with its
ABSOLUTE RULES section removed: the chart passage the model can quote wins,
and the verifier adjudicates disagreements with quotes.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .context import ChartContext, _CHART_CAP, date_tuples, psa_values_from_curve, recent_clinician_notes
from .ap_compose import parse_json_object, _clean

logger = logging.getLogger(__name__)
LLMCallable = Callable[[str], str]


def ledger_as_data(facts_block: str) -> str:
    """The deterministic ledger without its ABSOLUTE RULES — data, not law."""
    if not facts_block:
        return ""
    cut = facts_block.find("ABSOLUTE RULES")
    return (facts_block[:cut] if cut > 0 else facts_block).rstrip()


def build_stage1_context(
    clinical_document: str,
    raw_clinical_text: str,
    gu_notes: List[Dict[str, Any]],
    facts: Any,
    psa_data: str = "",
    pathology_data: str = "",
    psh_data: str = "",
    medications_data: str = "",
    imaging_data: str = "",
    patient_name: str = "",
    patient_age: Any = "",
    patient_sex: str = "",
    visit_date: str = "",
) -> ChartContext:
    from ..patient_status_facts import format_facts_for_prompt
    from ..adt_status import build_adt_status, adt_plan_directive, adt_plan_constraint
    ctx = ChartContext()
    ctx.chart = (clinical_document or raw_clinical_text or "")[:_CHART_CAP]
    sex = (patient_sex or "").upper()
    ctx.patient_banner = "Patient: " + " | ".join(
        p for p in (str(patient_name or "").strip(), f"Age: {patient_age}" if patient_age else "",
                    f"Sex: {sex}" if sex else "", f"Visit: {visit_date}" if visit_date else "") if p)
    ctx.visit_date = visit_date or ""
    ctx.prior_clinician_notes = recent_clinician_notes(gu_notes or [])
    ctx.tables = {k: v for k, v in (
        ("PSA CURVE", psa_data), ("PATHOLOGY RESULTS", pathology_data), ("PAST SURGICAL HISTORY", psh_data),
        ("MEDICATIONS", medications_data), ("IMAGING", imaging_data)) if v and v.strip()}
    ctx.facts_block = ledger_as_data(format_facts_for_prompt(facts)) if facts is not None else ""
    st = build_adt_status(raw_clinical_text or clinical_document or "", visit_date=visit_date or "")
    if getattr(st, "present", False):
        ctx.adt_directive = (adt_plan_directive(st) or "").strip()
        ctx.adt_constraint = (adt_plan_constraint(st) or "").strip()
        if getattr(st, "last_injection_display", ""):
            ctx.adt_directive = (f"Last documented depot injection {st.last_injection_display}; "
                                 f"status {st.status}. " + ctx.adt_directive).strip()
    ctx.psa_values = psa_values_from_curve(psa_data or "")
    ctx.chart_dates = date_tuples(ctx.chart) | date_tuples(ctx.tables_text(cap=200_000)) | date_tuples(ctx.patient_banner)
    return ctx


def _instructions(ctx: ChartContext, name: str, age: str, sex: str) -> str:
    sex_word = "male" if sex.lower().startswith("m") else ("female" if sex.lower().startswith("f") else "patient")
    opener = f"{name} is a {age}-year-old {sex_word}" if (name and age) else (f"{name} is a {sex_word}" if name else "The patient")
    return f"""\
You are the attending urologist writing the CHIEF COMPLAINT (CC) and HISTORY OF PRESENT
ILLNESS (HPI) for today's clinic visit ({ctx.visit_date or 'today'}) after reading this
patient's entire chart. Write the HPI as the patient's STORY, the way a senior urologic
oncologist tells it to a colleague: what the disease is, how it was found, what was done
and WHY, what the current therapy is and how the patient is responding, what other
services decided, what has happened since the last visit, and what the patient reports
today.

HOW TO READ THE CHART
- The most recent UROLOGY notes (section "MOST RECENT CLINICIAN NOTES") are the backbone:
  the clinician's own synthesis. Carry it forward and update it with interval events.
- The AUTHORITATIVE DATA tables (PSA curve, pathology, surgical history, medications,
  imaging) are verified. Every date, PSA value, Gleason score / Grade Group, stage and
  drug name you write MUST come from them or from the chart verbatim. Never invent,
  round, or infer a value or a date.
- The EXTRACTED FACTS block is advisory data from automated extraction. It is often
  useful (treatment constraints, risk category, secondary findings) and sometimes wrong
  (status labels, phase). Where it conflicts with a chart passage you can quote, the
  chart wins; list the conflict under "open_questions".
- The ADT SCHEDULER VERDICT is arithmetic on documented injection dates and is
  authoritative for depot dates and whether the course is ongoing.

HPI CONTENT (1-3 flowing paragraphs; complete beats brief; no bullets)
1. Open with "{opener} who ..." and state the primary diagnosis in that first sentence
   with grade/stage/NCCN risk EXACTLY as the chart states it, and the reason for today's
   visit. Never open with an incidental problem.
2. How it was found: the PSA history that led to biopsy, the biopsy result (highest
   Gleason / Grade Group, cores, adverse features, date), staging imaging with findings.
   Use the grading system appropriate to the organ (prostate: Gleason / Grade Group;
   kidney: subtype + ISUP grade; bladder: WHO grade + depth; testis: histology +
   markers). A benign / negative biopsy is reported as such with its date, never graded.
3. The treatment path AND the reasons: every documented constraint (a course stopped
   early and why, surgical candidacy, declined options, intolerances) and every
   treatment with agent/type and date. A course the chart says was stopped early is never
   "completed". Bicalutamide started with the first LHRH-agonist dose is ~30-day flare
   prophylaxis, not ongoing therapy; its later absence from the medication list is
   expected and is not "discontinued".
4. Current therapy and response: dated PSA values establishing the direction, testosterone
   if on ADT, the ADT schedule from the scheduler verdict (last and next depot).
5. Interval events: decisions by other services, attempted or failed procedures, new
   imaging, ED visits, new diagnoses that bear on urologic care, with dates.
6. Today's symptoms as documented (urinary symptoms with IPSS if scored, hematuria, erectile
   function and therapies tried, constitutional symptoms reported or denied).
7. Secondary or incidental findings in ONE closing clause, never earlier.

RULES
- Time-sensitive findings are stated WITH their date ("PSA 0.04 ng/mL on 08/20/2026"),
  never with vague recency ("recent", "recently"). The newest dated result is current.
- After radical prostatectomy an undetectable PSA means no recurrence; never assert
  salvage therapy, recurrence or a rising PSA the chart does not document as true.
- Do not infer a treatment from a risk factor or from an option that was only discussed.
- A relative's history (family history) is never the patient's.
- Affirmative history only: no recommendations, no hypotheticals, no meta-commentary.
- CC: one line naming the active primary problem / the documented reason for today's
  visit, tied to the diagnosis and treatment state (e.g. "Follow-up of Grade Group 3
  prostate cancer on ADT; scheduled leuprolide injection"). An incidental never leads.

Return ONLY a JSON object:
{{"chief_complaint": "<one line>", "hpi": "<1-3 paragraphs>", "open_questions": ["<unresolved item for the clinician>", "..."]}}"""


def build_prompt(ctx: ChartContext, name: str, age: str, sex: str) -> str:
    parts = [_instructions(ctx, name, age, sex), ""]
    if ctx.patient_banner:
        parts += ["=== PATIENT ===", ctx.patient_banner, ""]
    if ctx.prior_clinician_notes:
        parts += ["=== MOST RECENT CLINICIAN NOTES (newest first; the backbone) ===", ctx.prior_clinician_notes, ""]
    tables = ctx.tables_text()
    if tables:
        parts += ["=== AUTHORITATIVE DATA (deterministic tables) ===", tables, ""]
    if ctx.adt_directive:
        parts += ["=== ADT SCHEDULER VERDICT (authoritative for depot dates) ===", ctx.adt_directive, ""]
    elif ctx.adt_constraint:
        parts += ["=== ADT (historical) ===", ctx.adt_constraint, ""]
    if ctx.facts_block:
        parts += ["=== EXTRACTED FACTS (advisory data; the chart wins on conflict) ===", ctx.facts_block, ""]
    parts += ["=== FULL CHART (normalized) ===", ctx.chart, "", "Write the JSON now:"]
    return "\n".join(parts)


def compose_cc_hpi_v3(ctx: ChartContext, llm_call: LLMCallable, name: str = "", age: Any = "",
                      sex: str = "", max_retry: int = 1) -> Tuple[str, str, Dict[str, Any]]:
    """Return (cc, hpi, audit). Raises RuntimeError when nothing usable comes back
    (no fallback by design)."""
    prompt = build_prompt(ctx, str(name or "").strip(), str(age or "").strip(), str(sex or ""))
    audit: Dict[str, Any] = {"attempts": 0, "prompt_chars": len(prompt)}
    obj = None
    for attempt in range(max_retry + 1):
        audit["attempts"] = attempt + 1
        raw = (llm_call(prompt) or "").strip()
        audit["raw_chars"] = len(raw)
        obj = parse_json_object(raw)
        hpi = _clean((obj or {}).get("hpi") or (obj or {}).get("history_of_present_illness"))
        if obj and len(hpi) >= 200:
            break
        logger.warning("CC/HPI composer: unusable output on attempt %d (%d chars)", attempt + 1, len(raw))
        obj = None
    if not obj:
        raise RuntimeError("composition v3: the CC/HPI composer produced no usable JSON after retries")
    cc = _clean(obj.get("chief_complaint") or obj.get("cc"))
    hpi = (obj.get("hpi") or obj.get("history_of_present_illness") or "").strip()
    hpi = re.sub(r"[ \t]+", " ", hpi)
    hpi = re.sub(r"\n{3,}", "\n\n", hpi).strip()
    if not cc:
        raise RuntimeError("composition v3: the CC/HPI composer returned no chief complaint")
    oq = [_clean(q) for q in (obj.get("open_questions") or [])]
    oq = [q for q in oq if q and not (re.search(r"(?i)bicalutamide|casodex|anti-?androgen", q) and not re.search(r"(?i)flare", q))]
    audit["open_questions"] = oq[:6]
    return cc, hpi, audit


_HPI_FOOTER_RE = re.compile(r"\n*VERIFICATION NOTES \(HPI\).*?(?=\n\n[A-Z][A-Z /&()\-]{2,}:|\Z)", re.S)


def strip_hpi_footer(stage1_note: str) -> str:
    return _HPI_FOOTER_RE.sub("", stage1_note or "")
