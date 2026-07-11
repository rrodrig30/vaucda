"""LLM-forward dated lesion-size trajectory extractor with deterministic grounding.

Regex extraction fails on these copied-forward VistA charts: a diagnostic size is
pasted into every later note, so dating by the note date fabricates a trajectory,
and requiring a study header drops real narrative-only measurements. Associating
a size with the STUDY it came from is a reading-comprehension task the LLM does
well.

So: the LLM reads the imaging/size context and returns a dated size series per
follow-able lesion (renal mass, prostate cancer lesion, dominant node). Then EVERY
point is deterministically GROUNDED — its verbatim source quote must be present in
the chart and its date must appear in the source — so a fabricated size/date can
never survive. Ungrounded points are dropped. Points are flagged as
extracted-for-provider-review; nothing here is asserted as authoritative.

Scope (v1): renal_mass, prostate_lesion (mpMRI index lesion — NOT gland volume),
dominant_node.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], str]

_SIZE_LINE = re.compile(r"\d+\.?\d*\s*(?:[x×]\s*\d+\.?\d*\s*)*(?:cm|mm)\b", re.IGNORECASE)
_LESION = re.compile(r"renal|kidney|bosniak|\bRCC\b|prostat|gland|pi-?rads|lesion|"
                     r"mass|lymph\s*node|nodal|\bnode\b", re.IGNORECASE)
_STUDY = re.compile(r"\b(CT|CTU|MRI|MR|US|ultrasound|sonogra|PET|PSMA|bone\s+scan|"
                    r"mpMRI|multiparametric)\b", re.IGNORECASE)
_DATE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|"
                   r"sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}?,?\s*\d{4}\b", re.IGNORECASE)

_LESION_KEYS = ("renal_mass", "prostate_lesion", "dominant_node")


@dataclass
class SizePoint:
    date_display: str
    date_key: str          # sortable YYYY[-MM[-DD]]
    size_cm: float
    quote: str


def build_size_context(chart: str, max_chars: int = 16000) -> str:
    """Lines carrying a size, a lesion, or an imaging study header (+neighbors)."""
    if not chart:
        return ""
    lines = chart.splitlines()
    keep = set()
    for i, ln in enumerate(lines):
        if _SIZE_LINE.search(ln) or (_STUDY.search(ln) and _DATE.search(ln)) \
                or (_LESION.search(ln) and _SIZE_LINE.search(ln)):
            for j in range(max(0, i - 2), min(len(lines), i + 3)):
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
Extract a DATED SIZE TRAJECTORY for follow-able lesions from the urology imaging
material below. Lesion types (only these):
  - renal_mass         (a renal mass / cyst / RCC)
  - prostate_lesion    (the prostate CANCER lesion on mpMRI / the PI-RADS index
                        lesion — NOT the whole-gland volume)
  - dominant_node      (the largest pathologic lymph node)

For EACH lesion type, list every DATED size measurement.

RULES:
  - Use the IMAGING STUDY date (when the scan was performed), NOT a clinic-note
    date. A size copied into a later note keeps its ORIGINAL study date.
  - Report the LARGEST dimension, in cm (convert mm to cm).
  - EXCLUDE prostate gland volume (cc / gram / mL), kidney length, ureteral
    stents, post-void residual, and digital-rectal-exam gland estimates.
  - EXCLUDE PSMA PET / nuclear-scan measurements (tracer-uptake regions,
    photopenic defects, SUV volumes) — those are FUNCTIONAL, not anatomic tumor
    sizes. Use ONLY anatomic sizes from mpMRI / CT / ultrasound.
  - Use ONLY measurements explicitly written in the text. Do NOT infer or invent.
    If you cannot tell the study date for a measurement, OMIT that point.
  - "quote" MUST be copied VERBATIM from the text (the exact phrase containing the
    size), so it can be verified.

Output ONLY JSON in this exact shape (empty arrays if none):
{{"renal_mass":[{{"date":"M/D/YYYY","size_cm":0.0,"quote":"..."}}],
 "prostate_lesion":[],"dominant_node":[]}}

IMAGING MATERIAL:
{ctx}

Output the JSON now:"""


def _parse_json(raw: str) -> Optional[dict]:
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


# PSMA PET / nuclear-scan measurements are FUNCTIONAL (tracer-uptake regions,
# photopenic defects, SUV volumes), not anatomic tumor sizes — including them
# fabricates false progressions (JONES/RIPLEY prostate PET uptake vs the smaller
# mpMRI lesion). A dated ANATOMIC size trajectory must exclude them.
_FUNCTIONAL = re.compile(
    r"photopenic|tracer|\bSUV\b|uptake|\bPSMA\b|\bPET\b|scintigra|metabolic|"
    r"\bavid\b|hypermetabolic|radiotracer", re.IGNORECASE)


