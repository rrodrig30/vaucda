"""Shared temporal-validity checks for the narrative note sections.

A clinical finding is true only AS OF the date it was reported — a "no
recurrence" CT is a point-in-time fact, and NED / stable / on-treatment can
reverse. Prior documentation is treated as timelessly true, which is where the
HPI, Assessment and Plan go wrong. These checks enforce the discernment
deterministically (the LLM applies it inconsistently):

  * NO VAGUE RECENCY — "recent" / "recently" / "recent MRI/CT" is banned; the
    actual DATE must be used.
  * VOLATILE-MUST-BE-DATED — a point-in-time status (NED / no recurrence /
    stable / remission / on ADT) must carry its as-of date.
  * LATEST-OBSERVATION-WINS — the most-recent PSA cited must be the newest value;
    an asserted current disease-free state must not contradict a later
    progression / recurrence in the timeline.

Assertion class (durable vs volatile) + source tier live on
clinical_timeline.TimelineEvent; this module consumes them via the facts object.
"""
from __future__ import annotations

import logging
import re
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

_UNI_SPACE = re.compile("[\u00a0\u2000-\u200a\u202f\u205f\u3000]")


def norm(text: str) -> str:
    """Normalize unicode spaces (LLMs emit narrow/thin/no-break spaces)."""
    return _UNI_SPACE.sub(" ", text or "")


def sentences(text: str) -> List[str]:
    return re.split(r"(?<=[.!?])\s+", text or "")


DATE_IN_SENT = re.compile(
    r"\b(?:19|20)\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|"
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}",
    re.IGNORECASE)
VAGUE_RECENCY = re.compile(r"\b(?<!most )(?:recent|recently|lately|newly)\b", re.IGNORECASE)
VOLATILE_STATUS = re.compile(
    r"no\s+evidence\s+of\s+(?:disease|recurren|malignan)|\bNED\b|"
    r"no\s+(?:recurren|residual|metasta|progression)|stable\s+disease|"
    r"in\s+remission|\bremission\b|biochemical\s+control|disease[-\s]free|"
    r"complete\s+response|"
    r"(?:on|continues\s+on|remains\s+on|currently\s+on)\s+"
    r"(?:continuous\s+|active\s+)?(?:ADT|androgen\s+deprivation|leuprolide|eligard|"
    r"lupron|degarelix|abiraterone|enzalutamide|apalutamide|darolutamide)",
    re.IGNORECASE)

_MON3 = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_PROGRESSED = ("recurren", "mcrpc", "castrat", "progress", "metasta")
_DISEASE_FREE = re.compile(
    r"\bNED\b|no\s+(?:evidence\s+of\s+)?recurren|disease[-\s]free|complete\s+response|"
    r"no\s+metasta", re.IGNORECASE)


def temporal_violations(text: str) -> List[str]:
    viol: List[str] = []
    for s in sentences(text):
        dated = bool(DATE_IN_SENT.search(s))
        if VAGUE_RECENCY.search(s):
            viol.append("replace vague recency ('recent' / 'recently' / 'recent "
                        "MRI/CT') with the actual DATE of the study or result")
        if VOLATILE_STATUS.search(s) and not dated:
            viol.append("a point-in-time status (NED / no recurrence / stable / on "
                        "ADT) is stated without its as-of DATE — add the date it was "
                        "observed (e.g. 'no recurrence on CT of <date>')")
    return list(dict.fromkeys(viol))


def scrub_vague_recency(text: str) -> str:
    """Guarantee no bare 'recent/recently' survives in an UNDATED sentence (keep
    'most recent'); the date is preferred, but the vague wording must never ship."""
    out = []
    for s in sentences(text):
        if VAGUE_RECENCY.search(s) and not DATE_IN_SENT.search(s):
            s = VAGUE_RECENCY.sub("", s)
            s = re.sub(r"\s{2,}", " ", s).replace(" ,", ",").replace(" .", ".")
        out.append(s.strip())
    return " ".join(x for x in out if x)


