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


from ..temporal_checks import (  # noqa: E402
    norm as _norm, sentences as _sentences,
    temporal_violations as _temporal_violations,
    scrub_vague_recency as _scrub_vague_recency,
    latest_wins_violations as _latest_wins_violations,
    staleness_violations as _staleness_violations,
    tier_override_violations as _tier_override_violations,
    reference_ym as _reference_ym,
)


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


# ---- biopsy-date grounding against the RAW SOURCE (HARD) --------------------
# The ledger (clinical_timeline / procedure_findings) can mis-date a biopsy on a
# copy-forward chart (BILEK: a colon "TUBULAR ADENOMA Collected: 06/01/2011"
# mis-read as the prostate diagnosis; FRAGA: an ungrounded "9/11/2014"). The
# composer renders the ledger faithfully, so a bad ledger date becomes a
# fabricated HPI biopsy date. This check grounds each stated biopsy year against
# PROSTATE-specific biopsy/pathology/diagnosis dates in the RAW source; an
# unconfirmable biopsy date is a HARD violation -> repair, else fall back to v2.
_DATE_TOK = r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{4})"
_PROSTATE_CTX = re.compile(r"prostat|gleason|grade\s+group|\bGG[1-5]\b|adenocarcinoma", re.I)
_BX_DATE_PATS = [
    re.compile(rf"(?:prostate\s+)?(?:biopsy|core\s+needle\s+biopsy|TRUS\s*bx|prostate\s*bx)"
               rf"\s+(?:on\s+|performed\s+(?:on\s+)?|dated\s+)?{_DATE_TOK}", re.I),
    re.compile(rf"{_DATE_TOK}\s+(?:prostate\s+)?(?:biopsy|core\s+needle|TRUS|prostate\s*bx)\b", re.I),
    re.compile(rf"(?:pathology|path\s*report|collected|date\s+spec(?:imen)?\s+taken|"
               rf"accession\w*)\s*:?\s*{_DATE_TOK}", re.I),
    re.compile(rf"(?:initial\s+diagnosis|date\s+of\s+(?:initial\s+)?diagnosis)\s*:?\s*{_DATE_TOK}", re.I),
    re.compile(rf"(?:initially\s+)?diagnos\w+\s+(?:with\s+[^.]{{0,40}}?)?(?:on\s+|in\s+)?{_DATE_TOK}", re.I),
]
_YEAR = re.compile(r"(19[89]\d|20\d\d)")


def _source_prostate_biopsy_years(chart: str) -> Set[str]:
    """Years of PROSTATE biopsy/pathology/diagnosis dates in the raw source.
    Prostate-qualified so a non-prostate specimen date (colon adenoma) doesn't
    count; verb + label forms both covered so real dates aren't missed."""
    years: Set[str] = set()
    for pat in _BX_DATE_PATS:
        for m in pat.finditer(chart):
            if _PROSTATE_CTX.search(chart[max(0, m.start() - 120):m.end() + 120]):
                ym = _YEAR.search(m.group(1) or "")
                if ym:
                    years.add(ym.group(1))
    return years


def _biopsy_date_hard(hpi: str, chart: str) -> List[str]:
    allowed = _source_prostate_biopsy_years(chart)
    if not allowed:
        return []  # nothing to ground against -> can't prove a violation
    for s in _sentences(hpi):
        if not _BIOPSY_KW.search(s):
            continue
        low = s.lower()
        if "no biops" in low or "denies" in low or "without" in low:
            continue
        yrs = set(re.findall(r"\b((?:19|20)\d{2})\b", s))
        if yrs and not (yrs & allowed):
            return [f"the biopsy date {sorted(yrs)} in the HPI is not corroborated by any "
                    f"documented PROSTATE biopsy/pathology/diagnosis date (documented "
                    f"prostate biopsy years: {sorted(allowed)}) — use a documented biopsy "
                    f"date or state the diagnosis WITHOUT an unverified date"]
    return []


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
    # The FIRST sentence must carry the cancer. Checking the first two let a note
    # bury the cancer behind an incidental opener (TAYLOR: "...chronic kidney
    # disease... vitamin D capsule. He is being evaluated for prostate
    # adenocarcinoma...") — sentence 1 was CKD/vitamin-D, cancer only in sentence 2.
    first = (_sentences(hpi)[:1] or [""])[0].lower()
    if not any(re.search(k, first) for k in _CANCER_KW):
        return ["the FIRST sentence does not name the cancer though the patient has "
                "a documented cancer — open the FIRST sentence with the cancer "
                "diagnosis, not an incidental problem (CKD, vitamin D, HTN, BPH)"]
    return []


