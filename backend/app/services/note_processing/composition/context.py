"""ChartContext — everything the Assessment/Plan composer and the verifier see.

Built ONCE per Stage 2 call from: the raw/normalized chart, the Stage 1 note
(whose deterministic sections are the authoritative tables), the identified
notes (for the clinician's most recent HPI / Assessment / Plan, verbatim), the
fact ledger, the ADT scheduler verdict, the functional-status / life-expectancy
block, and the GraphRAG guideline passages.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_CHART_CAP = 90_000          # deepseek 64k-token context; the chart is the bulk
_PRIOR_NOTE_CAP = 3_000      # per clinician note (HPI + A + P)
_MAX_PRIOR_NOTES = 4

# Stage 1 section headers (plain and banner forms) whose bodies are DATA.
_TABLE_HEADERS = (
    "PSA CURVE", "PSA DOUBLING TIME", "ANDROGEN DEPRIVATION THERAPY (ADT)", "MEDICATIONS",
    "ALLERGIES", "PATHOLOGY RESULTS", "TESTOSTERONE", "ENDOCRINE LABS", "STONE RELATED LABS",
    "LABS", "IMAGING", "FUNCTIONAL STATUS", "PAST MEDICAL HISTORY", "PAST SURGICAL HISTORY",
    "FAMILY HISTORY", "SOCIAL HISTORY",
)
_HDR_RE = re.compile(r"(?m)^(?:=+\s*)?([A-Z][A-Z /&()\-]{2,60}?)\s*(?::|=+)\s*=*\s*$")


@dataclass
class ChartContext:
    chart: str = ""                       # normalized chart (capped)
    patient_banner: str = ""              # "Patient: ... | Visit: MM/DD/YYYY"
    visit_date: str = ""                  # MM/DD/YYYY
    prior_clinician_notes: str = ""       # most recent urology HPI/A/P, verbatim, newest first
    tables: Dict[str, str] = field(default_factory=dict)   # header -> Stage 1 section body
    facts_block: str = ""                 # format_facts_for_prompt(facts)
    adt_directive: str = ""               # scheduler verdict (arithmetic authority)
    adt_constraint: str = ""              # prompt-only guard when ADT is historical
    life_expectancy_block: str = ""       # age guardrail / Schonberg / ECOG block
    guidelines: str = ""                  # GraphRAG passages, "[query]\n..." blocks
    psa_values: List[float] = field(default_factory=list)
    chart_dates: set = field(default_factory=set)          # (y, m, d|None) tuples found in chart+tables

    # ---- rendering helpers -------------------------------------------------
    def tables_text(self, headers: Tuple[str, ...] = _TABLE_HEADERS, cap: int = 14_000) -> str:
        out = []
        for h in headers:
            body = self.tables.get(h)
            if body:
                out.append(f"{h}:\n{body.strip()}")
        return "\n\n".join(out)[:cap]


# ---------------------------------------------------------------------------
# Section parsing of the Stage 1 note
# ---------------------------------------------------------------------------
def split_stage1_sections(stage1_note: str) -> Dict[str, str]:
    """Header -> body for the Stage 1 note. Banner headers
    ('===== LABS =====') and plain headers ('PSA CURVE:') both count."""
    out: Dict[str, str] = {}
    if not stage1_note:
        return out
    hits = list(_HDR_RE.finditer(stage1_note))
    for i, m in enumerate(hits):
        name = re.sub(r"\s+", " ", m.group(1)).strip().upper()
        start = m.end()
        end = hits[i + 1].start() if i + 1 < len(hits) else len(stage1_note)
        body = stage1_note[start:end].strip("\n")
        if body.strip():
            out[name] = (out.get(name, "") + "\n" + body).strip("\n") if name in out else body
    return out


# ---------------------------------------------------------------------------
# Most recent clinician notes (verbatim backbone)
# ---------------------------------------------------------------------------
_NOTE_DATE_FMTS = ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%b %d,%Y")
_HPI_BLOCK_RE = re.compile(r"(?is)\bHPI\s*:\s*(.*?)(?=\n\s*(?:[A-Z][A-Z /&()\-]{3,}:|\Z))")
_AP_BLOCK_RE = re.compile(r"(?is)\b(?:ASSESSMENT(?:\s*(?:/|AND|&)\s*PLAN)?|A/P|IMPRESSION)\s*:\s*(.*?)(?=\n\s*(?:/es/|Signed|Receipt|Electronically)|\Z)")
_PLAN_BLOCK_RE = re.compile(r"(?is)\bPLAN\s*:\s*(.*?)(?=\n\s*(?:/es/|Signed|Receipt|Electronically|[A-Z][A-Z /&()\-]{3,}:)|\Z)")


def _note_dt(n: Dict[str, Any]) -> Optional[datetime]:
    d = (n.get("date") or "").strip()
    for f in _NOTE_DATE_FMTS:
        try:
            return datetime.strptime(d.split("@")[0].strip(), f)
        except Exception:  # noqa: BLE001
            continue
    return None


def recent_clinician_notes(gu_notes: List[Dict[str, Any]], max_notes: int = _MAX_PRIOR_NOTES) -> str:
    """The last few UROLOGY notes' HPI / Assessment / Plan, verbatim, newest
    first. These are the clinician's own synthesis and the composer's backbone."""
    cands = []
    for n in gu_notes or []:
        if not isinstance(n, dict):
            continue
        body = n.get("content") or ""
        if len(body) < 300 or not re.search(r"(?i)\bHPI\s*:|\bASSESSMENT|\bPLAN\s*:", body):
            continue
        if re.search(r"(?i)nurs(?:e|ing)\s+note|chart\s+check|telephone|phone\s+note", n.get("title") or ""):
            continue
        cands.append((_note_dt(n) or datetime.min, n))
    cands.sort(key=lambda t: t[0], reverse=True)
    blocks = []
    for dt, n in cands[:max_notes]:
        body = n.get("content") or ""
        parts = []
        hm = _HPI_BLOCK_RE.search(body)
        if hm:
            parts.append("HPI: " + re.sub(r"[ \t]+", " ", hm.group(1)).strip()[:1600])
        am = _AP_BLOCK_RE.search(body)
        if am:
            parts.append("ASSESSMENT/PLAN: " + re.sub(r"[ \t]+", " ", am.group(1)).strip()[:1600])
        else:
            pm = _PLAN_BLOCK_RE.search(body)
            if pm:
                parts.append("PLAN: " + re.sub(r"[ \t]+", " ", pm.group(1)).strip()[:1200])
        if parts:
            label = f"{(n.get('title') or 'UROLOGY').strip()} — {n.get('date') or 'undated'}"
            blocks.append(f"--- {label} ---\n" + "\n".join(parts)[:_PRIOR_NOTE_CAP])
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Grounding sets (dates, PSA values) used by the verifier
# ---------------------------------------------------------------------------
_MON = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE_RES = (
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b"),
    re.compile(r"\b(\d{1,2})/((?:19|20)\d{2})\b"),
    re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b"),
    re.compile(r"\b([A-Za-z]{3,9})\.?\s+((?:19|20)\d{2})\b"),
    re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b"),
)


def date_tuples(text: str) -> set:
    """All dates in `text` as (y, m, d) and their (y, m, None) month forms, plus
    bare (y, None, None) years for every date found."""
    out = set()
    if not text:
        return out
    for m in _DATE_RES[0].finditer(text):
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 50 else (y + 1900 if y < 100 else y)
        if 1 <= mo <= 12 and 1 <= d <= 31:
            out |= {(y, mo, d), (y, mo, None), (y, None, None)}
    for m in _DATE_RES[1].finditer(text):
        mo, y = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            out |= {(y, mo, None), (y, None, None)}
    for m in _DATE_RES[2].finditer(text):
        mo = _MON.get(m.group(1)[:3].lower())
        if mo:
            d, y = int(m.group(2)), int(m.group(3))
            out |= {(y, mo, d), (y, mo, None), (y, None, None)}
    for m in _DATE_RES[3].finditer(text):
        mo = _MON.get(m.group(1)[:3].lower())
        if mo:
            out |= {(int(m.group(2)), mo, None), (int(m.group(2)), None, None)}
    for m in _DATE_RES[4].finditer(text):
        out |= {(int(m.group(1)), int(m.group(2)), int(m.group(3))),
                (int(m.group(1)), int(m.group(2)), None), (int(m.group(1)), None, None)}
    return out


def psa_values_from_curve(psa_section: str) -> List[float]:
    vals = []
    for line in (psa_section or "").splitlines():
        m = re.search(r"(\d+\.\d+|\d+)\s*(?:H|L)?\s*$", line.strip())
        if m and re.search(r"\d{4}", line):
            try:
                vals.append(float(m.group(1)))
            except ValueError:
                pass
    return vals


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
def build_chart_context(
    stage1_note: str,
    clinical_document: str,
    gu_notes: List[Dict[str, Any]],
    non_gu_notes: Optional[List[Dict[str, Any]]],
    facts: Any,
    rag_content: Optional[str] = None,
    adt_directive: Optional[str] = None,
    adt_constraint: Optional[str] = None,
) -> ChartContext:
    from ..source_normalizers import normalize_to_cprs
    from ..patient_status_facts import format_facts_for_prompt
    ctx = ChartContext()
    raw = clinical_document or ""
    if not raw:
        # Stage 2 called without the chart: reconstruct from the note bodies.
        raw = "\n\n".join((n.get("content") or "") for n in (gu_notes or []) + list(non_gu_notes or [])
                          if isinstance(n, dict))
    try:
        norm = normalize_to_cprs(raw, "vista") or raw
    except Exception:  # noqa: BLE001
        norm = raw
    ctx.chart = norm[:_CHART_CAP]
    first = (stage1_note or "").splitlines()[0] if stage1_note else ""
    ctx.patient_banner = first if first.startswith("Patient:") else ""
    vm = re.search(r"\|\s*Visit:\s*(\d{1,2}/\d{1,2}/\d{4})", ctx.patient_banner) or \
        re.search(r"VISIT\s+DATE:\s*(\d{1,2}/\d{1,2}/\d{4})", raw[:400])
    ctx.visit_date = vm.group(1) if vm else datetime.now().strftime("%m/%d/%Y")
    ctx.prior_clinician_notes = recent_clinician_notes(gu_notes or [])
    ctx.tables = split_stage1_sections(stage1_note or "")
    try:
        ctx.facts_block = format_facts_for_prompt(facts) if facts is not None else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("facts block unavailable: %s", e)
    ctx.adt_directive = (adt_directive or "").strip()
    ctx.adt_constraint = (adt_constraint or "").strip()
    try:
        from ..agents.age_guardrail import build_age_guardrail_block
        ctx.life_expectancy_block = build_age_guardrail_block(stage1_note or "") or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("life-expectancy block unavailable: %s", e)
    ctx.guidelines = (rag_content or "").strip()
    ctx.psa_values = psa_values_from_curve(ctx.tables.get("PSA CURVE", ""))
    ctx.chart_dates = date_tuples(ctx.chart) | date_tuples(ctx.tables_text(cap=200_000)) | \
        date_tuples(ctx.patient_banner)
    return ctx
