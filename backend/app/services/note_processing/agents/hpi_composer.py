"""LLM-forward HPI composer with a grounding + completeness verify-repair loop.

The legacy HPI paths RENDER a deterministic skeleton / GroundTruth JSON, so a bad
ledger value propagates verbatim into the prose — e.g. copied-forward pathology
minted phantom biopsy events and the HPI printed "Biopsy on October 29, 2025"
(real biopsy 8/16/2022).

This composer lets the LLM WRITE the HPI from the fact ledger + PSA/pathology,
then deterministically VERIFIES it:
  * GROUNDING (precision): a biopsy/treatment date asserted in the prose must be
    grounded in the ledger's biopsy/treatment event YEARS (year-level match keeps
    false positives low). PSA values + fabricated biopsy claims are scrubbed with
    the existing conservative scrubbers.
  * COMPLETENESS (recall): each documented cancer + confirmed treatment + the
    most-recent PSA must appear.
Violations trigger ONE repair prompt naming them; if a biopsy-date violation
survives, the surgical biopsy-claim scrubber removes the offending clause as a
last resort. Prefer repair over strip so a wrong date is corrected, not deleted.

Safe-degrade: disabled (VAUCDA_HPI_COMPOSER=0), empty output, or any exception ->
return None and the caller falls back to the v2/v1 HPI path.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, List, Optional, Set, Tuple

from ..patient_status_facts import format_facts_for_prompt

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], str]

_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_BIOPSY_KW = re.compile(r"biops", re.IGNORECASE)
_TREATMENT_KW = re.compile(
    r"radiation|\bXRT\b|\bEBRT\b|\bIMRT\b|brachy|prostatectom|\bADT\b|androgen|"
    r"eligard|lupron|leuprolide|degarelix|goserelin|orgovyx|relugolix|abiraterone|"
    r"enzalutamide|apalutamide|darolutamide|ablation|cryo", re.IGNORECASE)


def _sentences(text: str) -> List[str]:
    return re.split(r"(?<=[.!?])\s+", text or "")


def _years_in(s: str) -> Set[str]:
    return set(re.findall(r"\b((?:19|20)\d{2})\b", s))


def _ledger_year_sets(facts: Any) -> Tuple[Set[str], Set[str]]:
    """(biopsy_years, treatment_years) from the clinical timeline + procedures."""
    biopsy: Set[str] = set()
    treatment: Set[str] = set()
    for e in (getattr(facts, "clinical_timeline", None) or []):
        yr = (getattr(e, "date_key", "") or "")[:4]
        if not yr.isdigit():
            continue
        mod = (getattr(e, "modality", "") or "").lower()
        et = getattr(e, "event_type", "") or ""
        if "biopsy" in mod or et == "PATHOLOGY":
            biopsy.add(yr)
        if et.startswith("TREATMENT_"):
            treatment.add(yr)
    for pf in (getattr(facts, "procedure_findings", None) or []):
        yr = (getattr(pf, "date_key", "") or "")[:4]
        if yr.isdigit() and "biopsy" in (getattr(pf, "procedure", "") or "").lower():
            biopsy.add(yr)
    return biopsy, treatment


def _grounding_violations(hpi: str, facts: Any) -> List[str]:
    """Clause-level year grounding for biopsy/treatment dates. Conservative:
    only flags when the class year-set is NON-EMPTY and the sentence's years
    share NOTHING with it (a correct year alongside a wrong one is not flagged)."""
    b_years, t_years = _ledger_year_sets(facts)
    viol: List[str] = []
    for s in _sentences(hpi):
        yrs = _years_in(s)
        if not yrs:
            continue
        low = s.lower()
        if "no biops" in low or "denies" in low:   # negation guard
            continue
        if _BIOPSY_KW.search(s) and b_years and not (yrs & b_years):
            viol.append(f"biopsy date {sorted(yrs)} is not documented; the only "
                        f"documented biopsy year(s): {sorted(b_years)} — correct it")
        if _TREATMENT_KW.search(s) and t_years and not (yrs & t_years):
            viol.append(f"treatment date {sorted(yrs)} is not documented; documented "
                        f"treatment year(s): {sorted(t_years)} — correct it")
    return viol


def _completeness_violations(hpi: str, facts: Any) -> List[str]:
    lc = hpi.lower()
    miss: List[str] = []
    for d in (getattr(facts, "other_gu_diagnoses", None) or []):
        if getattr(d, "category", "") == "cancer":
            organ = (getattr(d, "organ", "") or "").lower()
            words = {"renal": ["renal", "kidney"], "bladder": ["bladder", "urothelial"],
                     "penile": ["penile", "penis"], "testicular": ["testic"]}.get(organ, [organ])
            if organ and not any(w in lc for w in words):
                miss.append(f"the documented {organ} cancer is not mentioned")
    if (getattr(facts, "cancer_status", "") or "").upper() in ("PRESENT", "TREATED") \
            and "prostate" not in lc:
        miss.append("the documented prostate cancer is not mentioned")
    return miss


def _compose_prompt(ledger: str, psa_data: str, pathology_data: str, timeline: str) -> str:
    return f"""\