def psa_pairs(psa_data: str) -> List[Tuple[str, float]]:
    pairs = []
    for m in re.finditer(
            r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})[^\n]*?(\d+\.\d+)", psa_data or ""):
        mon = _MON3.get(m.group(1)[:3].lower())
        if mon:
            pairs.append((f"{m.group(3)}-{mon:02d}-{int(m.group(2)):02d}", float(m.group(4))))
    return pairs


def psa_section(note: str) -> str:
    """The PSA CURVE block from a rendered note (for latest-PSA checks)."""
    m = re.search(r"(?ims)^PSA\s+CURVE:\s*(.*?)(?=\n[A-Z][A-Za-z /]{2,40}:\s|\Z)", note or "")
    return m.group(1) if m else ""


def latest_wins_violations(text: str, facts: Any, psa_data: str) -> List[str]:
    viol: List[str] = []
    pairs = psa_pairs(psa_data)
    if len(pairs) >= 2:
        latest = max(pairs, key=lambda p: p[0])[1]
        m = re.search(r"(?:most\s+recent|current|latest)\s+(?:serum\s+)?"
                      r"(?:prostate[\s-]specific\s+antigen|psa)[^.\n]*?(\d+\.\d+)",
                      norm(text), re.IGNORECASE)
        if m and abs(float(m.group(1)) - latest) > 0.011:
            viol.append(f"the text calls {m.group(1)} the most-recent PSA, but the "
                        f"LATEST documented PSA is {latest:g} — the newest result wins")
    staging = [e for e in (getattr(facts, "clinical_timeline", None) or [])
               if getattr(e, "event_type", "") == "STAGING_DECISION" and getattr(e, "date_key", "")]
    if staging:
        latest_ev = max(staging, key=lambda e: e.date_key)
        blob = f"{getattr(latest_ev, 'modality', '')} {getattr(latest_ev, 'detail', '')}".lower()
        if any(k in blob for k in _PROGRESSED) and _DISEASE_FREE.search(text):
            viol.append(f"the LATEST documented disease state ({latest_ev.date_display}: "
                        f"{latest_ev.modality}) indicates progression/recurrence, but the "
                        f"text asserts disease-free/no-recurrence — reconcile to the latest state")
    return viol


def _repair_prompt(text: str, viol: List[str], section: str) -> str:
    issues = "\n".join(f"  - {v}" for v in viol)
    return f"""\
The {section} below has temporal-validity problem(s):
{issues}

Rewrite it fixing ONLY these: render time-sensitive findings as DATED
observations (e.g. "no recurrence on CT of <date>"); never use vague recency
("recent"/"recently"); present the MOST RECENT result as current; do not assert
a stale point-in-time status. Keep everything else exactly as written.

{section.upper()}:
{text}

Rewrite it now:"""


def finalize_temporal(
    text: str,
    facts: Any,
    psa_data: str = "",
    llm_call: Optional[Any] = None,
    section: str = "note section",
    max_repair: int = 1,
) -> str:
    """Deterministic scrub of vague recency + an optional repair loop for
    volatile-must-be-dated / latest-wins. Safe-degrade: returns the scrubbed text
    on any error or when disabled."""
    import os
    if not text or os.environ.get("VAUCDA_TEMPORAL_AP", "1") != "1":
        return text
    text = scrub_vague_recency(text)
    if facts is None:
        return text
    try:
        repairs = 0
        while llm_call is not None and repairs < max_repair:
            viol = temporal_violations(text) + latest_wins_violations(text, facts, psa_data or "")
            if not viol:
                break
            new = (llm_call(_repair_prompt(text, viol, section)) or "").strip()
            if new and len(new) > 40:
                text = scrub_vague_recency(new)
            repairs += 1
        residual = temporal_violations(text) + latest_wins_violations(text, facts, psa_data or "")
        if residual:
            logger.info(f"[TEMPORAL:{section}] residual: {residual}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"finalize_temporal({section}) error: {e}")
    return text
