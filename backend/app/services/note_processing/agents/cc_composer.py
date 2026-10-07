"""LLM-forward Chief-Complaint refiner (verify-and-repair the deterministic CC).

The legacy synthesize_cc() AUTHORS the CC through a deterministic cascade
(phase-driven templates, injection reframe, PMH-derive). When the upstream
verdict is right that cascade produces a *specific* CC (metastatic
hormone-sensitive, biochemically recurrent, s/p brachytherapy). When it is wrong
it prints a contradictory CC verbatim — the canonical failure: a single
historical Eligard (10/2022) + completed radiation made the phase classifier say
ON_INITIAL_TREATMENT and it emitted "...on androgen deprivation therapy for
scheduled Eligard injection" for a patient in post-treatment surveillance
(JELLSEY).

Rather than compose from scratch (which loses the cascade's hard-won
specificity and can swap drug names), this REFINES the deterministic CC: the LLM
keeps it verbatim UNLESS it contradicts the fact ledger / visit narrative
(wrong treatment framing, benign-incidental-led, or a resected cancer called
"uncertain significance"), in which case it minimally rewrites. A deterministic
verifier (shared with eval/audit_cc) then rejects any output that is worse than
the seed, so the refiner can only improve or keep.

Safe-degrade: disabled (VAUCDA_CC_COMPOSER=0), empty output, or any exception ->
return the seed CC unchanged.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, List, Optional

from ..cc_checks import benign_incidental_leads, uncertain_mislabels_cancer
from ..patient_status_facts import format_facts_for_prompt

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], str]

_CANCER_KW = ("prostate", "renal", "kidney", "bladder", "penile", "penis",
              "testic", "urothelial", "adenocarcinoma", "carcinoma", "rcc",
              "cancer", "malignan", "nephrectomy", "cystectomy", "seminoma")

_VISIT_MARKER = re.compile(
    r"HISTORY OF PRESENT ILLNESS|REASON FOR|CHIEF COMPLAINT|presenting|returns?\s+for|"
    r"here\s+for|follow[\s-]?up|interval\s+history|s/p\b|PSA\s+check|injection|"
    r"surveillance|biochemical", re.IGNORECASE)

# Treatment-framing language in the seed CC — the ONLY thing the refiner is
# allowed to change (in either direction: a wrongly-surveillance CC for a patient
# on active ADT, or a wrongly-on-treatment CC for a post-treatment patient). If
# the seed carries none of this (and has no defect), the refiner keeps it
# verbatim, so a clean specific CC (e.g. "metastatic prostate cancer") is never
# padded or expanded.
_FRAMING = re.compile(
    r"injection|androgen\s+deprivation|\bADT\b|on\s+treatment|during\s+treatment|"
    r"surveillance|after\s+radiation|after\s+prostatectomy|after\s+brachytherapy|"
    r"brachytherapy|\bs/p\b|scheduled|active\s+surveillance", re.IGNORECASE)


def _visit_context(chart: str, max_chars: int = 4500) -> str:
    if not chart:
        return ""
    lines = chart.splitlines()
    keep = set()
    for i, ln in enumerate(lines):
        if _VISIT_MARKER.search(ln):
            for j in range(max(0, i - 1), min(len(lines), i + 4)):
                keep.add(j)
    if not keep:
        return ""
    out, prev = [], -2
    for i in sorted(keep):
        if i != prev + 1:
            out.append("...")
        out.append(lines[i])
        prev = i
    return "\n".join(out)[:max_chars]


def _has_documented_cancer(facts: Any) -> bool:
    if (getattr(facts, "cancer_status", "") or "").upper() in ("PRESENT", "TREATED"):
        return True
    return any(getattr(d, "category", "") == "cancer"
               for d in (getattr(facts, "other_gu_diagnoses", None) or []))


def _defects(cc: str, facts: Any, source: str) -> List[str]:
    """Reliable, source-grounded CC defects. Empty list == acceptable."""
    v: List[str] = []
    if benign_incidental_leads(cc, source):
        v.append("leads with a radiology-benign incidental (adrenal "
                 "myelolipoma/adenoma or simple cyst)")
    if uncertain_mislabels_cancer(cc, source):
        v.append("calls a resected/established renal or bladder cancer 'of "
                 "uncertain significance'")
    if _has_documented_cancer(facts) and not any(k in cc.lower() for k in _CANCER_KW):
        v.append("does not name the patient's documented urologic cancer")
    return v


def _prompt(ledger: str, visit_ctx: str, seed_cc: str) -> str:
    return f"""\
