"""LLM-forward HPI composer with a grounding + completeness verify-repair loop.

The legacy HPI paths RENDER a deterministic skeleton / GroundTruth JSON, so a bad
ledger value propagates verbatim into the prose. This composer lets the LLM WRITE
the HPI from the fact ledger + PSA/pathology/timeline, then deterministically
VERIFIES it before accepting.

Verification is split by severity:
  HARD (fall back to v2/v1 rather than emit — clinically unsafe):
    * GRADE   — a Gleason / Grade Group in the prose must be documented in the
                chart (catches URIARTE 3+4/GG2 downgraded to 3+3/GG1).
    * DRUG    — an oncologic drug named in the prose must be documented in the
                chart, by generic (catches Eligard->Lupron only across generics,
                and darolutamide->enzalutamide).
  SOFT (repair + log, then keep):
    * DATE    — a biopsy/treatment YEAR must match the ledger's event years.
    * LEAD    — when the patient has a cancer, the HPI must open on it, not a
                benign/secondary complaint (catches BARRERA opening on
                incontinence for a metastatic patient).
    * COMPLETENESS — each documented cancer must appear.
The word-doubling collapse + the conservative PSA/biopsy scrubbers run as the
final safety net.

Safe-degrade: disabled (VAUCDA_HPI_COMPOSER=0), empty output, a surviving HARD
violation, or any exception -> return None and the caller falls back to v2/v1.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, List, Optional, Set, Tuple

from ..patient_status_facts import format_facts_for_prompt

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], str]

_BIOPSY_KW = re.compile(r"biops", re.IGNORECASE)
_TREATMENT_KW = re.compile(
    r"radiation|\bXRT\b|\bEBRT\b|\bIMRT\b|brachy|prostatectom|\bADT\b|androgen|"
    r"eligard|lupron|leuprolide|degarelix|goserelin|orgovyx|relugolix|abiraterone|"
    r"enzalutamide|apalutamide|darolutamide|ablation|cryo", re.IGNORECASE)

# Oncologic drug -> generic. Only CROSS-GENERIC mismatches are flagged (Eligard
# vs Lupron are both leuprolide and interchangeable; darolutamide vs
# enzalutamide are not).
_DRUG_GENERIC = {
    "eligard": "leuprolide", "lupron": "leuprolide", "leuprolide": "leuprolide",
    "degarelix": "degarelix", "firmagon": "degarelix",
    "goserelin": "goserelin", "zoladex": "goserelin",
    "triptorelin": "triptorelin", "trelstar": "triptorelin",
    "orgovyx": "relugolix", "relugolix": "relugolix",
    "abiraterone": "abiraterone", "zytiga": "abiraterone",
    "enzalutamide": "enzalutamide", "xtandi": "enzalutamide",
    "apalutamide": "apalutamide", "erleada": "apalutamide",
    "darolutamide": "darolutamide", "nubeqa": "darolutamide",
    "docetaxel": "docetaxel", "cabazitaxel": "cabazitaxel",
    "bicalutamide": "bicalutamide", "nilutamide": "nilutamide", "flutamide": "flutamide",
}
_CANCER_KW = ("cancer", "carcinoma", "adenocarc", "malign", "\brcc\b", "renal cell",
              "tumou", "seminoma", "gleason", "grade group", "urotheli")


_UNI_SPACE = re.compile("[\u00a0\u2000-\u200a\u202f\u205f\u3000]")


def _norm(text: str) -> str:
    """Normalize unicode spaces (LLMs emit narrow/thin/no-break spaces around
    '+' and numbers) so grade/drug extraction and matching are not blinded."""
    return _UNI_SPACE.sub(" ", text or "")


def _sentences(text: str) -> List[str]:
    return re.split(r"(?<=[.!?])\s+", text or "")


# ---- grade grounding --------------------------------------------------------
def _grades(text: str) -> Set[str]:
    text = _norm(text)
    try:
        from ..pathology_findings import core_findings
        return {t for t in core_findings(text) if t.startswith(("gleason:", "gg:"))}
    except Exception:  # noqa: BLE001
        out: Set[str] = set()
        for a, b in re.findall(r"gleason[^0-9]{0,12}(\d)\s*\+\s*(\d)", text, re.I):
            out.add(f"gleason:{a}+{b}")
        for g in re.findall(r"(?:grade\s+group|\bGG)\s*[:=]?\s*([1-5])\b", text, re.I):
            out.add(f"gg:{g}")
        return out


def _grade_violations(hpi: str, chart: str) -> List[str]:
    allowed = _grades(chart)
    if not allowed:
        return []
    bad = _grades(hpi) - allowed
    if bad:
        return [f"the grade(s) {sorted(bad)} stated in the HPI are NOT documented "
                f"(documented grades: {sorted(allowed)}) — use the documented grade"]
    return []


def _gleason_max_sum(findings: Set[str]) -> Optional[int]:
    sums = [sum(int(x) for x in t.split(":")[1].split("+"))
            for t in findings if t.startswith("gleason:") and "+" in t]
    return max(sums) if sums else None


def _grade_undersell(hpi: str, chart: str) -> List[str]:
    """The cancer's grade should be the HIGHEST documented Gleason, not a lower
    secondary core (URIARTE reporting 3+3 when 3+4 is documented)."""
    ch = _gleason_max_sum(_grades(chart))
    hp = _gleason_max_sum(_grades(hpi))
    if ch and (hp is None or hp < ch):
        return [f"the HPI reports a Gleason sum of {hp}; the HIGHEST documented "
                f"Gleason sum is {ch} — report the highest-grade core as the "
                f"cancer's grade"]
    return []


# ---- drug grounding ---------------------------------------------------------
def _drug_violations(hpi: str, chart: str) -> List[str]:
    hpi_l, chart_l = _norm(hpi).lower(), _norm(chart).lower()
    viol, flagged = [], set()
    for drug, generic in _DRUG_GENERIC.items():
        if drug in hpi_l and generic not in flagged:
            syns = [d for d, g in _DRUG_GENERIC.items() if g == generic]
            if not any(s in chart_l for s in syns):
                viol.append(f"the drug '{generic}' named in the HPI is not documented "
                            f"in the chart — name only the documented agent")
                flagged.add(generic)
    return viol


# ---- temporal validity ------------------------------------------------------
# Assertion CLASS: DURABLE facts (a biopsy-proven diagnosis, a completed
# procedure) persist once true. VOLATILE facts (disease status, treatment
# status) are true only AS OF their observation date — a "no recurrence" CT is
# true when reported, not before or after — so they must carry that date and be
# re-anchored to the latest result, never carried forward as a standing truth.
# Vague recency ("recent MRI", "recently") hides the as-of date and is banned;
# the actual date must be used.
_DATE_IN_SENT = re.compile(
    r"\b(?:19|20)\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|"
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}",
    re.IGNORECASE)
_VAGUE_RECENCY = re.compile(r"\b(?<!most )(?:recent|recently|lately|newly)\b", re.IGNORECASE)
_VOLATILE_STATUS = re.compile(
    r"no\s+evidence\s+of\s+(?:disease|recurren|malignan)|\bNED\b|"
    r"no\s+(?:recurren|residual|metasta|progression)|stable\s+disease|"
    r"in\s+remission|\bremission\b|biochemical\s+control|disease[-\s]free|"
    r"complete\s+response|"
    r"(?:on|continues\s+on|remains\s+on|currently\s+on)\s+"
    r"(?:continuous\s+|active\s+)?(?:ADT|androgen\s+deprivation|leuprolide|eligard|"
    r"lupron|degarelix|abiraterone|enzalutamide|apalutamide|darolutamide)",
    re.IGNORECASE)


def _temporal_violations(hpi: str) -> List[str]:
    viol: List[str] = []
    for s in _sentences(hpi):
        dated = bool(_DATE_IN_SENT.search(s))
        if _VAGUE_RECENCY.search(s):
            viol.append("replace vague recency ('recent' / 'recently' / 'recent "
                        "MRI/CT') with the actual DATE of the study or result")
        if _VOLATILE_STATUS.search(s) and not dated:
            viol.append("a point-in-time status (NED / no recurrence / stable / on "
                        "ADT) is stated without its as-of DATE — add the date it was "
                        "observed (e.g. 'no recurrence on CT of <date>')")
    return list(dict.fromkeys(viol))


def _scrub_vague_recency(hpi: str) -> str:
    """Guarantee no bare 'recent/recently' survives in an UNDATED sentence (keep
    'most recent'); the date is preferred, but the vague wording must never ship."""
    out = []
    for s in _sentences(hpi):
        if _VAGUE_RECENCY.search(s) and not _DATE_IN_SENT.search(s):
            s = _VAGUE_RECENCY.sub("", s)
            s = re.sub(r"\s{2,}", " ", s).replace(" ,", ",").replace(" .", ".")
        out.append(s.strip())
    return " ".join(x for x in out if x)


# ---- date grounding (year-level, ledger) ------------------------------------
def _ledger_year_sets(facts: Any) -> Tuple[Set[str], Set[str]]:
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
    b_years, t_years = _ledger_year_sets(facts)
    viol: List[str] = []
    for s in _sentences(hpi):
        yrs = set(re.findall(r"\b((?:19|20)\d{2})\b", s))
        if not yrs:
            continue
        low = s.lower()
        if "no biops" in low or "denies" in low:
            continue
        if _BIOPSY_KW.search(s) and b_years and not (yrs & b_years):
            viol.append(f"biopsy date {sorted(yrs)} is not documented; documented "
                        f"biopsy year(s): {sorted(b_years)} — correct it")
        if _TREATMENT_KW.search(s) and t_years and not (yrs & t_years):
            viol.append(f"treatment date {sorted(yrs)} is not documented; documented "
                        f"treatment year(s): {sorted(t_years)} — correct it")
    return viol


# ---- lead-ordering + completeness -------------------------------------------
def _has_cancer(facts: Any) -> bool:
    if (getattr(facts, "cancer_status", "") or "").upper() in ("PRESENT", "TREATED"):
        return True
    return any(getattr(d, "category", "") == "cancer"
               for d in (getattr(facts, "other_gu_diagnoses", None) or []))


def _lead_violation(hpi: str, facts: Any) -> List[str]:
    if not _has_cancer(facts):
        return []
    opener = " ".join(_sentences(hpi)[:2]).lower()
    if not any(re.search(k, opener) for k in _CANCER_KW):
        return ["the HPI opens on a secondary/benign complaint though the patient "
                "has a documented cancer — open with the cancer"]
    return []


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


def _hard(hpi: str, chart: str) -> List[str]:
    return _grade_violations(hpi, chart) + _drug_violations(hpi, chart)


def _soft(hpi: str, facts: Any, chart: str = "") -> List[str]:
    return (_grounding_violations(hpi, facts) + _lead_violation(hpi, facts)
            + _completeness_violations(hpi, facts) + _grade_undersell(hpi, chart)
            + _temporal_violations(hpi))


# ---- prompt -----------------------------------------------------------------
def _compose_prompt(ledger: str, psa_data: str, pathology_data: str, timeline: str) -> str:
    return f"""\
