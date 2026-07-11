"""LLM-forward dated PSMA PET tracking with deterministic grounding.

For PSMA PET, clinical significance is the AVIDITY / scoring system (SUVmax,
PSMA-RADS), not lesion size — a small lesion can be avid and matter, which is
PET's advantage over CT. So a size trajectory is the wrong tool for PET; the
right one is a dated series of AVID DISEASE SITES + their SUVmax + the overall
impression, so serial PSMA PETs show response vs progression (SUV falling / sites
resolving, or SUV rising / new sites).

The LLM reads the PSMA PET material and returns one entry per dated study; every
entry is GROUNDED — its verbatim quote must be in the source, its date must
appear in the source, and each cited SUVmax must appear as an "SUV" value in the
source (so a mis-read like the statin "suvastatin 10" cannot become "SUV 10").
Flagged for provider verification; nothing here is authoritative.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], str]

_PSMA = re.compile(r"PSMA|PYLARIFY|piflufolastat|DCFPyL|Ga[-\s]?68|gallium|18F[-\s]?DCF",
                   re.IGNORECASE)
_PET = re.compile(r"\bPET\b|PET/CT", re.IGNORECASE)
_DATE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|"
                   r"sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}?,?\s*\d{4}\b", re.IGNORECASE)
# a real SUV value: \bSUV token (avoids "suvastatin") + optional of/=/: + number
_SUV_VAL = r"\bSUV(?:max|mean)?\b\s*(?:of|=|:)?\s*{n}"


@dataclass
class PsmaStudy:
    date_display: str
    date_key: str
    impression: str
    sites: List[str] = field(default_factory=list)
    dominant_suv: Optional[float] = None
    quote: str = ""


def build_psma_context(chart: str, max_chars: int = 14000) -> str:
    if not chart:
        return ""
    lines = chart.splitlines()
    keep = set()
    for i, ln in enumerate(lines):
        if (_PSMA.search(ln) and _PET.search(ln)) or _PSMA.search(ln) \
                or re.search(r"\bSUV(?:max|mean)?\b", ln, re.IGNORECASE):
            for j in range(max(0, i - 2), min(len(lines), i + 4)):
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


def _prompt(ctx: str) -> str:
    return f"""\
Summarize the patient's PSMA PET history from the material below — ONE entry per
DATED PSMA PET (or PSMA / PET-CT) study.

For each study, report:
  - date          (the STUDY date)
  - impression    (one short clause: e.g. "no distant disease", "avid disease at
                   <sites>", "response vs prior", "progression / new lesions")
  - sites         (each AVID disease site, with its SUVmax if given —
                   "left external iliac node (SUV 4.2)", "prostate bed (SUV 8)")
  - dominant_suv  (the single HIGHEST SUVmax reported in that study, as a number;
                   0 if no SUV is given)

RULES:
  - Significance is AVIDITY, not size — include a small avid lesion.
  - Use ONLY what is written. Do NOT invent SUV values, sites, or dates.
  - An "SUV" value is written as "SUV 30.8" / "SUV=30.8" / "SUVmax of 8". Do NOT
    treat drug names like "suvastatin" as an SUV.
  - "quote" MUST be copied VERBATIM from the text.

Output ONLY JSON (empty array if no PSMA PET):
{{"studies":[{{"date":"M/D/YYYY","impression":"...","sites":["..."],
              "dominant_suv":0.0,"quote":"..."}}]}}

PSMA PET MATERIAL:
{ctx}

Output the JSON now:"""


def _parse(raw: str) -> Optional[dict]:
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


def _date_key(disp: str) -> Optional[str]:
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", disp)
    if m:
        y = int(m.group(3)); y += 2000 if y < 50 else (1900 if y < 100 else 0)
        return f"{y}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    mon = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
           "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(?:\d{1,2},?\s*)?(\d{4})",
                  disp, re.IGNORECASE)
    if m:
        return f"{m.group(2)}-{mon[m.group(1)[:3].lower()]:02d}"
    return None


def _suv_in_source(num: float, source: str) -> bool:
    pat = _SUV_VAL.format(n=re.escape(f"{num:g}"))
    return bool(re.search(pat, source, re.IGNORECASE))


def _ground(st: dict, src_norm: str, source: str) -> Optional[PsmaStudy]:
    quote = str(st.get("quote", "")).strip()
    date_disp = str(st.get("date", "")).strip()
    impression = re.sub(r"\s+", " ", str(st.get("impression", "")).strip())
    qn = re.sub(r"\s+", " ", quote).strip().lower()
    if len(qn) < 6 or qn not in src_norm:            # provenance
        return None
    dk = _date_key(date_disp)
    if not dk:
        return None
    parts = re.findall(r"\d+", date_disp)
    if date_disp not in source and not (parts and all(p in source for p in parts[:2])):
        return None
    # dominant SUV must be a real SUV in the source (else null it, keep the study)
    dom = None
    try:
        v = float(st.get("dominant_suv") or 0)
        if v > 0 and _suv_in_source(v, source):
            dom = round(v, 1)
    except Exception:  # noqa: BLE001
        pass
    # keep only sites whose cited SUV (if any) is grounded
    sites = []
    for s in (st.get("sites") or []):
        s = re.sub(r"\s+", " ", str(s)).strip()
        if not s:
            continue
        sm = re.search(r"SUV\w*\s*(?:of|=|:)?\s*(\d+\.?\d*)", s, re.IGNORECASE)
        if sm and not _suv_in_source(float(sm.group(1)), source):
            continue
        sites.append(s[:70])
    return PsmaStudy(date_disp, dk, impression[:120], sites[:6], dom, quote[:90])


def extract_psma_series(chart: str, llm_call: LLMCallable) -> List[PsmaStudy]:
    ctx = build_psma_context(chart)
    if not ctx:
        return []
    try:
        data = _parse(llm_call(_prompt(ctx)))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"psma_pet_series LLM failed: {e}")
        return []
    if not data:
        return []
    src_norm = re.sub(r"\s+", " ", chart).lower()
    seen = {}
    for st in (data.get("studies") or []):
        if not isinstance(st, dict):
            continue
        g = _ground(st, src_norm, chart)
        if g and g.date_key not in seen:
            seen[g.date_key] = g
    return sorted(seen.values(), key=lambda s: s.date_key)


def render_psma_table(studies: List[PsmaStudy]) -> str:
    if not studies:
        return ""
    lines = []
    for st in reversed(studies):   # most recent first
        parts = [st.impression] if st.impression else []
        if st.sites:
            parts.append("; ".join(st.sites))
        elif st.dominant_suv:
            parts.append(f"SUVmax {st.dominant_suv}")
        lines.append(f"  {st.date_display:>12}  {' — '.join(parts)}".rstrip())
    # SUV trend across studies that report one
    suvs = [(s.date_display, s.dominant_suv) for s in studies if s.dominant_suv]
    trend = ""
    if len(suvs) >= 2:
        d = suvs[-1][1] - suvs[0][1]
        word = "rising" if d > 0 else ("falling" if d < 0 else "stable")
        trend = (f"\n  Dominant SUVmax {word}: {suvs[0][1]} ({suvs[0][0]}) "
                 f"-> {suvs[-1][1]} ({suvs[-1][0]})")
    return ("PSMA PET TRAJECTORY (auto-extracted — provider to VERIFY against the "
            "PET reports; significance is avidity/PSMA-RADS, not size):\n"
            + "\n".join(lines) + trend)
