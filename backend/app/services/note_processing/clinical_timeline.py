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
    _HEDGING_RE,
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
    # Temporal-validity metadata (see _classify_event). source_tier ranks
    # trustworthiness: 1 = structured dated result (path / imaging / lab /
    # procedure), 2 = dated history (treatment course), 3 = narrative.
    # assertion_class: "durable" facts persist once true; "volatile" facts
    # (disease status, on-treatment status, a measured value, an imaging
    # impression) are true only AS OF their date and must be re-anchored to the
    # latest observation, never carried forward as a standing truth.
    source_tier: int = 2
    assertion_class: str = ""   # "durable" | "volatile" | ""


# Source-reliability tier by event type (1 = most trustworthy point-in-time
# fact). Assertion class by event type: a completed/declined treatment, a
# diagnosis, a pathology report and a procedure are DURABLE historical facts; an
# imaging impression, a lab value, a staging decision and an ongoing-treatment
# start/restart are VOLATILE (true only as of their date).
_TIER_BY_TYPE = {
    "PATHOLOGY": 1, "IMAGING": 1, "PROCEDURE": 1, "LAB_TREND": 1,
    "DIAGNOSIS": 1, "STAGING_DECISION": 1,
    "TREATMENT_STARTED": 2, "TREATMENT_COMPLETED": 2,
    "TREATMENT_RESTARTED": 2, "TREATMENT_DECLINED": 2, "VISIT": 3,
}
_VOLATILE_TYPES = {"IMAGING", "LAB_TREND", "STAGING_DECISION",
                   "TREATMENT_STARTED", "TREATMENT_RESTARTED"}
_DURABLE_TYPES = {"DIAGNOSIS", "PATHOLOGY", "PROCEDURE",
                  "TREATMENT_COMPLETED", "TREATMENT_DECLINED"}


def _classify_event(e: "TimelineEvent") -> "TimelineEvent":
    e.source_tier = _TIER_BY_TYPE.get(e.event_type, 2)
    if e.event_type in _VOLATILE_TYPES:
        e.assertion_class = "volatile"
    elif e.event_type in _DURABLE_TYPES:
        e.assertion_class = "durable"
    return e


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


# Any date-like token, used to pick the date NEAREST a keyword (by position)
# rather than the first-by-format-priority date _parse_date_from_text returns.
_ANY_DATE_TOKEN = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|"
    r"\b[A-Za-z]{3,9}\s+\d{0,2},?\s*\d{4}\b|"
    r"\b\d{1,2}/\d{4}\b|"
    r"\b(?:19[89]\d|20\d\d)\b")


def _date_forward(text: str, pos: int, span: int = 40) -> Optional[Tuple[str, str]]:
    """The POSITIONALLY-FIRST date in a TIGHT window immediately AFTER ``pos``.
    Position-based (not _parse_date_from_text's format-priority) so 'radiation
    therapy 4/2022. Pathology 12/15/2021' dates to 4/2022 — the date adjacent to
    the treatment word — not the full-format pathology stamp just after it."""
    seg = text[pos:pos + span]
    for mm in _ANY_DATE_TOKEN.finditer(seg):
        d = _parse_date_from_text(mm.group(0))
        if d:
            return d
    return None


def _date_before_nearest(text: str, pos: int, span: int = 70) -> Optional[Tuple[str, str]]:
    """The date CLOSEST before ``pos`` (rightmost in the preceding segment) —
    positionally nearest, not first-by-format."""
    seg = text[max(0, pos - span):pos]
    for mm in reversed(list(_ANY_DATE_TOKEN.finditer(seg))):
        d = _parse_date_from_text(mm.group(0))
        if d:
            return d
    return None


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


# Qualifiers that FOLLOW a staging phrase and mark it unconfirmed /
# speculative, e.g. "metastatic disease, though this has not been
# confirmed", "... has not been confirmed", "... is unlikely",
# "... versus ablation", "... cannot be excluded".
_TRAILING_HEDGE_RE = re.compile(
    r"\b(?:"
    r"(?:has\s+)?not\s+(?:been\s+)?(?:confirmed|established|proven)|"
    r"unconfirmed|unlikely|cannot\s+be\s+(?:excluded|confirmed|ruled)|"
    r"remains?\s+(?:to\s+be\s+|un)?(?:confirmed|determined)|"
    r"is\s+(?:possible|suspected|uncertain)|versus\b|vs\.?\b|"
    r"if\s+there\s+is\s+evidence"
    r")",
    re.IGNORECASE,
)