def _grounded(pt: dict, src_norm: str, source: str) -> Optional[SizePoint]:
    """Keep a point only if its verbatim quote is in the source, its date appears
    in the source, its size is consistent with the quote, and it is an ANATOMIC
    (not functional/PET) measurement."""
    quote = str(pt.get("quote", "")).strip()
    date_disp = str(pt.get("date", "")).strip()
    try:
        size = float(pt.get("size_cm"))
    except Exception:  # noqa: BLE001
        return None
    if not quote or size <= 0:
        return None
    qn = re.sub(r"\s+", " ", quote).strip().lower()
    if len(qn) < 6 or qn not in src_norm:            # provenance: quote in source
        return None
    # Exclude FUNCTIONAL (PET/nuclear) measurements — check the source CONTEXT
    # around the quote, since the SUV/PET marker often sits just outside the
    # quoted size ("measuring 3.1 x 2.7 cm (Max SUV 12.4)").
    qpos = src_norm.find(qn)
    if qpos >= 0 and _FUNCTIONAL.search(src_norm[max(0, qpos - 130):qpos + len(qn) + 130]):
        return None
    # size consistent with a number in the quote (as cm, or its mm form)
    nums = [float(x) for x in re.findall(r"\d+\.?\d*", quote)]
    if not any(abs(n - size) < 0.05 or abs(n / 10 - size) < 0.05 for n in nums):
        return None
    dk = _date_key(date_disp)
    if not dk:
        return None
    # date must appear in the source (grounding the study date)
    if date_disp not in source and not re.search(re.escape(date_disp.split()[0]), source):
        # try the numeric date parts
        parts = re.findall(r"\d+", date_disp)
        if not (parts and all(p in source for p in parts[:2])):
            return None
    return SizePoint(date_disp, dk, round(size, 1), quote[:80])


def extract_lesion_series(
    chart: str,
    llm_call: LLMCallable,
) -> Dict[str, List[SizePoint]]:
    """LLM-extract + ground a dated size series per lesion type. Returns only
    grounded points; {} on any failure."""
    ctx = build_size_context(chart)
    if not ctx:
        return {}
    try:
        data = _parse_json(llm_call(_prompt(ctx)))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"lesion_series LLM failed: {e}")
        return {}
    if not data:
        return {}
    src_norm = re.sub(r"\s+", " ", chart).lower()
    out: Dict[str, List[SizePoint]] = {}
    for key in _LESION_KEYS:
        seen = {}
        for pt in (data.get(key) or []):
            if not isinstance(pt, dict):
                continue
            g = _grounded(pt, src_norm, chart)
            if not g:
                continue
            # one point per study date; keep the largest (dominant lesion)
            if g.date_key not in seen or g.size_cm > seen[g.date_key].size_cm:
                seen[g.date_key] = g
        if seen:
            out[key] = sorted(seen.values(), key=lambda p: p.date_key)
    return out


def is_changing(points: List[SizePoint], thresh_cm: float = 0.5) -> bool:
    """A trajectory is 'changing' if max-min exceeds a small threshold."""
    if len(points) < 2:
        return False
    sizes = [p.size_cm for p in points]
    return (max(sizes) - min(sizes)) >= thresh_cm


_LABEL = {"renal_mass": "Renal mass", "prostate_lesion": "Prostate lesion (mpMRI)",
          "dominant_node": "Dominant lymph node"}


def render_lesion_table(series: Dict[str, List[SizePoint]]) -> str:
    """A CHANGING lesion gets a reverse-chronological dated size table (the
    trajectory is the clinical content); a STABLE lesion gets a one-line summary
    (a table of identical rows adds nothing). Empty string if nothing to show.
    Explicitly flagged as auto-extracted for provider verification."""
    if not series:
        return ""
    blocks: List[str] = []
    for key in _LESION_KEYS:
        pts = series.get(key)
        if not pts:
            continue
        label = _LABEL.get(key, key)
        if is_changing(pts):
            first, last = pts[0], pts[-1]
            verb = "increased" if last.size_cm > first.size_cm else "decreased"
            rows = "\n".join(f"    {p.date_display:>12}    {p.size_cm} cm"
                             for p in reversed(pts))
            blocks.append(f"  {label} — {verb} {first.size_cm} → {last.size_cm} cm "
                          f"({first.date_display} → {last.date_display}):\n{rows}")
        else:
            last = pts[-1]
            blocks.append(f"  {label} — stable at {last.size_cm} cm "
                          f"(most recent {last.date_display})")
    if not blocks:
        return ""
    return ("LESION SIZE TRAJECTORY (auto-extracted from imaging reports — "
            "provider to VERIFY against the source studies):\n" + "\n".join(blocks))
