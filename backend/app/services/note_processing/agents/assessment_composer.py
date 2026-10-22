"""Assessment finalization: deterministic garbage strip + completeness-repair.

The Assessment is composed by synthesize_assessment (which now carries the
primary-first / benign-incidental / no-metadata prompt rules). This layer adds
the two deterministic guards from the compose -> ledger -> repair pattern:

  1. strip_assessment_garbage — remove hallucinated scanner/technical-metadata
     sentences that leak into the prose (phantom size, kVp/mAs, CPT codes, raw
     reference numbers) — e.g. MOLINA's "...based on the 32 cm diameter phantom
     is 1616".
  2. finalize_assessment — a completeness-repair loop: if a documented cancer
     the patient HAS is not addressed anywhere in the Assessment, re-prompt the
     LLM with that organ + the note context until it is covered.

Safe-degrade: on any error the (garbage-stripped) input is returned unchanged.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional, Set

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], str]

# Scanner-DUMP artifacts: their presence means the WHOLE sentence/line is
# machine metadata and should be dropped entirely (e.g. MOLINA's "...based on the
# 32 cm diameter phantom is 1616").
_SCANNER_DUMP = re.compile(
    r"\bphantom\b|diameter\s+phantom|\bkVp\b|\bmAs\b|reconstruction\s+kernel|"
    r"SEE\s+NOTE\s+\d|\bslice\s+thickness\b|\bDLP\b|\bCTDIvol\b|mGy-?cm",
    re.IGNORECASE)
# Inline coding tokens that ride ALONG legitimate clinical prose — scrub just the
# token, keep the sentence (e.g. STARKS's "cystoscopy ... (CPT 52000) was
# normal; no repeat cystoscopy unless ..." must survive).
_INLINE_META = re.compile(
    r"\s*[\(\[]?\b(?:CPT|code)\s+\d{4,5}[\)\]]?", re.IGNORECASE)
# Back-compat: any garbage at all (used by external callers / audits).
_GARBAGE = re.compile(
    r"\bphantom\b|diameter\s+phantom|\bkVp\b|\bmAs\b|reconstruction\s+kernel|"
    r"\bcode\s+5\d{4}\b|\bCPT\s+\d{4,5}\b|SEE\s+NOTE\s+\d|\bslice\s+thickness\b|"
    r"\bDLP\b|\bCTDIvol\b", re.IGNORECASE)


def _scrub_inline(text: str) -> str:
    """Excise inline coding tokens (CPT/code NNNNN) without losing the prose."""
    out = _INLINE_META.sub("", text)
    # tidy orphaned empty parens/space left behind
    out = re.sub(r"\(\s*\)|\[\s*\]", "", out)
    return re.sub(r"\s{2,}", " ", out).replace(" .", ".").replace(" ,", ",")

_ORGAN_WORDS = {
    "prostate": ["prostate", "prostatic"],
    "renal": ["renal", "kidney", "nephr"],
    "bladder": ["bladder", "urothelial"],
    "penile": ["penile", "penis"],
    "testicular": ["testicular", "testis", "testicle"],
    "upper_tract": ["ureter", "renal pelvis", "upper tract"],
    "adrenal": ["adrenal"],
}


def strip_assessment_garbage(text: str) -> str:
    """Drop sentences that are scanner-metadata dumps; inline-scrub coding tokens
    (CPT/code) from otherwise-clinical sentences so their prose survives."""
    if not text:
        return text
    sents = re.split(r"(?<=[.!?])\s+", text)
    kept = [_scrub_inline(s) for s in sents if not _SCANNER_DUMP.search(s)]
    out = " ".join(s for s in kept if s.strip()).strip()
    return re.sub(r"\s{2,}", " ", out)


def strip_garbage_lines(text: str) -> str:
    """For line/bullet-structured text (e.g. Plan): drop whole lines that are
    scanner-metadata dumps, but inline-scrub coding tokens (CPT/code) from
    legitimate clinical bullets so the instruction survives."""
    if not text:
        return text
    out = []
    for ln in text.splitlines():
        if _SCANNER_DUMP.search(ln):
            continue
        out.append(_scrub_inline(ln))
    return "\n".join(out)


def required_cancer_organs(patient_facts: Any) -> Set[str]:
    """The organs the Assessment MUST address — the patient's confirmed cancers,
    from the verified problem list (non-prostate GU cancers + prostate when
    cancer_status confirms it)."""
    orgs: Set[str] = set()
    for d in (getattr(patient_facts, "other_gu_diagnoses", None) or []):
        if getattr(d, "category", "") == "cancer" and getattr(d, "organ", ""):
            orgs.add(d.organ)
    if (getattr(patient_facts, "cancer_status", "") or "").upper() in ("PRESENT", "TREATED"):
        orgs.add("prostate")
    return orgs


def _uncovered(text: str, organs: Set[str]) -> Set[str]:
    lc = text.lower()
    return {o for o in organs
            if not any(w in lc for w in _ORGAN_WORDS.get(o, [o]))}


def _repair_prompt(text: str, stage1_note: str, missing: Set[str]) -> str:
    return f"""\
The Assessment below did NOT address the patient's documented {sorted(missing)}
cancer(s). Rewrite the COMPLETE Assessment (4-8 sentences) so every one of the
patient's cancers is addressed, leading with the primary. Use ONLY facts from
the note context; do not invent grades/stages/PSA. Do not add scanner or
procedure-code metadata.

NOTE CONTEXT (for the facts):
{stage1_note[:6000]}

CURRENT ASSESSMENT (incomplete):
{text}

Rewrite the complete Assessment now:"""


def finalize_assessment(
    text: str,
    stage1_note: str,
    patient_facts: Any,
    llm_call: Optional[LLMCallable] = None,
    max_repair: int = 1,
) -> str:
    """Garbage-strip, then repair cancer-coverage completeness."""
    text = strip_assessment_garbage(text)
    if not text or patient_facts is None or llm_call is None:
        return text
    try:
        required = required_cancer_organs(patient_facts)
        repairs = 0
        while required and repairs < max_repair:
            missing = _uncovered(text, required)
            if not missing:
                break
            new = (llm_call(_repair_prompt(text, stage1_note, missing)) or "").strip()
            new = strip_assessment_garbage(new)
            if new and len(new) > 40:
                text = new
            repairs += 1
        still = _uncovered(text, required) if required else set()
        if still:
            logger.info(f"[ASMT] cancer(s) still unaddressed after repair: {sorted(still)}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Assessment finalize error (kept stripped text): {e}")
    return text