You are a urologist reviewing the one-line CHIEF COMPLAINT drafted for today's
clinic note. Your job is to KEEP the draft as-is unless it contradicts the
record, in which case you minimally correct it. Output only the final CC line —
no preamble, no explanation.

{ledger}

VISIT NARRATIVE (today's reason for visit / interval history):
{visit_ctx or "(not found)"}

DRAFT CHIEF COMPLAINT:
{seed_cc}

Keep the DRAFT verbatim UNLESS one of these is true — then rewrite minimally:
1. TREATMENT FRAMING contradicts the record: the draft says the patient is on
   ADT / here for a scheduled injection, but CURRENT_TREATMENT_STATUS and the
   VISIT NARRATIVE show definitive treatment (radiation/prostatectomy) is
   COMPLETED and there is no active/scheduled injection this visit -> reframe as
   post-treatment surveillance ("Follow-up after radiation therapy for prostate
   cancer"). (CURRENT_PHASE is only a hint and may be stale.)
   Conversely, if the narrative shows an injection today / ADT ACTIVE, KEEP the
   injection framing.
2. A radiology-BENIGN incidental (adrenal myelolipoma/adenoma, simple cyst)
   leads the CC -> lead with the active problem instead.
3. A resected/established renal or bladder cancer is called "of uncertain
   significance" -> name the carcinoma.

If NONE of the three apply, output the DRAFT EXACTLY as given — do NOT add
symptoms or problems (e.g. incontinence, hematuria), do NOT expand or reword.
When you DO correct treatment framing, ADD/change only the framing — PRESERVE
grounded detail already in the draft (do not drop "after radiation therapy" when
adding an injection). Keep all specificity and EXACT names (metastatic
hormone-sensitive / castration-resistant, biochemically recurrent, s/p
brachytherapy, the exact ADT drug — do NOT substitute Lupron for Eligard).

Final CC line:"""


def _clean(cc: str) -> str:
    for ln in (cc or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        ln = re.sub(r"^(?:CC|Chief\s+Complaint|Final\s+CC[^:]*)\s*[:\-]\s*", "",
                    ln, flags=re.IGNORECASE)
        ln = re.sub(r"\*\*(.*?)\*\*", r"\1", ln).strip().strip('"')
        return ln
    return ""


def refine_cc(
    seed_cc: str,
    facts: Any,
    clinical_document: str,
    llm_call: LLMCallable,
) -> str:
    """Return a CC that is the deterministic seed, improved only where it
    contradicts the ledger/visit. Never returns something worse than the seed."""
    if os.environ.get("VAUCDA_CC_COMPOSER", "1") != "1":
        return seed_cc
    if not seed_cc or facts is None:
        return seed_cc
    source = clinical_document or ""
    seed_defects = _defects(seed_cc, facts, source)
    try:
        ledger = format_facts_for_prompt(facts)
        visit_ctx = _visit_context(clinical_document)
        out = _clean(llm_call(_prompt(ledger, visit_ctx, seed_cc)))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"CC refiner failed, keeping seed: {e}")
        return seed_cc
    if not out:
        return seed_cc
    # Only accept a rewrite when the seed was actually a candidate for one — it
    # had a deterministic defect OR carried treatment-framing language. This stops
    # the refiner from padding/expanding a clean specific seed (BARRERA
    # "metastatic prostate cancer ..." gaining "urinary incontinence"; FRAGA
    # "Urology follow-up" expanding into an invented CC).
    if out.strip().lower() != seed_cc.strip().lower() \
            and not seed_defects and not _FRAMING.search(seed_cc):
        logger.info("[CC] refiner rewrite rejected (clean non-framing seed); keeping seed")
        return seed_cc
    # Never accept an output that introduces a NEW deterministic defect.
    if len(_defects(out, facts, source)) > len(seed_defects):
        logger.info("[CC] refiner output rejected (new defect); keeping seed")
        return seed_cc
    if out.strip().lower() != seed_cc.strip().lower():
        logger.info(f"[CC] refined: {seed_cc!r} -> {out!r}")
    try:
        from .cc_agent import _apply_terminology
        out = _apply_terminology(out)
    except Exception:  # noqa: BLE001
        pass
    return out