You are a urologist writing the HISTORY OF PRESENT ILLNESS (HPI) for today's
clinic note — 1-2 concise flowing paragraphs. Ground EVERY fact in the material
below; do NOT invent or alter dates, values, grades, drugs, or procedures.

{ledger}

CLINICAL TIMELINE (dated events — use THESE dates, never a note's copy date):
{timeline or "(none)"}

PSA VALUES:
{psa_data or "(none)"}

PATHOLOGY:
{pathology_data or "(none)"}

RULES:
- If the patient has a cancer, OPEN with it (diagnosis, grade, treatment course).
  Do NOT open with a secondary/benign complaint (incontinence, BPH).
- Use the EXACT dates from the CLINICAL TIMELINE; a biopsy/treatment happened on
  its documented date, never a later clinic-visit date.
- Use the EXACT Gleason score and Grade Group as documented — never round or
  change them. When multiple cores are documented, report the HIGHEST Gleason /
  Grade Group as the cancer's grade. Use the EXACT drug name documented (do NOT
  substitute Lupron for Eligard, or enzalutamide for darolutamide).
- Never attach a PSA value or date to an event from a DIFFERENT year (do not
  write 'recurrence in 2010 with PSA ... on <2026 date>').
- Reflect CURRENT_TREATMENT_STATUS (do not write "on/continues ADT" for a
  completed/discontinued course). CURRENT_PHASE is a hint and may be stale.
