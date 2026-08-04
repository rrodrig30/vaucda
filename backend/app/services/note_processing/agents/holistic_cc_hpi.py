"""LLM-first HOLISTIC Chief-Complaint + HPI composer (VAUCDA_CC_HPI_HOLISTIC).

Motivation (provider feedback): the fragmented, deterministic-scaffold CC/HPI
pipeline reads less cohesively than a single expert LLM pass over the whole chart
(ChatGPT / Opus), and — worse — it can INJECT a false "ground-truth" fact (e.g.
a discussed-but-never-performed salvage radiation) as an absolute rule the LLM is
forbidden to contradict, confabulating a treatment course that then corrupts the
Assessment/Plan.

This composer flips the authority: the LLM reads the CHART holistically and
writes BOTH the CC and the HPI in one coherent pass. The deterministic facts are
passed as ADVISORY context the model is told it MAY override when the chart
disagrees. A thin, deterministic grounding net (grade / drug / biopsy-date HARD
checks + PSA scrubbers + named-opener + temporal) still runs so the model can't
reopen the number-hallucination door.

Safe-degrade: disabled, empty/malformed output, a surviving HARD violation, or
any exception -> returns None and the caller falls back to the existing
CC-refiner / HPI-composer -> v2 -> v1 chain.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Dict, Optional

from ..patient_status_facts import format_facts_for_prompt
from .hpi_composer import (
    _hard as _hpi_hard,
    _soft as _hpi_soft,
    _ensure_named_opening,
    _has_cancer,
)
from ..temporal_checks import scrub_vague_recency as _scrub_vague_recency
from ..cc_checks import (
    benign_incidental_leads,
    uncertain_mislabels_cancer,
    strip_liver_directed_therapy,
)

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], str]

# Cap the chart we feed so a 100K+ VistA dump doesn't blow the context. The
# normalized (CPRS-canonical) chart is section-organized and de-noised; the
# structured PSA / pathology blocks are appended verbatim because those are the
# highest-error surfaces and the deterministic extractors clean them best.
_CHART_CAP = 90_000


_NAMED_OPENER_RE = re.compile(
    r"\b[A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){0,3}\s+is\s+an?\s+"
    r"\d{1,3}[-\s]year[-\s]old\b")


def _collapse_double_opener(hpi: str) -> str:
    """If two '<Name> is a <N>-year-old' openers appear near the start (a
    prepend + the LLM's own opener), keep the second, richer one."""
    if not hpi:
        return hpi
    ms = list(_NAMED_OPENER_RE.finditer(hpi[:320]))
    if len(ms) >= 2:
        return hpi[ms[1].start():].lstrip()
    return hpi


def _build_prompt(chart: str, facts_block: str, psa_data: str,
                  pathology_data: str, prior_hpi: str,
                  name: str, age: str, sex: str) -> str:
    sex_word = "male" if (sex or "").lower().startswith("m") else \
        ("female" if (sex or "").lower().startswith("f") else "patient")
    opener = f"{name} is a {age}-year-old {sex_word}" if (name and age) else \
        (f"{name} is a {sex_word}" if name else "The patient")
    return f"""\
You are an expert urologist writing the CHIEF COMPLAINT (CC) and HISTORY OF
PRESENT ILLNESS (HPI) for today's clinic note. Read the ENTIRE chart below and
write both — cohesively and accurately, the way a careful clinician would after
reading the whole record.

================= SOURCE CHART (AUTHORITATIVE) =================
{chart}

================= PRIOR CLINICIAN NARRATIVE (high signal) =================
{prior_hpi or "(none)"}

================= PSA VALUES (authoritative lab list) =================
{psa_data or "(none)"}

================= PATHOLOGY (authoritative) =================
{pathology_data or "(none)"}

================= ADVISORY EXTRACTED FACTS (convenience only) =================
{facts_block}

CRITICAL — HOW TO USE THE ADVISORY FACTS:
The CHART is authoritative. The advisory facts were auto-extracted and MAY BE
WRONG. If any advisory item conflicts with the chart, TRUST THE CHART and ignore
the advisory item. In particular, do NOT state a treatment as completed if the
chart shows it was only discussed, planned, offered, or conditional ("salvage
radiation IF the PSA rises", "candidate for...", "we could consider...").

RULES:
- CHIEF COMPLAINT: a single concise line naming the primary ACTIVE problem / the
  documented reason for today's visit. Lead with the cancer or primary diagnosis;
  a radiology-benign incidental (simple cyst, adrenal myelolipoma/adenoma) never
  leads. Name a confirmed cancer as such — never "of uncertain significance".
- HPI: 1-3 flowing paragraphs — favor COMPLETE over brief; a careful clinician
  would not drop documented, clinically-relevant history to save space. Open the
  FIRST sentence with "{opener} who ..." and state the primary diagnosis in that
  first sentence — not an incidental problem (CKD, vitamin D, HTN, BPH).
- MUST INCLUDE (completeness contract) — cover EACH of the following THAT IS
  DOCUMENTED in the chart; do not omit a documented item, and do not invent one
  that is absent:
  * every active/relevant urologic cancer, each with its current status
    (on surveillance / treatment-naive / on treatment / post-treatment);
  * the PSA trajectory: the most-recent value WITH its date, plus the prior
    value(s) with dates that establish the direction (rising / stable / declining);
  * each documented treatment or procedure with its agent/type and date, and the
    current treatment status;
  * documented constitutional symptoms — e.g. UNINTENTIONAL WEIGHT LOSS, fatigue,
    night sweats, decreased appetite — when the record notes them;
  * current urologic symptom status as documented (LUTS/IPSS with the score,
    hematuria, erectile dysfunction and the therapies tried);
  * the documented reason for today's visit.
- GROUND EVERY FACT in the chart. Never invent or alter a date, PSA value,
  Gleason score / Grade Group, drug name, or procedure. Each event happened on
  its DOCUMENTED date (a biopsy/treatment on its report date, never a later
  clinic-visit copy-forward date). Report the HIGHEST documented Gleason as the
  grade. Use the EXACT drug documented (do not swap Lupron for Eligard).
- DISCONFIRMING EVIDENCE — reason over the whole picture, do not pattern-match:
  * A patient s/p radical prostatectomy with an UNDETECTABLE PSA has NO
    biochemical recurrence — do NOT assert salvage radiation, recurrence, or
    "rising PSA" unless the chart explicitly documents them as performed/true.
  * Do not infer a treatment from a risk factor (a positive margin does NOT mean
    radiation was given).
- TEMPORAL VALIDITY: a time-sensitive finding is true only AS OF its date. Write
  such findings DATED ("PSA 0.05 on 12 Jun 2026", "CT on 3 Mar 2026 showed no
  recurrence"). NEVER use vague recency ("recent", "recently", "recent MRI").
  The MOST RECENT dated result wins; never carry a stale status forward as current.
- AFFIRMATIVE ONLY: state what IS true and what happened. No hypotheticals, no
  "should he...", no recommendations here (the HPI is history only).
- No markdown, no bullet points, no meta-preamble.

Output ONLY a single JSON object, nothing else:
{{"chief_complaint": "<one line>", "hpi": "<1-2 paragraph HPI>"}}"""


def _repair_prompt(chart: str, facts_block: str, draft_cc: str, draft_hpi: str,
                   issues: list) -> str:
    issue_txt = "\n".join(f"  - {v}" for v in issues)
    return f"""\
Your CC/HPI has factual problem(s) against the documented chart:
{issue_txt}

Rewrite BOTH the chief complaint and the complete HPI, keeping everything already
correct and fixing the problems above. Use ONLY documented facts; the chart is
authoritative over any advisory extraction. Do NOT drop any documented,
clinically-relevant history while fixing the problems (keep every active cancer,
the dated PSA trajectory, documented treatments, constitutional symptoms, and
symptom status). Keep the "<NAME> is a <AGE>-year-old <sex> who ..." opener.

ADVISORY FACTS (may be wrong — defer to the chart):
{facts_block}

YOUR PREVIOUS CHIEF COMPLAINT:
{draft_cc}

YOUR PREVIOUS HPI:
{draft_hpi}

Output ONLY the corrected JSON object:
{{"chief_complaint": "...", "hpi": "..."}}"""


def _parse_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw.strip(),
                  flags=re.IGNORECASE | re.MULTILINE).strip()
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def _cc_defects(cc: str, chart: str, facts: Any) -> list:
    """CC-level grounding defects (reuse the shared cc_checks)."""
    out = []
    src = chart or ""
    try:
        if benign_incidental_leads(cc, src):
            out.append("the CC leads with a radiology-benign incidental though the "
                       "patient has an active primary — lead with the primary diagnosis")
        if uncertain_mislabels_cancer(cc, src):
            out.append("the CC calls a confirmed/treated cancer 'of uncertain "
                       "significance' — name the cancer")
    except Exception:  # noqa: BLE001
        pass
    if _has_cancer(facts):
        low = cc.lower()
        if not re.search(r"cancer|carcinoma|adenocarc|malign|\brcc\b|renal cell|"
                         r"tumou|gleason|grade group|urotheli|seminoma", low):
            out.append("the patient has a documented cancer but the CC does not name "
                       "it — center the CC on the cancer")
    return out


