"""
Clinical Timeline Extractor + Phase Classifier.

This module is the structured-state foundation the CC / HPI / Assessment /
Plan agents anchor to. It replaces the prior approach where each agent
inferred chronology from raw prose — which failed when the prose came
from prior-visit notes written before a major treatment change (e.g.
mCRPC restart of ADT after the first 2-year course completed).

What the module produces
------------------------
1. ``extract_clinical_timeline(raw_text, today) -> List[TimelineEvent]``
   Scans the raw clinician-written text for dated clinical events and
   emits a chronologically-sorted timeline. Event categories include
   DIAGNOSIS, TREATMENT_STARTED / COMPLETED / RESTARTED / DECLINED,
   STAGING_DECISION (metastatic, castration-resistant, biochemical
   recurrence), PATHOLOGY, IMAGING, PROCEDURE (cystoscopy, urodynamics,
   biopsy, TURBT, etc.), LAB_TREND, and VISIT.

2. ``classify_current_phase(timeline, today) -> str``
   Deterministic state-machine over the sorted timeline that returns one
   of: TREATMENT_NAIVE | ON_INITIAL_TREATMENT | POST_TREATMENT_SURVEILLANCE
   | BIOCHEMICAL_RECURRENCE | SALVAGE_OR_RESTART
   | METASTATIC_HORMONE_SENSITIVE | METASTATIC_CASTRATION_RESISTANT
   | PROGRESSION | UNCERTAIN.

3. ``detect_current_active_treatments(raw_text) -> List[str]``
   Captures the meds the patient is currently taking, anchored to the
   most-recent encounter's medication list when present.

4. ``extract_procedure_findings(raw_text) -> List[ProcedureFinding]``
   Surfaces key findings from cystoscopy, urodynamics, and biopsy /
   pathology procedures — these drive clinical decisions and were
   frequently missing from synthesized output.

5. ``format_timeline_for_prompt(...)`` rendering helpers used by
   ``patient_status_facts.format_facts_for_prompt``.

Safety properties
-----------------
- Negation guard reused from patient_status_facts: a "no evidence of
  recurrence" sentence does NOT produce a BIOCHEMICAL_RECURRENCE event.
- Prostate-cancer context gate from patient_status_facts: an event
  must sit within 300 chars of a prostate-cancer marker to be treated
  as a urologic event. Dermatology cryotherapy etc. cannot enter the
  timeline.
- Dedup: events that share (date_key, category, modality) collapse to
  one entry. The same fact mentioned across many prior notes does not
  inflate the timeline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Tuple

from .patient_status_facts import (
    _PROSTATE_CONTEXT_RE,
    _in_prostate_context,
    _preceded_by_negation,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------
@dataclass
class TimelineEvent:
    """A single dated clinical event surfaced from the source text."""
    date_key: str               # "YYYY-MM-DD" if known precisely; "YYYY-MM" or "YYYY" if not
    date_display: str           # "Mar 2026" / "2023" — what we render in prompts
    event_type: str             # see EVENT_TYPES below
    modality: str = ""          # "ADT" / "EBRT" / "abiraterone" / "cystoscopy" / "PSMA PET" etc.
    detail: str = ""            # short, readable detail (the finding / value / context)
    source_quote: str = ""      # the original quote from source (for provenance)


EVENT_TYPES = (
    "DIAGNOSIS",
    "TREATMENT_STARTED",
    "TREATMENT_COMPLETED",
    "TREATMENT_RESTARTED",
    "TREATMENT_DECLINED",
    "PATHOLOGY",
    "IMAGING",
    "PROCEDURE",
    "LAB_TREND",
    "STAGING_DECISION",
    "VISIT",
)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_date_from_text(s: str) -> Optional[Tuple[str, str]]:
    """Parse a date from a free-text fragment and return (date_key, display).

    Returns None if no parseable date is present.
    """
    if not s:
        return None
    s = s.strip()

    # MM/DD/YYYY or M/D/YY
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", s)
    if m:
        mo, day, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if yr < 100:
            yr = 2000 + yr if yr < 69 else 1900 + yr
        if 1 <= mo <= 12 and 1 <= day <= 31 and 1900 <= yr <= 2099:
            try:
                d = date(yr, mo, day)
                return f"{yr:04d}-{mo:02d}-{day:02d}", d.strftime("%b %d, %Y")
            except ValueError:
                pass

    # Month-name DD, YYYY  or  Month-name YYYY
    m = re.search(
        r"\b([A-Za-z]{3,9})\s+(\d{1,2})?,?\s*(\d{4})\b", s,
    )
    if m:
        mo_name = m.group(1).lower()
        mo = _MONTHS.get(mo_name)
        if mo:
            yr = int(m.group(3))
            if m.group(2):
                day = int(m.group(2))
                try:
                    d = date(yr, mo, day)
                    return f"{yr:04d}-{mo:02d}-{day:02d}", d.strftime("%b %d, %Y")
                except ValueError:
                    pass
            return f"{yr:04d}-{mo:02d}", f"{m.group(1).title()[:3]} {yr}"

    # MM/YYYY
    m = re.search(r"\b(\d{1,2})/(\d{4})\b", s)
    if m:
        mo, yr = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{yr:04d}-{mo:02d}", f"{date(yr, mo, 1).strftime('%b %Y')}"

    # YYYY only
    m = re.search(r"\b(19[89]\d|20\d\d)\b", s)
    if m:
        yr = int(m.group(1))
        return f"{yr:04d}", str(yr)

    return None


def _date_in_window(text: str, center: int, window: int = 80) -> Optional[Tuple[str, str]]:
    """Look for a date in a ``window``-char window centered on ``center``."""
    snippet = text[max(0, center - window):center + window]
    return _parse_date_from_text(snippet)


# ---------------------------------------------------------------------------
# Pattern catalogs
# ---------------------------------------------------------------------------
# Treatment vocabulary used across event types.
_TX_VOCAB = (
    # AR-pathway / ADT
    (r"(?:Lupron|Eligard|leuprolide|degarelix)", "Eligard / leuprolide"),
    (r"(?:androgen\s+deprivation(?:\s+therapy)?|\bADT\b)", "ADT"),
    (r"\babiraterone\b", "abiraterone"),
    (r"\benzalutamide\b", "enzalutamide"),
    (r"\bapalutamide\b", "apalutamide"),
    (r"\bdarolutamide\b", "darolutamide"),
    # Radiation
    (r"(?:high[\-\s]?dose\s+|external\s+beam\s+|definitive\s+)?"
     r"radiation(?:\s+therapy)?|\bXRT\b|\bEBRT\b|\bIMRT\b|\bSBRT\b|\bIGRT\b",
     "radiation therapy"),
    (r"\bbrachytherapy\b|seed\s+implant", "brachytherapy"),
    # Surgery
    (r"radical\s+prostatectomy|\bprostatectomy\b|\bRALP\b|\bRARP\b|\bRRP\b",
     "prostatectomy"),
    # Focal
    (r"focal\s+(?:therapy|ablation|cryoablation|cryotherapy|laser\s+ablation)|"
     r"\bHIFU\b|\bTULSA(?:-PRO)?\b",
     "focal therapy"),
    # Chemo / other systemic
    (r"\bdocetaxel\b|\bcabazitaxel\b", "chemotherapy"),
    (r"\bsipuleucel(?:-T)?\b|\bProvenge\b", "Provenge"),
    (r"\bradium[- ]?223\b", "Ra-223"),
    (r"\b(?:177\s*Lu|Lu[- ]?177|Pluvicto)\b", "Lu-177 PSMA"),
)


_RESTART_TRIGGERS = re.compile(
    r"(?:re-?started|restart(?:ed)?|reinitiat(?:ed|ion)|resum(?:ed|ption))",
    re.IGNORECASE,
)
_COMPLETION_TRIGGERS = re.compile(
    r"(?:completed|finished|last\s+(?:injection|dose|administration|cycle))",
    re.IGNORECASE,
)
_START_TRIGGERS = re.compile(
    r"(?:initiated|started|began|received|opt(?:ed)?\s+for|underwent|consented\s+to\s+start)",
    re.IGNORECASE,
)
_DECLINE_TRIGGERS = re.compile(
    r"(?:declined|refused|elected\s+against|opted\s+against|deferred|not\s+a\s+candidate)",
    re.IGNORECASE,
)


# Procedure vocabulary (cystoscopy, urodynamics, biopsy, etc.)
_PROCEDURE_VOCAB = (
    (r"\bcystoscop(?:y|ies)\b", "cystoscopy"),
    (r"\bcystourethroscop(?:y|ies)\b", "cystourethroscopy"),
    (r"\burodynamic(?:s|\s+study|\s+studies)?\b|\bUDS\b", "urodynamics"),
    (r"\bprostate\s+biops(?:y|ies)\b|\bTRUS\s*[-/]?\s*Bx?\b|fusion\s+biopsy", "prostate biopsy"),
    (r"\bbladder\s+biops(?:y|ies)\b", "bladder biopsy"),
    (r"\bTURBT\b|transurethral\s+resection\s+of\s+bladder", "TURBT"),
    (r"\bTURP\b|transurethral\s+resection\s+of\s+(?:the\s+)?prostate", "TURP"),
    (r"\bcystolitholapaxy\b|bladder\s+stone\s+removal", "cystolitholapaxy"),
    (r"\bureteroscop(?:y|ies)\b|\bURS\b", "ureteroscopy"),
    (r"\bnephrolithotomy\b|\bPCNL\b", "PCNL"),
    (r"\bSWL\b|shock\s+wave\s+lithotripsy", "SWL"),
    (r"\bsuprapubic\s+catheter\b|\bSPC\b", "SPC placement"),
    (r"\bDEXA(?:\s+scan)?\b", "DEXA"),
)


# Staging / progression decision vocabulary
_STAGING_PATTERNS = (
    (r"\bmCRPC\b|metastatic\s+castration[\s\-]?resistant\s+prostate\s+cancer|"
     r"castration[\s\-]?resistant\s+(?:metastatic\s+)?(?:prostate\s+)?(?:cancer|disease)",
     "metastatic castration-resistant prostate cancer (mCRPC)"),
    (r"\bmHSPC\b|metastatic\s+hormone[\s\-]?sensitive\s+prostate\s+cancer",
     "metastatic hormone-sensitive prostate cancer (mHSPC)"),
    (r"\bmetastatic\s+(?:prostate\s+)?(?:cancer|adenocarcinoma|disease)\b",
     "metastatic prostate cancer"),
    (r"biochemical\s+recurrence|biochemical\s+failure|biochemical\s+relapse",
     "biochemical recurrence"),
    (r"\bcastrate[\s\-]?resistan\w+",
     "castration-resistant disease"),
)


# Imaging modality vocabulary
_IMAGING_MODALITIES = (
    (r"\bPSMA[\s\-]?PET(?:/CT)?\b", "PSMA PET/CT"),
    (r"\b(?:m[Pp])?MRI\s+(?:of\s+the\s+)?prostate\b|prostate\s+MRI",
     "prostate MRI"),
    (r"\bmpMRI\b", "multiparametric prostate MRI"),
    (r"\bbone\s+scan\b|\bTc[\s\-]?99(?:m)?\b", "bone scan"),
    (r"\bCT\s+(?:urogram|abdomen|pelvis|abd/pel)\b", "CT abdomen/pelvis"),
    (r"\brenal\s+ultrasound\b", "renal ultrasound"),
    (r"\bMRI\s+(?:T[\s/]?L\s+)?spine\b|MRI\s+thoracic.{0,15}lumbar", "MRI spine"),
)


# ---------------------------------------------------------------------------
# Helper: scan for a treatment word with completion verb / restart trigger
# ---------------------------------------------------------------------------
def _find_treatment_events(
    text: str, trigger_re: re.Pattern, event_type: str,
) -> List[TimelineEvent]:
    """Find treatment events of the given type (e.g. RESTARTED, COMPLETED, STARTED, DECLINED).

    A match requires: trigger verb within 60 chars BEFORE a treatment vocab
    word, NOT preceded by negation, AND within prostate-cancer context.
    """
    events: List[TimelineEvent] = []
    seen = set()
    for tx_pattern, tx_display in _TX_VOCAB:
        for m in re.finditer(tx_pattern, text, re.IGNORECASE):
            if _preceded_by_negation(text, m.start()):
                continue
            # Trigger may appear either BEFORE the modality
            # ("Restarted ADT") or AFTER it ("ADT was restarted"). Check
            # both windows so we don't miss the post-modality-trigger
            # phrasing that dominates real clinician prose.
            preceding = text[max(0, m.start() - 80):m.start()]
            trailing = text[m.end():m.end() + 60]
            if not (trigger_re.search(preceding) or trigger_re.search(trailing)):
                continue
            if event_type == "TREATMENT_DECLINED":
                # The decline trigger and treatment word together are the event.
                pass
            else:
                # Some triggers (like "declined") are ambiguous wrt RESTART/COMPLETE
                # — make sure a competing decline doesn't trip START/COMPLETE here.
                if event_type != "TREATMENT_DECLINED" and _DECLINE_TRIGGERS.search(preceding):
                    continue
            if not _in_prostate_context(text, m.start()):
                continue
            # Date can be on either side, prefer following (~50 chars after)
            d = (_date_in_window(text, m.end(), window=60)
                 or _date_in_window(text, m.start(), window=80))
            if not d:
                continue
            date_key, date_display = d
            key = (date_key, event_type, tx_display.lower())
            if key in seen:
                continue
            seen.add(key)
            # Capture a quote from -60 to +30
            q_start = max(0, m.start() - 60)
            q_end = min(len(text), m.end() + 30)
            quote = re.sub(r"\s+", " ", text[q_start:q_end]).strip()
            events.append(TimelineEvent(
                date_key=date_key,
                date_display=date_display,
                event_type=event_type,
                modality=tx_display,
                detail=quote[:140],
                source_quote=quote,
            ))
    return events


# ---------------------------------------------------------------------------
# Procedure findings extractor
# ---------------------------------------------------------------------------
@dataclass
class ProcedureFinding:
    procedure: str          # "cystoscopy" / "urodynamics" / "prostate biopsy" / ...
    date_key: str           # parsed date key for sorting
    date_display: str       # human-readable date
    finding: str            # short summary of the key finding
    source_quote: str       # provenance


def extract_procedure_findings(raw_text: str) -> List[ProcedureFinding]:
    """Surface key findings from urologic procedures.

    Procedures we surface:
      - Cystoscopy (key findings: tumor, stricture, BNC, mucosa, normal)
      - Urodynamics (BOOI, BCI, Pdet/Qmax, detrusor overactivity)
      - Prostate biopsy (Gleason, Grade Group, % involvement) — gated to
        avoid duplicating the existing pathology extractor; we only add
        biopsy events here when a date is adjacent.
      - TURBT / TURP (resection extent, pathology if cited inline)
      - DEXA (BMD T-score)

    These were the procedures the user reported missing from synthesized
    output despite being clinically decisive.
    """
    findings: List[ProcedureFinding] = []
    seen = set()

    for proc_pat, proc_label in _PROCEDURE_VOCAB:
        for m in re.finditer(proc_pat, raw_text, re.IGNORECASE):
            if _preceded_by_negation(raw_text, m.start()):
                continue
            d = (_date_in_window(raw_text, m.start(), window=80)
                 or _date_in_window(raw_text, m.end(), window=80))
            date_key = d[0] if d else ""
            date_display = d[1] if d else "(undated)"
            # Skip purely planning-context mentions ("consider cystoscopy")
            preceding = raw_text[max(0, m.start() - 30):m.start()].lower()
            if any(w in preceding for w in ("consider ", "discuss ", "may ", "if ", "schedule ")):
                continue
            # Look for finding text in the 0..400 char window AFTER the
            # procedure word. Different shapes for different procedures.
            tail = raw_text[m.end():m.end() + 400]
            finding = _summarize_procedure_finding(proc_label, tail, raw_text, m.start())
            if not finding:
                continue
            key = (proc_label, date_key, finding.lower()[:60])
            if key in seen:
                continue
            seen.add(key)
            q = raw_text[max(0, m.start() - 20):m.end() + 200]
            findings.append(ProcedureFinding(
                procedure=proc_label,
                date_key=date_key,
                date_display=date_display,
                finding=finding[:200],
                source_quote=re.sub(r"\s+", " ", q).strip()[:300],
            ))

    findings.sort(key=lambda f: (f.date_key or "0", f.procedure), reverse=True)
    return findings


def _summarize_procedure_finding(
    proc: str, tail: str, full_text: str, anchor: int,
) -> str:
    """Build a short finding string for a specific procedure category."""
    tail_clean = re.sub(r"\s+", " ", tail).strip()

    if proc in ("cystoscopy", "cystourethroscopy"):
        # Common cystoscopy finding markers
        m = re.search(
            r"(?:(?:revealed|showed|demonstrated|notable\s+for|notable\s+findings?(?:\s+include)?[:\s]|"
            r"impression[:\s]|findings?[:\s])[^.]{4,250})",
            tail_clean, re.IGNORECASE,
        )
        if m:
            return _clean_finding_text(m.group(0))
        # Quick keyword grab if no explicit "showed" verb
        for kw in ("tumor", "papillary", "lesion", "stricture", "bladder neck contracture",
                   "BNC", "normal urethra", "normal bladder", "trabeculation",
                   "stone", "mass", "mucosa", "diverticulum", "no recurrence"):
            if re.search(rf"\b{re.escape(kw)}\b", tail_clean, re.IGNORECASE):
                m2 = re.search(
                    rf"[^.]{{0,80}}\b{re.escape(kw)}\b[^.]{{0,80}}",
                    tail_clean, re.IGNORECASE,
                )
                if m2:
                    return _clean_finding_text(m2.group(0))

    elif proc == "urodynamics":
        bits: List[str] = []
        for pat in (
            r"(?:BOOI|BCI|BCIE|DCI)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            r"(?:Pdet|Q\s*max|Qmax)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            r"detrusor\s+(?:over)?activity",
            r"(?:obstruct|equivocal|unobstructed)\w*",
            r"\bvoiding\s+pressure[s]?\s*[:=]?\s*(\d+)",
            r"\bcapacity\s*[:=]?\s*(\d+)\s*(?:mL|cc)?",
            r"compliance\s*[:=]?\s*(?:normal|reduced|impaired)",
        ):
            mm = re.search(pat, tail_clean, re.IGNORECASE)
            if mm:
                bits.append(mm.group(0))
        if bits:
            return _clean_finding_text("; ".join(bits))

    elif proc == "prostate biopsy":
        m = re.search(
            r"(Gleason\s+\d\s*\+\s*\d(?:\s*=\s*\d+/10)?|Grade\s+Group\s+[1-5]|"
            r"\bGG[1-5]\b|negative\s+for\s+malignancy|prostatic\s+adenocarcinoma|"
            r"atypical\s+small\s+acinar\s+proliferation|\bASAP\b|HGPIN)",
            tail_clean, re.IGNORECASE,
        )
        if m:
            return _clean_finding_text(m.group(0))

    elif proc == "bladder biopsy":
        m = re.search(
            r"(high[\-\s]?grade|low[\-\s]?grade|papillary\s+urothelial\s+carcinoma|"
            r"CIS|carcinoma\s+in\s+situ|invasive|muscle\s+invasive|"
            r"non[\-\s]?invasive|Ta\b|T1\b|T2\b)",
            tail_clean, re.IGNORECASE,
        )
        if m:
            return _clean_finding_text(m.group(0))

    elif proc in ("TURBT",):
        m = re.search(
            r"(papillary|high[\-\s]?grade|low[\-\s]?grade|invasive|non[\-\s]?invasive|"
            r"muscle[\-\s]?invasive|T[01-4]\b|carcinoma\s+in\s+situ|CIS|"
            r"complete\s+resection|incomplete\s+resection)",
            tail_clean, re.IGNORECASE,
        )
        if m:
            return _clean_finding_text(m.group(0))

    elif proc == "TURP":
        m = re.search(
            r"(prostate\s+volume|\d+\s*g(?:rams?)?|resected\s+\d+|"
            r"clot\s+evacuation|good\s+irrigation)",
            tail_clean, re.IGNORECASE,
        )
        if m:
            return _clean_finding_text(m.group(0))

    elif proc == "cystolitholapaxy":
        m = re.search(
            r"(bladder\s+stone|stone\s+(?:fragmented|removed)|"
            r"complete\s+stone\s+clearance)",
            tail_clean, re.IGNORECASE,
        )
        if m:
            return _clean_finding_text(m.group(0))
        return "performed"  # bare existence still surfaces the procedure

    elif proc == "DEXA":
        m = re.search(
            r"T[\-\s]?score\s*[:=]?\s*([\-+]?\d+(?:\.\d+)?)|"
            r"normal\s+(?:BMD|bone\s+mineral\s+density)|"
            r"osteopenia|osteoporosis",
            tail_clean, re.IGNORECASE,
        )
        if m:
            return _clean_finding_text(m.group(0))

    elif proc == "ureteroscopy":
        m = re.search(
            r"(stone\s+(?:identified|fragmented|extracted)|"
            r"ureteral\s+(?:tumor|stricture|stenosis)|"
            r"clearance|no\s+stones?)",
            tail_clean, re.IGNORECASE,
        )
        if m:
            return _clean_finding_text(m.group(0))

    elif proc in ("PCNL", "SWL"):
        m = re.search(
            r"(stone\s+(?:cleared|fragmented|residual)|"
            r"complete\s+stone\s+removal|residual\s+fragment)",
            tail_clean, re.IGNORECASE,
        )
        if m:
            return _clean_finding_text(m.group(0))

    return ""


def _clean_finding_text(s: str) -> str:
    out = re.sub(r"\s+", " ", s or "").strip()
    # Cap length and trim trailing punctuation
    out = out.rstrip(" .,;:")
    return out[:200]


# ---------------------------------------------------------------------------
# Imaging events
# ---------------------------------------------------------------------------
def _extract_imaging_events(raw_text: str) -> List[TimelineEvent]:
    events: List[TimelineEvent] = []
    seen = set()
    for pat, modality in _IMAGING_MODALITIES:
        for m in re.finditer(pat, raw_text, re.IGNORECASE):
            if _preceded_by_negation(raw_text, m.start()):
                continue
            if not _in_prostate_context(raw_text, m.start()):
                # imaging only enters timeline if urologic context is present
                continue
            d = (_date_in_window(raw_text, m.start(), 80)
                 or _date_in_window(raw_text, m.end(), 80))
            if not d:
                continue
            date_key, date_display = d
            # Try to extract a short finding from the trailing window
            tail = raw_text[m.end():m.end() + 300]
            tail_clean = re.sub(r"\s+", " ", tail).strip()
            finding_m = re.search(
                r"(?:show(?:ed|s)?|demonstrat(?:ed|es)?|reveal(?:ed|s)?|"
                r"impression[:\s]|notable\s+for|consistent\s+with)\s+([^.]{4,200})",
                tail_clean, re.IGNORECASE,
            )
            detail = (
                _clean_finding_text(finding_m.group(1)) if finding_m
                else _clean_finding_text(tail_clean[:160])
            )
            key = (date_key, "IMAGING", modality.lower())
            if key in seen:
                continue
            seen.add(key)
            events.append(TimelineEvent(
                date_key=date_key,
                date_display=date_display,
                event_type="IMAGING",
                modality=modality,
                detail=detail,
                source_quote=re.sub(r"\s+", " ", raw_text[max(0, m.start() - 30):m.end() + 200]).strip()[:300],
            ))
    return events


# ---------------------------------------------------------------------------
# Pathology events (lighter; pathology_extractor remains the authoritative
# source for the rendered note, this just surfaces them on the timeline)
# ---------------------------------------------------------------------------
_BIOPSY_DATE_RE = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|"
    r"\d{1,2}/\d{4})\s+"
    r"(?:Prostate\s+biopsy|TRUS\s*Bx|Prostate\s+Bx|biopsy)",
    re.IGNORECASE,
)


def _extract_pathology_events(raw_text: str) -> List[TimelineEvent]:
    events: List[TimelineEvent] = []
    seen = set()
    for m in _BIOPSY_DATE_RE.finditer(raw_text):
        d = _parse_date_from_text(m.group(1))
        if not d:
            continue
        date_key, date_display = d
        # Look 0..400 chars after for Gleason/GG
        tail = raw_text[m.end():m.end() + 400]
        finding_m = re.search(
            r"Gleason\s+(\d\s*\+\s*\d)(?:\s*=\s*\d+/10)?\s*"
            r"(?:\(?\s*(?:Grade\s+Group|GG)\s*(\d)\)?)?|"
            r"negative\s+for\s+malignancy|prostatic\s+adenocarcinoma|"
            r"atypical\s+small\s+acinar\s+proliferation",
            tail, re.IGNORECASE,
        )
        detail = "biopsy"
        if finding_m:
            detail = _clean_finding_text(finding_m.group(0))
        key = (date_key, "PATHOLOGY", detail.lower()[:60])
        if key in seen:
            continue
        seen.add(key)
        events.append(TimelineEvent(
            date_key=date_key,
            date_display=date_display,
            event_type="PATHOLOGY",
            modality="prostate biopsy",
            detail=detail,
            source_quote=re.sub(r"\s+", " ", raw_text[m.start():m.end() + 200]).strip()[:300],
        ))
    return events


# ---------------------------------------------------------------------------
# Diagnosis events
# ---------------------------------------------------------------------------
def _extract_diagnosis_events(raw_text: str) -> List[TimelineEvent]:
    events: List[TimelineEvent] = []
    seen = set()
    # Pattern: "diagnosed in YYYY (or MM/YYYY) with prostate (adeno)carcinoma"
    # OR: "(YYYY) ... prostate cancer / adenocarcinoma"
    for m in re.finditer(
        r"\b(?:diagnos(?:ed|is)|found\s+to\s+have)\s+(?:with|of)?\s*[^.]{0,80}?"
        r"\bprostate\s+(?:cancer|adenocarcinoma)\b",
        raw_text, re.IGNORECASE,
    ):
        d = _date_in_window(raw_text, m.start(), 100)
        if not d:
            continue
        date_key, date_display = d
        key = ("DIAGNOSIS", date_key)
        if key in seen:
            continue
        seen.add(key)
        events.append(TimelineEvent(
            date_key=date_key,
            date_display=date_display,
            event_type="DIAGNOSIS",
            modality="prostate cancer",
            detail="prostate adenocarcinoma diagnosed",
            source_quote=re.sub(r"\s+", " ", raw_text[max(0, m.start() - 40):m.end() + 80]).strip()[:300],
        ))
    return events


# ---------------------------------------------------------------------------
# Staging decisions (mCRPC, mHSPC, biochemical recurrence)
# ---------------------------------------------------------------------------
def _extract_staging_events(raw_text: str) -> List[TimelineEvent]:
    events: List[TimelineEvent] = []
    seen = set()
    for pat, display in _STAGING_PATTERNS:
        for m in re.finditer(pat, raw_text, re.IGNORECASE):
            if _preceded_by_negation(raw_text, m.start()):
                continue
            d = _date_in_window(raw_text, m.start(), 100)
            date_key = d[0] if d else ""
            date_display = d[1] if d else "(undated)"
            key = ("STAGING_DECISION", display.lower(), date_key)
            if key in seen:
                continue
            seen.add(key)
            events.append(TimelineEvent(
                date_key=date_key,
                date_display=date_display,
                event_type="STAGING_DECISION",
                modality=display,
                detail=display,
                source_quote=re.sub(r"\s+", " ", raw_text[max(0, m.start() - 40):m.end() + 100]).strip()[:300],
            ))
    return events


# ---------------------------------------------------------------------------
# PSA trajectory (sorted descending — newest first when rendered)
# ---------------------------------------------------------------------------
_PSA_CURVE_RE = re.compile(
    r"\[r\]\s*([A-Za-z]{3}\s+\d{1,2},\s+\d{4})\s+\d{1,4}[:.]?\d{0,2}\s+"
    r"(\d+\.?\d*)\s*([HL]?)",
    re.IGNORECASE,
)


def extract_psa_trajectory(raw_text: str) -> List[Tuple[str, str, float]]:
    """Return PSA trajectory as a list of (date_key, date_display, value)."""
    pts: List[Tuple[str, str, float]] = []
    seen = set()
    for m in _PSA_CURVE_RE.finditer(raw_text):
        d = _parse_date_from_text(m.group(1))
        if not d:
            continue
        date_key, date_display = d
        try:
            val = float(m.group(2))
        except ValueError:
            continue
        k = (date_key, val)
        if k in seen:
            continue
        seen.add(k)
        pts.append((date_key, date_display, val))
    pts.sort(key=lambda p: p[0], reverse=True)
    return pts


# ---------------------------------------------------------------------------
# Master extractor
# ---------------------------------------------------------------------------
def extract_clinical_timeline(
    raw_text: str,
    today: Optional[date] = None,
) -> List[TimelineEvent]:
    """Build the chronologically-sorted clinical timeline."""
    if not raw_text:
        return []
    today = today or date.today()

    events: List[TimelineEvent] = []
    events += _extract_diagnosis_events(raw_text)
    events += _find_treatment_events(raw_text, _START_TRIGGERS, "TREATMENT_STARTED")
    events += _find_treatment_events(raw_text, _COMPLETION_TRIGGERS, "TREATMENT_COMPLETED")
    events += _find_treatment_events(raw_text, _RESTART_TRIGGERS, "TREATMENT_RESTARTED")
    events += _find_treatment_events(raw_text, _DECLINE_TRIGGERS, "TREATMENT_DECLINED")
    events += _extract_pathology_events(raw_text)
    events += _extract_imaging_events(raw_text)
    events += _extract_staging_events(raw_text)

    # PROCEDURE events from the findings extractor
    for pf in extract_procedure_findings(raw_text):
        events.append(TimelineEvent(
            date_key=pf.date_key,
            date_display=pf.date_display,
            event_type="PROCEDURE",
            modality=pf.procedure,
            detail=pf.finding,
            source_quote=pf.source_quote,
        ))

    # Sort: events with dates ascend chronologically; dateless to the end.
    def sort_key(e: TimelineEvent):
        return (e.date_key or "9999", e.event_type)
    events.sort(key=sort_key)
    return events


# ---------------------------------------------------------------------------
# Phase classification
# ---------------------------------------------------------------------------
PHASES = (
    "TREATMENT_NAIVE",
    "ON_INITIAL_TREATMENT",
    "POST_TREATMENT_SURVEILLANCE",
    "BIOCHEMICAL_RECURRENCE",
    "SALVAGE_OR_RESTART",
    "METASTATIC_HORMONE_SENSITIVE",
    "METASTATIC_CASTRATION_RESISTANT",
    "PROGRESSION",
    "UNCERTAIN",
)


def classify_current_phase(
    timeline: List[TimelineEvent],
    today: Optional[date] = None,
) -> str:
    """Deterministic state-machine over the timeline."""
    today = today or date.today()
    if not timeline:
        return "UNCERTAIN"

    has_cancer = any(e.event_type == "DIAGNOSIS" for e in timeline) or any(
        e.event_type == "PATHOLOGY"
        and ("gleason" in e.detail.lower() or "adenocarcinoma" in e.detail.lower())
        for e in timeline
    )
    if not has_cancer:
        # No cancer evidence found
        return "TREATMENT_NAIVE"

    # Pull staging decisions
    staging = [e for e in timeline if e.event_type == "STAGING_DECISION"]
    has_mcrpc = any("mcrpc" in e.modality.lower() or "castration-resistant" in e.modality.lower()
                    for e in staging)
    has_mhspc = any("mhspc" in e.modality.lower() or "hormone-sensitive" in e.modality.lower()
                    for e in staging)
    has_metastatic = any("metastatic" in e.modality.lower() for e in staging)
    has_recurrence_decision = any("recurrence" in e.modality.lower() for e in staging)

    # AR-pathway agent currently active?
    ar_agents = ("abiraterone", "enzalutamide", "apalutamide", "darolutamide")
    has_ar_pathway_start = any(
        e.event_type == "TREATMENT_STARTED" and e.modality.lower() in ar_agents
        for e in timeline
    )

    # ADT current status: RESTARTED later than COMPLETED?
    adt_events = [
        e for e in timeline
        if e.modality.lower() in ("adt", "eligard / leuprolide")
    ]
    last_adt_action: Optional[TimelineEvent] = None
    for e in adt_events:
        if last_adt_action is None or e.date_key > last_adt_action.date_key:
            last_adt_action = e

    if has_mcrpc or (has_ar_pathway_start and has_metastatic):
        return "METASTATIC_CASTRATION_RESISTANT"

    if has_mhspc or (has_metastatic and last_adt_action
                     and last_adt_action.event_type in ("TREATMENT_STARTED", "TREATMENT_RESTARTED")):
        return "METASTATIC_HORMONE_SENSITIVE"

    if last_adt_action and last_adt_action.event_type == "TREATMENT_RESTARTED":
        return "SALVAGE_OR_RESTART"

    if has_recurrence_decision:
        # Recurrence noted but no restart yet
        return "BIOCHEMICAL_RECURRENCE"

    # All confirmed treatments completed?
    started = [e for e in timeline if e.event_type == "TREATMENT_STARTED"]
    completed = [e for e in timeline if e.event_type == "TREATMENT_COMPLETED"]
    if completed and (not started or completed[-1].date_key >= started[-1].date_key):
        return "POST_TREATMENT_SURVEILLANCE"
    if started:
        return "ON_INITIAL_TREATMENT"
    return "UNCERTAIN"


# ---------------------------------------------------------------------------
# Current active treatments
# ---------------------------------------------------------------------------
_MED_LIST_HEADER_RE = re.compile(
    r"(?:Active\s+Outpatient\s+Medications|Current\s+Medications|MEDICATIONS:?)\s*\n",
    re.IGNORECASE,
)

_ONCOLOGIC_MED_HINTS = (
    "eligard", "leuprolide", "lupron", "degarelix", "abiraterone",
    "enzalutamide", "apalutamide", "darolutamide", "prednisone",
    "docetaxel", "cabazitaxel", "sipuleucel", "provenge", "radium-223",
    "pluvicto", "tamsulosin", "finasteride", "dutasteride", "silodosin",
    "calcium", "vitamin d",
)


def detect_current_active_treatments(raw_text: str) -> List[str]:
    """Return a short list of meds the patient is currently taking, anchored
    to the most-recent medications list block in the source.

    Without this, the HPI/Plan agents have only an unordered set of "drugs
    mentioned somewhere" and can flip-flop on whether the patient is still
    on ADT (which is the Ketnick failure mode).
    """
    if not raw_text:
        return []
    out: List[str] = []
    seen = set()
    for m in _MED_LIST_HEADER_RE.finditer(raw_text):
        block = raw_text[m.end():m.end() + 2000]
        # Stop at next ALL-CAPS header / separator
        stop_m = re.search(r"^\s*(?:[A-Z]{4,}:\s*$|={5,})", block, re.MULTILINE)
        if stop_m:
            block = block[:stop_m.start()]
        for line in block.split("\n"):
            line_l = line.lower()
            for hint in _ONCOLOGIC_MED_HINTS:
                if hint in line_l:
                    quote = re.sub(r"\s+", " ", line).strip()
                    if quote and quote not in seen:
                        seen.add(quote)
                        out.append(quote[:160])
                    break
    return out


# ---------------------------------------------------------------------------
# Rendering for the prompt
# ---------------------------------------------------------------------------
def format_timeline_for_prompt(events: List[TimelineEvent], limit: int = 30) -> str:
    """Render the timeline as a dated bullet list for inclusion in the
    GROUND TRUTH prompt block. Sorted oldest -> newest so the narrative
    arc reads left-to-right."""
    if not events:
        return "(no dated clinical events extracted)"
    lines: List[str] = []
    # Show up to `limit` events. If overflow, summarize.
    show = events[-limit:] if len(events) > limit else events
    for e in show:
        date_disp = e.date_display or "(undated)"
        type_lbl = e.event_type.replace("_", " ").title()
        modality = e.modality or ""
        detail = (e.detail or "").strip()
        parts = [f"[{date_disp}]", type_lbl]
        if modality:
            parts.append(f"- {modality}")
        if detail and detail.lower() != modality.lower():
            parts.append(f": {detail}")
        lines.append("  " + " ".join(parts))
    if len(events) > limit:
        lines.insert(0, f"  ({len(events) - limit} older event(s) omitted; most recent shown)")
    return "\n".join(lines)


def format_procedures_for_prompt(findings: List[ProcedureFinding], limit: int = 12) -> str:
    """Render key procedure findings as a separate prompt section so the
    Assessment/Plan don't omit cystoscopy / urodynamics / biopsy outcomes."""
    if not findings:
        return ""
    lines = []
    for pf in findings[:limit]:
        lines.append(
            f"  - {pf.procedure} ({pf.date_display}): {pf.finding}"
        )
    return "\n".join(lines)