# ---- named opening enforcement ----------------------------------------------
# The template opener is "<NAME> is a <AGE>-year-old <sex> who ...". The composer,
# given only the fact ledger, writes "The patient is a male ..." — dropping the
# name and age (a regression vs v1/v2). This deterministically restores them.
# period-tolerant (matches through an honorific like "Mr.") but bounded so it
# stays within the opening clause.
_OPENER_HAS_NAME = re.compile(
    r"^\s*\S.{0,60}?\bis\s+an?\s+\d{1,3}[-\s]year[-\s]old\b", re.IGNORECASE)
_WEAK_SUBJECT = re.compile(
    r"^\s*(?:the\s+patient|this\s+patient|this|the\s+veteran|he|she|"
    r"mr\.?|ms\.?|mrs\.?)\s+is\s+an?\s+"
    r"(?:\d{1,3}[-\s]year[-\s]old\s+)?"
    r"(?:male|female|man|woman|gentleman|gentlewoman|lady|boy|girl)\b",
    re.IGNORECASE)


def _sex_word(sex: str) -> str:
    s = (sex or "").strip().lower()
    if s.startswith("m"):
        return "male"
    if s.startswith("f"):
        return "female"
    return "patient"


def _ensure_named_opening(hpi: str, name: Optional[str], age: Optional[Any],
                          sex: Optional[str]) -> str:
    """Guarantee the HPI opens with '<NAME> is a <AGE>-year-old <sex>'."""
    if not hpi or not name:
        return hpi
    if _OPENER_HAS_NAME.search(hpi):
        return hpi  # already named + aged
    age_str = str(age).strip() if age not in (None, "") else ""
    subj = (f"{name} is a {age_str}-year-old {_sex_word(sex)}"
            if age_str else f"{name} is a {_sex_word(sex)}")
    m = _WEAK_SUBJECT.search(hpi)
    if m:
        # "The patient is a male with a history of RCC..." ->
        # "<NAME> is a <AGE>-year-old male with a history of RCC..."
        return subj + hpi[m.end():]
    # No recognizable subject phrase — prepend a canonical opener sentence.
    body = hpi.lstrip()
    return f"{subj} presents for urologic follow-up. " + body[:1].upper() + body[1:]


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
    return (_grade_violations(hpi, chart) + _drug_violations(hpi, chart)
            + _biopsy_date_hard(hpi, chart))


def _soft(hpi: str, facts: Any, chart: str = "", psa_data: str = "") -> List[str]:
    return (_grounding_violations(hpi, facts) + _lead_violation(hpi, facts)
            + _completeness_violations(hpi, facts) + _grade_undersell(hpi, chart)
            + _temporal_violations(hpi) + _latest_wins_violations(hpi, facts, psa_data)
            + _staleness_violations(hpi, _reference_ym(chart))
            + _tier_override_violations(hpi, facts))


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
- Begin the FIRST sentence with the patient and the reason for the visit, e.g.
  "<the patient> is a <age>-year-old man who returns for <primary problem>".
- If the patient has a cancer, the FIRST sentence must name it (diagnosis, grade,
  treatment course). Do NOT open on a secondary/benign/incidental problem
  (chronic kidney disease, vitamin D, hypertension, incontinence, BPH) — those
  come later, if at all.
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
- SERIAL identical results (e.g. many "no evidence of disease" scans): do NOT
  list each and do NOT claim continuous truth across the whole span — anchor on
  the MOST RECENT observation + its date, optionally noting the surveillance span
  ("stable on serial CT, most recently <date>"). A structured dated result
  (pathology/imaging/lab) OUTRANKS any prior-note narrative — follow the newest
  structured result and never carry a narrative claim it contradicts.
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
        tag = ("  [volatile — true only as of this date; do not carry forward]"
               if getattr(e, "assertion_class", "") == "volatile" else "")
        out.append(f"  {disp} — {et} {mod}: {detail}{tag}".rstrip())
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
    patient_name: Optional[str] = None,
    patient_age: Optional[Any] = None,
    patient_sex: Optional[str] = None,
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
            viol = _hard(draft, chart) + _soft(draft, facts, chart, psa_data or "")
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
    # Restore the "<NAME> is a <AGE>-year-old <sex>" template opener the composer
    # drops (it only sees the fact ledger, so it writes "The patient is a male").
    draft = _ensure_named_opening(draft, patient_name, patient_age, patient_sex)
    # HARD violations that survive => unsafe to emit; fall back to v2/v1.
    hard = _hard(draft, chart)
    if hard:
        logger.info(f"[HPI] hard violation survives ({hard}); falling back to v2/v1")
        return None
    soft = _soft(draft, facts, chart, psa_data or "")
    if soft:
        logger.info(f"[HPI] composed with residual soft notes: {soft}")
    return draft or None