def compose_cc_hpi(
    facts: Any,
    raw_chart: str,
    normalized_chart: str,
    psa_data: str,
    pathology_data: str,
    psh_data: str,
    prior_hpi: str,
    patient_name: Optional[str],
    patient_age: Optional[Any],
    patient_sex: Optional[str],
    llm_call: LLMCallable,
    max_repair: int = 1,
) -> Optional[Dict[str, str]]:
    """Return {"cc": str, "hpi": str} from one holistic LLM pass, or None to fall
    back to the existing CC/HPI paths."""
    if os.environ.get("VAUCDA_CC_HPI_HOLISTIC", "1") != "1":
        return None
    if facts is None:
        return None
    try:
        # Prefer the normalized (CPRS-canonical) chart as the authoritative body;
        # it is section-organized and de-noised. Fall back to raw.
        chart = (normalized_chart or raw_chart or "")[:_CHART_CAP]
        if len(chart) < 200:
            return None
        facts_block = format_facts_for_prompt(facts)
        name = str(patient_name or "").strip()
        age = str(patient_age or "").strip()

        prompt = _build_prompt(chart, facts_block, psa_data or "",
                               pathology_data or "", prior_hpi or "",
                               name, age, patient_sex or "")
        obj = _parse_json((llm_call(prompt) or "").strip())
        if not obj:
            return None
        cc = (obj.get("chief_complaint") or obj.get("cc") or "").strip()
        hpi = (obj.get("hpi") or obj.get("history_of_present_illness") or "").strip()
        if not hpi or len(hpi) < 60:
            return None

        # verify -> single repair round covering BOTH sections
        repairs = 0
        while repairs < max_repair:
            issues = (_hpi_hard(hpi, chart) + _hpi_soft(hpi, facts, chart, psa_data or "")
                      + _cc_defects(cc, chart, facts))
            if not issues:
                break
            fixed = _parse_json(
                (llm_call(_repair_prompt(chart, facts_block, cc, hpi, issues)) or "").strip())
            if not fixed:
                break
            cc = (fixed.get("chief_complaint") or fixed.get("cc") or cc).strip()
            hpi = (fixed.get("hpi") or hpi).strip()
            repairs += 1
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Holistic CC/HPI failed, falling back: {e}")
        return None

    # --- LIGHT deterministic finishing on the HPI ---
    # Deliberately do NOT run the composer's aggressive scrubbers
    # (_scrub_unsupported_biopsy_claims / _strip_nonurologic_sentences): those
    # assume a deterministic skeleton and mangle chart-grounded prose — e.g. they
    # excise "underwent a prostate biopsy" mid-sentence when the structured
    # PATHOLOGY extraction is empty for a narrative-pathology patient. The holistic
    # HPI is already chart-grounded and HARD-verified, so only cosmetic cleanup +
    # the conservative PSA reconcilers run here.
    try:
        # Enforce the named opener FIRST, on the pristine LLM output, so a later
        # cleaner can't strip/alter the opener and trigger a wrong prepend.
        hpi = _ensure_named_opening(hpi, patient_name, patient_age, patient_sex)
        from .history_cleaners import clean_llm_commentary, _collapse_word_doubling
        hpi = clean_llm_commentary(hpi)
        hpi = _collapse_word_doubling(hpi)
        from .hpi_agent import _reconcile_psa_direction, _scrub_psa_hallucinations
        hpi = _reconcile_psa_direction(hpi, psa_data or "")
        hpi = _scrub_psa_hallucinations(hpi, psa_data or "")
        hpi = _collapse_word_doubling(hpi)
        hpi = _scrub_vague_recency(hpi)
        hpi = _collapse_double_opener(hpi)  # final safety net vs any doubled opener
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Holistic HPI light-finish partial: {e}")

    # HARD violations that survive -> unsafe to emit; fall back entirely.
    if _hpi_hard(hpi, chart):
        logger.info("[HOLISTIC] HPI hard violation survives; falling back to composer/v2")
        return None

    # --- deterministic finishing on the CC ---
    cc = strip_liver_directed_therapy(cc).strip().rstrip(".")
    if not cc:
        return None

    soft = _hpi_soft(hpi, facts, chart, psa_data or "")
    if soft:
        logger.info(f"[HOLISTIC] emitted with residual soft notes: {soft[:3]}")
    logger.info("[HOLISTIC] CC/HPI composed (LLM-first, chart-authoritative)")
    return {"cc": cc, "hpi": hpi}