- TEMPORAL VALIDITY: a finding is true only AS OF the date it was reported. Write
  time-sensitive findings as DATED observations — "CT on <date> showed no
  recurrence", "PSA <value> on <date>", "no metastatic disease on bone scan of
  <date>". NEVER assert a bare, undated point-in-time status (no "NED",
  "stable", "no recurrence", "on ADT" without its date). The MOST RECENT dated
  result wins; do not carry a stale status forward as if current.
- NEVER use vague recency ("recent", "recently", "recent MRI/CT", "lately").
  Always name the actual DATE of the study or result instead.
- PSA: state the MOST RECENT value + date, then summarize the trajectory
  (nadir / peak / trend) in ONE sentence. Do NOT list more than ~4 PSA values.
- Keep procedure findings brief. Cover every documented cancer. End with today's
  interval symptoms/denials. No markdown, no bullets, no "The plan is..."; the
  HPI is history only.

Write the concise HPI now:"""


def _repair_prompt(ledger: str, timeline: str, draft: str, viol: List[str]) -> str:
    issues = "\n".join(f"  - {v}" for v in viol)
    return f"""\
Your HPI has factual problem(s) against the documented record:
{issues}

Rewrite the COMPLETE HPI, keeping everything already correct and fixing the
above. Use ONLY documented facts; keep it concise (1-2 paragraphs).

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
    try:
        from .history_cleaners import clean_llm_commentary, _collapse_word_doubling
        hpi = clean_llm_commentary(hpi)
        hpi = _collapse_word_doubling(hpi)
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
    # word-doubling can be reintroduced by _reconcile_psa_direction
    try:
        from .history_cleaners import _collapse_word_doubling
        hpi = _collapse_word_doubling(hpi)
    except Exception:  # noqa: BLE001
        pass
    # Guarantee no undated vague-recency wording survives.
    hpi = _scrub_vague_recency(hpi)
    return hpi.strip()


def compose_hpi(
    facts: Any,
    psa_data: str,
    pathology_data: str,
    psh_data: str,
    chart: str,
    llm_call: LLMCallable,
    v1_fallback: Optional[str] = None,
    max_repair: int = 1,
) -> Optional[str]:
    """LLM-forward HPI; None to fall back to the v2/v1 HPI path."""
    if os.environ.get("VAUCDA_HPI_COMPOSER", "0") != "1":
        return None
    if facts is None:
        return None
    chart = chart or ""
    try:
        ledger = format_facts_for_prompt(facts)
        timeline = _timeline_text(facts)
        draft = (llm_call(_compose_prompt(ledger, psa_data or "", pathology_data or "",
                                          timeline)) or "").strip()
        repairs = 0
        while draft and repairs < max_repair:
            viol = _hard(draft, chart) + _soft(draft, facts, chart)
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
    # HARD violations that survive => unsafe to emit; fall back to v2/v1.
    hard = _hard(draft, chart)
    if hard:
        logger.info(f"[HPI] hard violation survives ({hard}); falling back to v2/v1")
        return None
    soft = _soft(draft, facts, chart)
    if soft:
        logger.info(f"[HPI] composed with residual soft notes: {soft}")
    return draft or None