You are a urologist writing the HISTORY OF PRESENT ILLNESS (HPI) for today's
clinic note — 1-2 flowing paragraphs of clinical prose. Ground EVERY fact in the
material below; do NOT invent dates, values, grades, drugs, or procedures.

{ledger}

CLINICAL TIMELINE (dated events — use THESE dates, never a note's copy date):
{timeline or "(none)"}

PSA VALUES:
{psa_data or "(none)"}

PATHOLOGY:
{pathology_data or "(none)"}

RULES:
- Open with "<Name> is a <age>-year-old <sex> who ..." only if given; otherwise
  start with the clinical story.
- Use the EXACT dates from the CLINICAL TIMELINE. A biopsy / treatment happened
  on its documented date — never a later clinic-visit date.
- Use the EXACT treatment drug + modality names documented (do NOT substitute
  Lupron for Eligard, etc.). Preserve documented specificity (biochemical
  recurrence, s/p brachytherapy, Grade Group, etc.).
- Reflect CURRENT_TREATMENT_STATUS: do not write "on/continues ADT" for a
  completed or discontinued course. CURRENT_PHASE is a hint and may be stale.
- State each treatment ONCE, concisely (do not restate the same injection twice).
- PSA: lead with the MOST RECENT (latest-date) PSA value and its date, then
  summarize the trajectory (e.g. "PSA has fallen from X (older date) to Y (most
  recent date)"). Cite only values from the PSA list, each with its date.
- Cover every documented cancer and confirmed treatment; end with today's
  interval symptoms/denials if documented.
- No markdown, no bullets, no meta-commentary.

Write the HPI now:"""


def _repair_prompt(ledger: str, timeline: str, draft: str, viol: List[str]) -> str:
    issues = "\n".join(f"  - {v}" for v in viol)
    return f"""\
Your HPI has factual problem(s) against the documented record:
{issues}

Rewrite the COMPLETE HPI, keeping everything already correct and fixing the
above. Use ONLY documented facts.

{ledger}

CLINICAL TIMELINE (authoritative dates):
{timeline or "(none)"}

YOUR PREVIOUS HPI:
{draft}

Rewrite the complete corrected HPI now:"""


def _timeline_text(facts: Any, limit: int = 20) -> str:
    out = []
    for e in (getattr(facts, "clinical_timeline", None) or [])[:limit]:
        disp = getattr(e, "date_display", "") or "(undated)"
        et = (getattr(e, "event_type", "") or "").replace("_", " ").lower()
        mod = getattr(e, "modality", "") or ""
        detail = (getattr(e, "detail", "") or "")[:80]
        out.append(f"  {disp} — {et} {mod}: {detail}".rstrip())
    return "\n".join(out)


def _postprocess(hpi: str, psa_data: str, pathology_data: str, psh_data: str) -> str:
    """Reuse the battle-tested HPI cleaners/scrubbers as the safety net."""
    try:
        from .history_cleaners import clean_llm_commentary
        hpi = clean_llm_commentary(hpi)
    except Exception:  # noqa: BLE001
        pass
    try:
        from .hpi_agent import (_dedupe_hpi_sentences, _reconcile_psa_direction,
                                _scrub_psa_hallucinations, _scrub_unsupported_biopsy_claims)
        hpi = _dedupe_hpi_sentences(hpi)
        hpi = _reconcile_psa_direction(hpi, psa_data)
        hpi = _scrub_psa_hallucinations(hpi, psa_data)
        hpi = _scrub_unsupported_biopsy_claims(hpi, pathology_data, psh_data)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"HPI composer post-process partial: {e}")
    return hpi.strip()


def compose_hpi(
    facts: Any,
    psa_data: str,
    pathology_data: str,
    psh_data: str,
    llm_call: LLMCallable,
    v1_fallback: Optional[str] = None,
    max_repair: int = 1,
) -> Optional[str]:
    """LLM-forward HPI; None to fall back to the v2/v1 HPI path."""
    if os.environ.get("VAUCDA_HPI_COMPOSER", "0") != "1":
        return None
    if facts is None:
        return None
    try:
        ledger = format_facts_for_prompt(facts)
        timeline = _timeline_text(facts)
        draft = (llm_call(_compose_prompt(ledger, psa_data or "", pathology_data or "",
                                          timeline)) or "").strip()
        repairs = 0
        while draft and repairs < max_repair:
            viol = _grounding_violations(draft, facts) + _completeness_violations(draft, facts)
            if not viol:
                break
            draft = (llm_call(_repair_prompt(ledger, timeline, draft, viol)) or draft).strip()
            repairs += 1
    except Exception as e:  # noqa: BLE001
        logger.warning(f"HPI composer failed, falling back: {e}")
        return None
    if not draft or len(draft) < 60:
        return None
    draft = _postprocess(draft, psa_data or "", pathology_data or "", psh_data or "")
    # Report residual grounding for the audit trail.
    residual = _grounding_violations(draft, facts)
    if residual:
        logger.info(f"[HPI] composed with residual grounding notes: {residual}")
    return draft or None