_PHASE_GUIDANCE = {
    "TREATMENT_NAIVE": (
        "Patient has NO confirmed prior prostate-cancer-directed treatment. "
        "Rising PSA is a workup question for new disease. The narrative should "
        "frame today's visit around evaluation, not surveillance after treatment."
    ),
    "ON_INITIAL_TREATMENT": (
        "Patient is currently receiving initial prostate-cancer treatment. "
        "The HPI and Plan must reflect ongoing therapy, including response to "
        "treatment and any in-progress sequencing decisions."
    ),
    "POST_TREATMENT_SURVEILLANCE": (
        "Patient has completed initial treatment and is in routine PSA / imaging "
        "surveillance. No active treatment. Phoenix criteria (nadir+2) applies for "
        "post-radiation patients. Do NOT recommend salvage unless biochemical "
        "recurrence has been documented."
    ),
    "BIOCHEMICAL_RECURRENCE": (
        "Biochemical recurrence is established (e.g. Phoenix met after radiation, "
        "or detectable PSA after prostatectomy). Restage with PSMA-PET; discuss "
        "salvage options. Do NOT call this 'active surveillance'."
    ),
    "SALVAGE_OR_RESTART": (
        "Patient has recently restarted or begun salvage therapy. The HPI must "
        "explicitly state the restart with date and modality. Do NOT describe the "
        "patient as treatment-completed; the active treatment is ONGOING."
    ),
    "METASTATIC_HORMONE_SENSITIVE": (
        "Metastatic hormone-sensitive prostate cancer (mHSPC). Patient is on ADT "
        "with or without AR-pathway intensification. Treatment is indefinite. The "
        "HPI must name the metastatic sites and the current regimen by name."
    ),
    "METASTATIC_CASTRATION_RESISTANT": (
        "Metastatic castration-resistant prostate cancer (mCRPC). Patient is on "
        "ADT INDEFINITELY plus an AR-pathway agent (abiraterone/enzalutamide/"
        "apalutamide/darolutamide) and/or other systemic therapy. The Plan MUST "
        "continue Eligard / leuprolide at the documented interval — do NOT write "
        "'no further ADT is planned'. The HPI must name the metastatic sites, "
        "the date ADT was restarted (if applicable), and the current systemic "
        "regimen."
    ),
    "PROGRESSION": (
        "Patient has documented progression on prior therapy. Sequencing of next "
        "systemic therapy is the active clinical question."
    ),
    "UNCERTAIN": (
        "Phase could not be determined deterministically. Defer to source notes "
        "for treatment-current vs treatment-completed status and explicitly cite "
        "the date of last documented therapy."
    ),
}


def phase_guidance(phase: str) -> str:
    return _PHASE_GUIDANCE.get(phase, _PHASE_GUIDANCE["UNCERTAIN"])