# Staging / progression decision vocabulary
_STAGING_PATTERNS = (
    (r"\bmCRPC\b|metastatic\s+castration[\s\-]?resistant\s+prostate\s+cancer|"
     r"castration[\s\-]?resistant\s+(?:metastatic\s+)?(?:prostate\s+)?(?:cancer|disease)",
     "metastatic castration-resistant prostate cancer (mCRPC)"),
    (r"\bmHSPC\b|metastatic\s+hormone[\s\-]?sensitive\s+prostate\s+cancer",
     "metastatic hormone-sensitive prostate cancer (mHSPC)"),
    # NOTE: an explicit "prostate" anchor is REQUIRED. Bare "metastatic
    # disease" in a renal/skeletal workup ("concern for possible metastatic
    # disease") must NOT be specialized into "metastatic prostate cancer"
    # (see ASHFORD: renal-mass patient with no prostate cancer). Confirmed
    # prostate cases that say only "metastatic disease" are still covered
    # via cancer_status downstream.
    (r"\bmetastatic\s+prostate\s+(?:cancer|adenocarcinoma|disease)\b",
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
            # Date association: a treatment's date is the one adjacent to the
            # treatment word — prefer a date immediately FOLLOWING it ("radiation
            # therapy 4/2022"), then the NEAREST date before it. The old centered
            # ±60 window returned the first-by-format date, so a diagnosis/MRI
            # date one clause back hijacked the treatment (WHITEHEAD: radiation
            # 4/2022 mis-dated to the 12/2021 diagnosis).
            d = (_date_forward(text, m.end(), span=40)
                 or _date_before_nearest(text, m.start(), span=70))
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


def _preceding_note_date(raw_text: str, anchor: int, window: int = 20000) -> Optional[Tuple[str, str]]:
    """Walk the preceding `window` chars looking for the most recent
    note-header date stamp at the start of a line.

    Recognized header shapes (preference: most-specific to least):
      1. "MM/DD/YYYY HH:MM  Local Title: ..." (VistA note opener)
      2. "DATE OF NOTE: MMM DD, YYYY@HH:MM" (CPRS note attribute)
      3. "MM/DD/YYYY<spaces><Service>  Surgeon:" (operative-report
         header — Ortega's cysto, Long's cysto)
      4. "Signed: MM/DD/YYYY HH:MM" (closing stamp)
      5. Bare "MM/DD/YYYY HH:MM" at line start
    """
    preceding = raw_text[max(0, anchor - window):anchor]
    # 0. Closest inline PATHOLOGY/specimen date header ("Pathology 3/6/2023",
    #    "Path Report: MM/DD/YYYY", "PATHOLOGY: ...", "Collected: ...", "Date
    #    Spec taken: MMM DD, YYYY"). These sit at the top of a copy-forward path
    #    block and ARE the finding's true date — take the CLOSEST one within a
    #    tight window so a pathology finding isn't dated to a far, unrelated
    #    note header (BILEK: 3/6/2023 biopsy findings mis-dated to a 6/1/2011
    #    orthopedics "DATE OF NOTE" stamp).
    tight = raw_text[max(0, anchor - 1500):anchor]
    path_best = None
    for m in re.finditer(
        r"(?i)(?:patholog\w*|path\s*report|collected|date\s+spec\s+taken|"
        r"accession(?:ed)?)\s*:?\s*"
        r"((?:\d{1,2}/\d{1,2}/\d{4})|(?:[A-Z]{3,9}\s+\d{1,2},?\s+\d{4}))",
        tight,
    ):
        path_best = m  # last = closest to the anchor
    if path_best is not None:
        d = _parse_date_from_text(path_best.group(1))
        if d:
            return d
    best = None
    # 1. "MM/DD/YYYY HH:MM Local Title:" (most-specific)
    for m in re.finditer(
        r"(?m)^(\d{1,2}/\d{1,2}/\d{4})\s+\d{1,2}:\d{2}\s+(?:Local\s+Title|Standard\s+Title|"
        r"LOCAL\s+TITLE)\s*:",
        preceding,
    ):
        best = m
    # 2. "DATE OF NOTE: MMM DD, YYYY"
    if best is None:
        for m in re.finditer(
            r"(?m)^\s*DATE\s+OF\s+NOTE:\s+([A-Z]{3,9}\s+\d{1,2},?\s+\d{4})",
            preceding, re.IGNORECASE,
        ):
            best = m
    # 3. "MM/DD/YYYY<spaces><Service>  Surgeon:" — operative report
    if best is None:
        for m in re.finditer(
            r"(?m)^(\d{1,2}/\d{1,2}/\d{4})\s+[A-Za-z][A-Za-z\s&]+\s+Surgeon:",
            preceding,
        ):
            best = m
    # 4. "Signed: MM/DD/YYYY HH:MM"
    if best is None:
        for m in re.finditer(
            r"(?m)^\s*Signed:\s*(\d{1,2}/\d{1,2}/\d{4})\s+\d{1,2}:\d{2}",
            preceding, re.IGNORECASE,
        ):
            best = m
    # 5. Bare "MM/DD/YYYY HH:MM" at line start
    if best is None:
        for m in re.finditer(
            r"(?m)^(\d{1,2}/\d{1,2}/\d{4})\s+\d{1,2}:\d{2}\b",
            preceding,
        ):
            best = m
    if best is None:
        return None
    return _parse_date_from_text(best.group(1))


# PROSTATE-qualified pathology-collection dating. VistA charts interleave many
# copy-forward specimens (prostate, colon, skin); the nearest "Collected:" header
# to a prostate biopsy can belong to a DIFFERENT specimen (BILEK: a colon TUBULAR
# ADENOMA "Collected: 06/01/2011" hijacking the 2019 prostate adenocarcinoma).
# Only a collection header whose specimen block is prostate counts.
_PROSTATE_PATH_CTX = re.compile(r"prostat|gleason|grade\s+group|\bGG[1-5]\b", re.I)
_PATH_COLLECT_RE = re.compile(
    r"(?i)(?:collected|received|date\s+spec(?:imen)?\s+taken|pathology|path\s*report|"
    r"reported)\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Z]{3,9}\s+\d{1,2},?\s+\d{4})")


def _prostate_pathology_date_before(
    raw_text: str, anchor: int, window: int = 1800,
) -> Optional[Tuple[str, str]]:
    """Closest PROSTATE-qualified collection date heading the block before
    ``anchor`` (the collection header whose specimen description is prostate)."""
    seg = raw_text[max(0, anchor - window):anchor]
    best = None
    for m in _PATH_COLLECT_RE.finditer(seg):
        block = seg[m.start():min(len(seg), m.end() + 300)]
        if _PROSTATE_PATH_CTX.search(block):
            best = m  # last = closest to the anchor
    return _parse_date_from_text(best.group(1)) if best else None


def _prostate_pathology_date_keys(raw_text: str) -> set:
    """date_keys of every PROSTATE-qualified pathology collection date — the true
    prostate biopsy dates, used to anchor the copy-forward collapse."""
    keys = set()
    for m in _PATH_COLLECT_RE.finditer(raw_text):
        block = raw_text[m.start():min(len(raw_text), m.end() + 300)]
        if _PROSTATE_PATH_CTX.search(block):
            d = _parse_date_from_text(m.group(1))
            if d:
                keys.add(d[0])
    return keys


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
            # Date lookup, in order of preference:
            #   1. Tight ±80 char window around the procedure word.
            #   2. Most recent VistA-style note-header date stamp in
            #      the preceding ~2500 chars (catches "UROLOGY PROCEDURE
            #      NOTE" headers that sit hundreds of chars above the
            #      procedure-specific keyword).
            if proc_label == "prostate biopsy":
                # Date a prostate biopsy by ITS OWN prostate report's collection
                # header, not a coincidental nearer non-prostate specimen date.
                d = (_prostate_pathology_date_before(raw_text, m.start())
                     or _date_in_window(raw_text, m.start(), window=80)
                     or _date_in_window(raw_text, m.end(), window=80)
                     or _preceding_note_date(raw_text, m.start()))
            else:
                d = (_date_in_window(raw_text, m.start(), window=80)
                     or _date_in_window(raw_text, m.end(), window=80)
                     or _preceding_note_date(raw_text, m.start()))
            date_key = d[0] if d else ""
            date_display = d[1] if d else "(undated)"
            # Skip purely planning-context mentions ("consider cystoscopy"),
            # but anchor on a strict word boundary so "schedule" inside a
            # different sentence doesn't suppress a confirmed procedure.
            preceding = raw_text[max(0, m.start() - 50):m.start()].lower()
            if re.search(
                # Catch BOTH "schedule" and "scheduled"/"scheduled for",
                # BOTH "plan/planned/planned for", and the additional
                # intent markers "due for", "to undergo", "needs", and
                # "interested in" that mark a procedure the patient has
                # NOT yet had.
                r"\b(?:consider(?:ing|ed)?|discuss(?:ed|ing)?|may|if\b|"
                r"scheduled?(?:\s+for)?|recommend(?:ed|ing)?|"
                r"plan(?:ned|ning)?(?:\s+for|\s+to)?|due\s+for|"
                r"to\s+undergo|needs?(?:\s+to)?|interested\s+in|"
                r"will\s+order|will\s+arrange|will\s+set\s+up)\b",
                preceding,
            ):
                continue
            # For procedure-note style matches (cystoscopy / urodynamics /
            # biopsy / TURBT etc.), require evidence that this match is
            # an actual report header, not a narrative reference to a
            # past or hypothetical procedure. The strongest signal:
            #   - immediately followed by ":" (the report's section
            #     marker, e.g. "Cystoscopy:")
            #   - immediately preceded/followed by a CPT code in parens
            #     (e.g. "Cystoscopy (52000)")
            #   - sits inside a "Urology Procedure Note: <proc>" header
            #     within ~80 preceding chars
            local = raw_text[max(0, m.start() - 80):m.end() + 30]
            is_report_header = bool(
                re.search(
                    rf"\b{proc_pat.replace(chr(92) + 'b', '')}\s*(?::|\(\d{{4,5}}\))",
                    local, re.IGNORECASE,
                )
                # Local Title must explicitly mention "procedure" or
                # one of the structured procedure-note types — a generic
                # CHART CHECK NOTE / TECH NOTE / TELEPHONE NOTE with
                # `Local Title:` does NOT count. Without this tightening
                # a CHART CHECK NOTE that says "He is scheduled for
                # cystoscopy" passes the report-header gate.
                or re.search(
                    r"(?:Urology\s+Procedure\s+Note|"
                    r"Local\s+Title\s*:\s*[^\n]*"
                    r"(?:PROCEDURE|CYSTOSCOPY|CYSTOURETHROSCOPY|"
                    r"URODYNAMICS|BIOPSY|TURBT|TURP|DEXA))",
                    raw_text[max(0, m.start() - 600):m.start()],
                    re.IGNORECASE,
                )
            )
            if not is_report_header:
                continue
            # Look for finding text. Cystoscopy and other structured
            # procedure notes can span >1000 chars between the procedure
            # word and the trailing findings (Bladder mucosa /
            # Trabeculation grade / etc. lines sit ~800 chars below).
            # Use a 1500-char tail for these structured notes; the
            # per-procedure summarizer is conservative about what it
            # actually keeps.
            tail = raw_text[m.end():m.end() + 1500]
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

    # Collapse copied-forward prostate-biopsy pathology. The diagnostic biopsy
    # result is pasted into every subsequent clinic note, so a per-occurrence
    # date attaches PHANTOM biopsies to later note-header dates (JELLSEY: 9
    # "prostatic adenocarcinoma" biopsies dated 2022→2025, HPI then renders the
    # newest, "biopsy 10/29/2025", after XRT finished in 2022). A given biopsy
    # RESULT is a single historical event: keep one per distinct finding, dated
    # by an EXPLICIT biopsy-date anchor ("8/16/2022 Prostate Biopsy") when one
    # exists, else the earliest observed date. A genuinely different repeat
    # biopsy has different finding text and is preserved as its own event.
    bx = [f for f in findings if f.procedure == "prostate biopsy"]
    if len(bx) > 1:
        explicit_bx_dates = set()
        for bm in _BIOPSY_DATE_RE.finditer(raw_text):
            pd = _parse_date_from_text(bm.group(1))
            if pd:
                explicit_bx_dates.add(pd[0])
        # Prostate-qualified pathology collection dates are authoritative biopsy
        # anchors — they exclude non-prostate specimen dates (colon adenoma).
        explicit_bx_dates |= _prostate_pathology_date_keys(raw_text)

        def _norm_find(s: str) -> str:
            return re.sub(r"\s+", " ", (s or "").lower()).strip()[:60]

        from collections import Counter
        groups: dict = {}
        for f in bx:
            groups.setdefault(_norm_find(f.finding), []).append(f)
        collapsed: List[ProcedureFinding] = []
        for grp in groups.values():
            anchored = [f for f in grp if f.date_key in explicit_bx_dates]
            pick_from = anchored or grp
            # Copy-forward pastes the SAME pathology block into many later notes,
            # so the CORRECT biopsy date recurs across copies, while a copy whose
            # date mis-resolved to an unrelated note header (BILEK: a 3/6/2023
            # biopsy block that fell back to a 6/1/2011 orthopedics stamp) appears
            # once. Pick the MOST COMMON date; tie-break by earliest (preserves the
            # JELLSEY phantom-biopsy fix, where distinct copy dates all tie -> the
            # earliest, closest-to-the-real-diagnosis, wins).
            counts = Counter(f.date_key for f in pick_from)
            best = min(counts, key=lambda dk: (-counts[dk], dk or "9999"))
            collapsed.append(next(f for f in pick_from if f.date_key == best))
        findings = [f for f in findings if f.procedure != "prostate biopsy"] + collapsed

    findings.sort(key=lambda f: (f.date_key or "0", f.procedure), reverse=True)
    return findings


def _summarize_procedure_finding(
    proc: str, tail: str, full_text: str, anchor: int,
) -> str:
    """Build a short finding string for a specific procedure category."""
    tail_clean = re.sub(r"\s+", " ", tail).strip()

    # Truncate cysto tail at next paragraph break / known-other-procedure
    # marker BEFORE any matching. Otherwise the prose / keyword fallback
    # can leak content from co-occurring procedures in the same
    # operative report (Long failure: cysto block consumed bilateral
    # retrograde pyelogram findings from the next paragraph).
    if proc in ("cystoscopy", "cystourethroscopy"):
        cutoff_re = re.compile(
            # Inline "with [bilateral] retrograde pyelogram" — when the
            # cysto word appears in a procedure-list line that also
            # mentions co-occurring procedures on the same line.
            r"\bwith\s+(?:bilateral\s+|right\s+|left\s+)?retrograde|"
            r"\bwith\s+(?:laser\s+)?lithotripsy|"
            r"\bwith\s+stent\s+placement|"
            # Paragraph break / new labeled section
            r"\n\s*\n|"
            r"\n\s*(?:Bilateral\s+retrograde|retrograde\s+pyelogram|"
            r"Indications?\s+for\s+Operation|Complications|"
            r"Description\s+of\s+(?:Operation|Procedure)|"
            r"Specimen|EBL\b|Anesthesia|Disposition|Stents?\s+placed|"
            r"Stents?\s+placement|Estimated\s+Blood\s+Loss|"
            r"POSTOP\s+|Plan:|Signed\s+by)",
            re.IGNORECASE,
        )
        cutoff_m = cutoff_re.search(tail)
        if cutoff_m:
            tail = tail[:cutoff_m.start()]
            tail_clean = re.sub(r"\s+", " ", tail).strip()

    if proc in ("cystoscopy", "cystourethroscopy"):
        # Structured VistA Urology Procedure Note format. Cysto reports
        # have labeled fields like:
        #   Obstructive assessment: bilobar hypertrophy with intravesical protrusion
        #   Bladder Neck: Open, high
        #   Bladder mucosa: Normal
        #   Bladder calculus: Not seen
        #   Trabeculation grade: 0 (none)
        #   Median lobe component: present
        # Walk a known label list and concatenate the non-empty values
        # into a clinically useful summary. This is the highest-priority
        # path because it captures structured findings the prose-style
        # regex misses.
        structured_fields = (
            "Obstructive assessment",
            "Bladder Neck",
            "Median lobe component",
            "Bladder mucosa",
            "Bladder Wall",
            "Bladder calculus",
            "Trabeculation grade",
            "Diverticulum",
            "Tumor",
            "Trigone",
            "Ureteral orifices",
            "Anterior Urethra",
            "Prostatic Urethra",
            "Stricture",
            "Hutchison Diverticulum",
        )
        structured_bits: List[str] = []
        for label in structured_fields:
            mm = re.search(
                rf"^\s*{re.escape(label)}\s*:\s*([^\n]{{2,120}})$",
                tail_clean if "\n" in tail_clean else tail,  # keep newlines for line-anchored match
                re.IGNORECASE | re.MULTILINE,
            )
            if mm:
                val = mm.group(1).strip().rstrip(".;,")
                # Skip values that are clearly empty or boilerplate
                if val and val.lower() not in ("not assessed", "n/a", "see above"):
                    structured_bits.append(f"{label}: {val}")
        if structured_bits:
            return _clean_finding_text("; ".join(structured_bits[:8]))

        # Common cystoscopy finding markers — prose-style fallback.
        # IMPORTANT: must stop at the next paragraph / section boundary
        # (blank line OR a new labeled section like "Bilateral
        # retrograde pyelograms:" / "Indications:" / "Complications:")
        # so the cysto summary doesn't leak content from co-occurring
        # procedures in the same operative report (Long failure mode).
        # Run match on the ORIGINAL tail (with newlines preserved) so
        # the blank-line / new-label terminators can fire.
        m = re.search(
            r"(?:revealed|showed|demonstrated|notable\s+for|"
            r"notable\s+findings?(?:\s+include)?[:\s]|"
            r"impression[:\s]|findings?[:\s])"
            # Capture up to 250 non-period chars, but stop at:
            #   - blank line (\n\n)
            #   - a new labeled section (line starting with
            #     "Capitalized Word(s):")
            #   - explicit known-other-procedure markers
            r"(?:(?!\n\s*\n|\n\s*[A-Z][A-Za-z\s]+:|"
            r"Bilateral\s+retrograde|retrograde\s+pyelogram|"
            r"Indications|Complications|Description\s+of\s+Operation|"
            r"Specimen|EBL\b|Anesthesia|Disposition|"
            r"stent\s+placed|stent\s+placement)"
            r"[^.])"
            r"{4,250}",
            tail, re.IGNORECASE,
        )
        if m:
            return _clean_finding_text(m.group(0))
        # Quick keyword grab if no explicit "showed" verb. tail_clean
        # here is already truncated to the cysto block (we trim above),
        # so the keyword match cannot leak into pyelogram / stent /
        # description-of-operation content.
        for kw in ("tumor", "papillary", "lesion", "stricture", "bladder neck contracture",
                   "BNC", "normal urethra", "normal bladder", "trabeculation",
                   "stone", "mass", "mucosa", "diverticulum", "no recurrence",
                   "hypertrophy", "intravesical"):
            if re.search(rf"\b{re.escape(kw)}\b", tail_clean, re.IGNORECASE):
                m2 = re.search(
                    rf"[^.]{{0,80}}\b{re.escape(kw)}\b[^.]{{0,80}}",
                    tail_clean, re.IGNORECASE,
                )
                if m2:
                    return _clean_finding_text(m2.group(0))
        # Final fallback: return the truncated cysto body verbatim
        # (capped at 250 chars). Better to surface "no suspicious lower
        # GU tract findings" than to return empty and lose the cysto
        # entirely.
        if tail_clean and len(tail_clean) < 250:
            return _clean_finding_text(tail_clean)

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
            # Hedged / speculative staging ("possible metastatic prostate
            # cancer", "concern for biochemical recurrence", "evaluate for
            # ...") is NOT a confirmed staging decision. Check a wide window
            # on BOTH sides — the qualifier can trail ("... metastatic
            # disease, though not confirmed" / "... versus ablation").
            _lo = max(0, m.start() - 90)
            _hi = min(len(raw_text), m.end() + 90)
            if _HEDGING_RE.search(raw_text[_lo:m.start()]) or \
                    _TRAILING_HEDGE_RE.search(raw_text[m.end():_hi]):
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
# Named oncologic agents / discrete procedures for which a dated mention in
# a prostate-cancer context is sufficient evidence of a real treatment event
# — NO started/completed trigger verb required. This is what catches the
# numbered "Treatment." narrative lists in oncology consults that the
# trigger-gated _find_treatment_events misses. Generic words
# ("radiation therapy", bare "ADT") stay on the trigger-gated path to avoid
# false positives from planning / discussion language. The 3rd field forces
# a status for one-time procedures (always COMPLETED if dated in the past).
_TX_NAMED_VOCAB = (
    (r"radical\s+(?:retropubic\s+)?prostatectomy|\bprostatectomy\b|\bRALP\b|\bRARP\b|\bRRP\b",
     "prostatectomy", "COMPLETED"),
    (r"external\s+beam\s+radiation|radiation\s+therapy|\bEBRT\b|\bIMRT\b|\bSBRT\b|\bXRT\b|\bIGRT\b|radiotherapy",
     "radiation therapy", None),
    (r"androgen\s+deprivation(?:\s+therapy)?|\bADT\b", "ADT", None),
    (r"\bbrachytherapy\b|seed\s+implant", "brachytherapy", "COMPLETED"),
    (r"\babiraterone\b|\bZytiga\b", "abiraterone", None),
    (r"\benzalutamide\b|\bXtandi\b", "enzalutamide", None),
    (r"\bapalutamide\b|apaluatimide|\bErleada\b", "apalutamide", None),
    (r"\bdarolutamide\b|\bNubeqa\b", "darolutamide", None),
    (r"\bbicalutamide\b|\bCasodex\b", "bicalutamide", None),
    (r"\b(?:Lupron|Eligard|leuprolide|degarelix|goserelin|relugolix|Firmagon|Orgovyx)\b",
     "Eligard / leuprolide", None),
    (r"\bdocetaxel\b|\bcabazitaxel\b|\bTaxotere\b|\bJevtana\b", "chemotherapy", None),
    (r"\bsipuleucel(?:-T)?\b|\bProvenge\b", "Provenge", "COMPLETED"),
    (r"\bradium[\s\-]?223\b|\bXofigo\b", "Ra-223", "COMPLETED"),
    (r"\b(?:177\s*Lu|Lu[\s\-]?177|Lutetium[\s\-]?177|Pluvicto)\b", "Lu-177 PSMA", "COMPLETED"),
)

# Local context that forces a COMPLETED classification for the otherwise
# ambiguous named drugs (no forced status). E.g. "Abiraterone April 2019 -
# dcd December 2021", "Docetaxel ... -November 2022".
# Strong, treatment-specific completion signals only. Deliberately EXCLUDES
# "until"/"through" — in these narratives those usually qualify a PSA value
# ("PSA stable until Jul 2014"), not treatment completion, and were
# mislabeling ongoing ADT as completed.
_COMPLETED_CTX_RE = re.compile(
    r"complet|stopped|\bd/?c'?d\b|\bdcd\b|discontinu|finished|\bs/?p\b|status\s+post|"
    r"ceased|off\s+therapy",
    re.IGNORECASE,
)


def _iter_numbered_items(raw_text: str):
    """Yield (item_text, offset) for each item in a numbered list
    ("1. ...", "2. ...") anywhere in the document.

    Item boundaries are the NEXT numbered-line marker, so adjacent
    list lines (no blank line between them — the norm in these
    oncology 'Treatment' lists) are split correctly. The final item is
    cut at the first blank line (section break) so it doesn't run away
    into the following paragraph.
    """
    matches = list(re.finditer(r"(?m)^[ \t]*\d{1,3}\.\s+", raw_text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        item = raw_text[start:end]
        cut = item.find("\n\n")
        if cut != -1:
            item = item[:cut]
        yield item, start


def _first_date_after(item_text: str, pos: int):
    """First parseable date at/after `pos` within the item, else first
    date anywhere in the item. Returns (date_key, date_display) or None."""
    return (_date_in_window(item_text, pos, window=len(item_text) + 1)
            or _date_in_window(item_text, 0, window=len(item_text) + 1))


def _extract_narrative_treatment_list(raw_text: str) -> List[TimelineEvent]:
    """Catch named oncologic treatments documented in narrative HPI
    'Treatment' lists where the trigger-verb-gated extractor fails.

    Parses NUMBERED list items so each treatment is anchored to the date
    in ITS OWN item — not a date that happens to be nearby in a dense
    list or a later summary sentence. A named agent/procedure (from
    _TX_NAMED_VOCAB) in a prostate-cancer context, not negated, is taken
    as a real treatment event.
    """
    events: List[TimelineEvent] = []
    seen = set()
    for item_text, item_offset in _iter_numbered_items(raw_text):
        for tx_pattern, tx_display, forced_status in _TX_NAMED_VOCAB:
            m = re.search(tx_pattern, item_text, re.IGNORECASE)
            if not m:
                continue
            if _preceded_by_negation(item_text, m.start()):
                continue
            # prostate-cancer context evaluated against the full document
            # at this item's location. Use a wide window: a numbered
            # treatment list spans hundreds of chars and the prostate
            # anchor (item 1 "prostatectomy", or "PSMA Therapy for
            # Prostate Cancer") may be far from a middle item.
            if not _in_prostate_context(raw_text, item_offset + m.start(),
                                        window=2000):
                continue
            d = _first_date_after(item_text, m.end())
            if not d:
                continue
            date_key, date_display = d
            if forced_status:
                etype = "TREATMENT_" + forced_status
            else:
                etype = ("TREATMENT_COMPLETED"
                         if _COMPLETED_CTX_RE.search(item_text)
                         else "TREATMENT_STARTED")
            key = (date_key, tx_display.lower())
            if key in seen:
                continue
            seen.add(key)
            detail = re.sub(r"\s+", " ", item_text).strip()
            events.append(TimelineEvent(
                date_key=date_key, date_display=date_display,
                event_type=etype, modality=tx_display,
                detail=detail[:140], source_quote=detail[:200],
            ))
    return events


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
    narrative_tx = _extract_narrative_treatment_list(raw_text)
    events += narrative_tx
    events += _extract_pathology_events(raw_text)
    events += _extract_imaging_events(raw_text)
    events += _extract_staging_events(raw_text)

    # The narrative numbered-list parser anchors each treatment to the date
    # in its own item; the trigger-gated _find_treatment_events uses fuzzy
    # char windows and garbles dense lists (grabbing a neighbor's date or
    # spanning items). When the narrative parser found a modality, treat it
    # as authoritative: drop trigger-gated events for that SAME modality so
    # the wrong-date duplicate doesn't survive.
    _narrative_modalities = {e.modality.lower() for e in narrative_tx if e.modality}

    # Dedup treatment events by (date, modality); prefer the more definitive
    # status (COMPLETED/RESTARTED over STARTED) for the same modality+date.
    _TX_PRIORITY = {"TREATMENT_COMPLETED": 3, "TREATMENT_RESTARTED": 3,
                    "TREATMENT_DECLINED": 2, "TREATMENT_STARTED": 1}
    _best: dict = {}
    _passthrough: List[TimelineEvent] = []
    _dx_best: dict = {}
    _narrative_ids = {id(e) for e in narrative_tx}
    for e in events:
        if e.event_type.startswith("TREATMENT_") and e.modality:
            mod = e.modality.lower()
            # Suppress trigger-gated events for modalities the narrative
            # parser already covers authoritatively.
            if mod in _narrative_modalities and id(e) not in _narrative_ids:
                continue
            k = (e.date_key, mod)
            cur = _best.get(k)
            if cur is None or _TX_PRIORITY.get(e.event_type, 0) > _TX_PRIORITY.get(cur.event_type, 0):
                _best[k] = e
        elif e.event_type == "DIAGNOSIS" and e.modality:
            # A cancer is diagnosed ONCE. The extractor emits a DIAGNOSIS
            # event every time "<cancer> diagnosed" appears near a date —
            # including later encounter/note dates — which lets the HPI pick
            # a recent encounter date (EVERETT: "diagnosed Nov 26 2025")
            # instead of the true diagnosis (2023). Keep only the EARLIEST
            # date per cancer modality.
            mod = e.modality.lower()
            cur = _dx_best.get(mod)
            if cur is None or (e.date_key or "9999") < (cur.date_key or "9999"):
                _dx_best[mod] = e
        else:
            _passthrough.append(e)
    events = _passthrough + list(_best.values()) + list(_dx_best.values())

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

    # Tag each event with its source tier + assertion class (temporal validity).
    events = [_classify_event(e) for e in events]

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


# Strong, unambiguous discontinuation verbs. Deliberately EXCLUDES bare
# "completed" (a chemo CYCLE can be "completed" while the drug continues) —
# the goal is to stop the Plan from saying "Continue abiraterone" when the
# narrative says the patient STOPPED it, without falsely dropping a drug the
# patient is still on.
_MED_DISCONT_VERB = (
    r"(?:stop(?:ped|ping)?|discontinu\w+|\bd/?c'?d\b|\bdc'?d\b|held|"
    r"no\s+longer\s+(?:on|taking|using)|taken\s+off|came\s+off|"
    r"\boff\s+(?:of\s+)?(?:the\s+)?|ceased|declined|elected\s+to\s+stop)"
)


def _drug_discontinued_in_narrative(drug: str, text_lc: str) -> bool:
    """True if the narrative explicitly says `drug` was stopped/discontinued.
    Checks both verb→drug ("stopped abiraterone") and drug→verb
    ("abiraterone was discontinued") within a short window."""
    d = re.escape(drug)
    if re.search(_MED_DISCONT_VERB + r"\s+(?:\w+[\s,]+){0,4}?" + d, text_lc):
        return True
    if re.search(d + r"\b[^.\n]{0,40}?\b(?:was\s+|is\s+|been\s+|now\s+)?"
                 + _MED_DISCONT_VERB, text_lc):
        return True
    return False


def _scan_block_for_meds(block: str) -> List[str]:
    """Pull oncologic / urologic med lines out of one medication block."""
    out: List[str] = []
    seen = set()
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


def detect_current_active_treatments(raw_text: str) -> List[str]:
    """Return the patient's CURRENT medications from the AUTHORITATIVE VistA
    RXOP active-outpatient list (rendered by the normalizer with
    ``RXOP_AUTHORITATIVE_SENTINEL``).

    The VistA "OUTPT RX-ACTIVE ONLY" list is the active meds AS OF COLLECTION
    and is authoritative above all other sources. We read ONLY that block —
    NOT the stale "Active Outpatient Medications" med-reconciliation snapshots
    embedded in older notes (which is what caused the Plan to "continue"
    long-finished drugs). The list is taken as-is; narrative "stopped X"
    statements do NOT override it.

    EXCEPTION — Eligard/ADT: an LHRH agonist is dosed intermittently in-clinic
    and is frequently ABSENT from the active outpatient Rx list even when the
    patient is on ongoing ADT. So ADT active/completed status must come from
    the treatment timeline / administration dates / course-completion language
    (see patient_status_facts.treatment_active_status), NOT from this list's
    presence or absence of Eligard.
    """
    if not raw_text:
        return []
    from .source_normalizers.vista_to_cprs import RXOP_AUTHORITATIVE_SENTINEL
    idx = raw_text.find(RXOP_AUTHORITATIVE_SENTINEL)
    if idx != -1:
        block = raw_text[idx + len(RXOP_AUTHORITATIVE_SENTINEL):]
        # The RXOP block uses "====" lines as separators BETWEEN med entries,
        # so we must NOT stop on those. The block ends at the next real
        # section — a VistA dash-bar ("---- SURGICAL PATHOLOGY ----") or an
        # ALL-CAPS CPRS section header.
        stop_m = re.search(r"\n(?:-{3,}\s*[A-Z]|[A-Z][A-Z /]{4,}:)", block)
        block = block[:stop_m.start()] if stop_m else block[:4000]
        return _scan_block_for_meds(block)

    # Fallback (non-VistA / cprs input with no authoritative block): use the
    # most-recent med-list block only, rather than aggregating every stale
    # snapshot across the document.
    headers = list(_MED_LIST_HEADER_RE.finditer(raw_text))
    if not headers:
        return []
    m = headers[-1]
    block = raw_text[m.end():m.end() + 2000]
    stop_m = re.search(r"^\s*(?:[A-Z]{4,}:\s*$|={5,})", block, re.MULTILINE)
    if stop_m:
        block = block[:stop_m.start()]
    return _scan_block_for_meds(block)


# ---------------------------------------------------------------------------
# Rendering for the prompt
# ---------------------------------------------------------------------------
_TX_FILLER_RE = re.compile(
    r"\b(completed?|start(?:ed)?|initiat(?:ed|e)|underwent|received|ongoing|"
    r"discontinued|therapy|treatment|course|for|prostate|cancer|adenocarcinoma|"
    r"of|the|a|an|on|to|with|status|post|s/?p)\b", re.IGNORECASE)


def _detail_is_redundant(detail: str, modality: str) -> bool:
    """True when ``detail`` conveys nothing beyond ``modality`` + status words
    (so appending it would just duplicate the treatment phrase)."""
    def core(s: str) -> set:
        s = _TX_FILLER_RE.sub(" ", (s or "").lower())
        return set(re.sub(r"[^a-z0-9]+", " ", s).split())
    dw, mw = core(detail), core(modality)
    return not dw or dw <= mw


def format_timeline_for_prompt(events: List[TimelineEvent], limit: int = 30) -> str:
    """Render the timeline as a dated bullet list for inclusion in the
    GROUND TRUTH prompt block. Sorted oldest -> newest so the narrative
    arc reads left-to-right."""
    if not events:
        return "(no dated clinical events extracted)"
    lines: List[str] = []
    # Show up to `limit` events. If overflow, summarize.
    show = events[-limit:] if len(events) > limit else events
    # A definitive treatment that has a COMPLETED event does not also need its
    # STARTED event — the two read as a redundant "initiated ... completed", and
    # an undated START sorts AFTER the completion ("initiated after completed").
    # Keep the completion; drop the same-modality START.
    _completed_mods = {(e.modality or "").strip().lower()
                       for e in show if e.event_type == "TREATMENT_COMPLETED"}
    show = [e for e in show if not (
        e.event_type == "TREATMENT_STARTED"
        and (e.modality or "").strip().lower() in _completed_mods)]
    for e in show:
        date_disp = e.date_display or "(undated)"
        type_lbl = e.event_type.replace("_", " ").title()
        modality = e.modality or ""
        detail = (e.detail or "").strip()
        parts = [f"[{date_disp}]", type_lbl]
        if modality:
            parts.append(f"- {modality}")
        # For TREATMENT_* events the detail is the raw matched phrase (e.g.
        # "radiation therapy completed"), which just repeats the type + modality
        # and makes the HPI render "completed radiation therapy on DATE -
        # radiation therapy completed". Only append detail when it ADDS
        # information (diagnosis/pathology/procedure/imaging findings) and isn't
        # a rewording of the modality + status.
        if detail and not e.event_type.startswith("TREATMENT") \
                and not _detail_is_redundant(detail, modality):
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
