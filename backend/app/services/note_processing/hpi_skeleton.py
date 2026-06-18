"""
HPI Skeleton Builder.

Phase 2 of the CC / HPI refactor. The HPI agent stops being a free-form
synthesizer that infers chronology from prior-visit prose and becomes a
renderer over a deterministic story skeleton.

The skeleton is built in Python from:
  - PatientStatusFacts (phase verdict, timeline, active treatments,
    procedure findings, cancer evidence)
  - Today's signals (visit date, today's PSA, today's symptoms,
    demographics)

The LLM's job is to produce fluent clinical prose that walks the
skeleton's blocks in order. It is forbidden from adding events not in
the skeleton or dropping events that are in it. This eliminates the
classic failure modes:
  - "averaging" across prior-visit HPIs and losing a recent treatment
    change (the Ketnick mCRPC ADT-restart case);
  - inventing tests / treatments that were never in the source;
  - forgetting cystoscopy / urodynamics / biopsy / DEXA findings.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skeleton model
# ---------------------------------------------------------------------------
@dataclass
class HPISkeleton:
    """Structured HPI story to be rendered into prose by the LLM."""
    # Demographics + intro
    patient_name: str = ""
    age: str = ""
    sex: str = ""
    phase: str = "UNCERTAIN"
    intro_clause: str = ""           # "returns for follow-up of <phase summary>"

    # Diagnosis (clinically named, with date)
    diagnosis_summary: str = ""      # "prostate adenocarcinoma diagnosed in October 2023..."
    diagnosis_grade: str = ""        # "Gleason 4+3=7, Grade Group 3"
    diagnosis_stage: str = ""        # "intraductal/high-risk features" or "metastatic..."

    # Prior treatments — list of human-readable phrases in date order
    prior_treatment_events: List[str] = field(default_factory=list)

    # Interval events — what happened since the last visit
    interval_events: List[str] = field(default_factory=list)

    # Current regimen — meds the patient is actively taking
    current_regimen: List[str] = field(default_factory=list)

    # PSA / lab trajectory
    psa_trajectory_text: str = ""    # "PSA fell from 34.23 (3/2026) to 0.33 (6/2026)"
    response_assessment: str = ""    # "excellent biochemical response" / "stable"

    # Key procedure findings (cystoscopy, urodynamics, biopsy, DEXA)
    procedure_findings_text: List[str] = field(default_factory=list)

    # Today — symptoms and denials from the most recent gu_note
    today_symptoms_reports: str = ""
    today_symptoms_denials: str = ""

    # Outstanding non-cancer urologic issues
    outstanding_issues: List[str] = field(default_factory=list)

    # Provenance for verification
    sources_used: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase-specific opening clauses
# ---------------------------------------------------------------------------
_PHASE_INTRO = {
    "TREATMENT_NAIVE":
        "returns for urology follow-up",
    "ON_INITIAL_TREATMENT":
        "returns for urology follow-up during ongoing treatment for prostate cancer",
    "POST_TREATMENT_SURVEILLANCE":
        "returns for urology surveillance follow-up after prior prostate-cancer treatment",
    "BIOCHEMICAL_RECURRENCE":
        "returns for urology follow-up of biochemical recurrence after prior treatment for prostate cancer",
    "SALVAGE_OR_RESTART":
        "returns for urology follow-up after recent restart of androgen-deprivation therapy",
    "METASTATIC_HORMONE_SENSITIVE":
        "returns for urology follow-up of metastatic hormone-sensitive prostate cancer on systemic therapy",
    "METASTATIC_CASTRATION_RESISTANT":
        "returns for urology follow-up of metastatic castration-resistant prostate cancer on combination systemic therapy",
    "PROGRESSION":
        "returns for urology follow-up of prostate cancer with disease progression on prior therapy",
    "UNCERTAIN":
        "returns for urology follow-up",
}


# ---------------------------------------------------------------------------
# Skeleton builders
# ---------------------------------------------------------------------------
def _format_diagnosis(timeline, cancer_evidence, pathology_data) -> Tuple[str, str, str]:
    """Return (summary, grade, stage_extras)."""
    if not timeline and not cancer_evidence:
        return "", "", ""

    # Earliest DIAGNOSIS event for the date
    dx_event = None
    for e in timeline:
        if e.event_type == "DIAGNOSIS":
            if dx_event is None or e.date_key < dx_event.date_key:
                dx_event = e
    dx_date = dx_event.date_display if dx_event else ""

    # Earliest PATHOLOGY event with a Gleason or GG marker
    grade = ""
    for e in timeline:
        if e.event_type == "PATHOLOGY":
            m = re.search(
                r"Gleason\s+\d\s*\+\s*\d(?:\s*=\s*\d+/?10?)?|Grade\s+Group\s+[1-5]|GG[1-5]",
                e.detail, re.IGNORECASE,
            )
            if m:
                grade = m.group(0)
                break
    # Fallback to cancer_evidence quotes
    if not grade:
        for ev in cancer_evidence:
            m = re.search(
                r"Gleason\s*\d\s*[\+/]\s*\d|Grade\s+Group\s+[1-5]|GG[1-5]",
                ev, re.IGNORECASE,
            )
            if m:
                grade = m.group(0)
                break

    summary_parts = ["prostate adenocarcinoma"]
    if dx_date:
        summary_parts.append(f"diagnosed in {dx_date}")
    summary = " ".join(summary_parts)

    # Look for intraductal / high-risk markers in pathology / cancer evidence
    stage_extras = ""
    text_search = "\n".join([
        pathology_data or "",
        "\n".join(cancer_evidence),
        "\n".join(e.detail for e in timeline if e.event_type == "PATHOLOGY"),
    ])
    if re.search(r"intraductal|cribriform|high[\-\s]?risk", text_search, re.IGNORECASE):
        stage_extras = "with intraductal/high-risk features"

    return summary, grade, stage_extras


def _normalize_modality(m: str) -> str:
    """Collapse equivalent modality names so dedup works."""
    s = (m or "").strip().lower()
    if s in ("adt", "eligard / leuprolide", "eligard", "leuprolide", "lupron"):
        return "adt"
    if s in ("radiation therapy", "ebrt", "imrt", "sbrt", "igrt", "xrt"):
        return "radiation"
    if s in ("brachytherapy", "seed implant"):
        return "brachytherapy"
    if s == "prostatectomy" or "prostatectomy" in s:
        return "prostatectomy"
    if "abiraterone" in s:
        return "abiraterone"
    if "enzalutamide" in s:
        return "enzalutamide"
    if "apalutamide" in s:
        return "apalutamide"
    if "darolutamide" in s:
        return "darolutamide"
    if "focal" in s:
        return "focal therapy"
    return s


def _staging_priority(modality: str) -> int:
    """Higher = more clinically actionable, used to keep one canonical
    staging event when multiple are present."""
    s = (modality or "").lower()
    if "castration-resistant" in s or "mcrpc" in s:
        return 4
    if "hormone-sensitive" in s or "mhspc" in s:
        return 3
    if "metastatic" in s:
        return 2
    if "recurrence" in s or "recurrent" in s:
        return 1
    return 0


def _format_treatment_timeline(timeline) -> List[str]:
    """Render the prior-treatment events as ordered human phrases.

    Dedup strategy:
      - For TREATMENT_STARTED / COMPLETED / RESTARTED / DECLINED: collapse
        by normalized (event_type, modality_canonical). Keep the earliest
        date_key for STARTED and COMPLETED; keep the latest for RESTARTED.
      - For STAGING_DECISION: keep at most one event per priority tier.
        mCRPC wins over plain "metastatic"; "biochemical recurrence" only
        emitted if no later mCRPC / mHSPC.

    This drops the bag of duplicate "classified as metastatic prostate
    cancer" entries that came from the same fact being mentioned in
    multiple prior notes.
    """
    # Bucket events
    started: dict = {}     # modality_canon -> (date_key, date_display)
    completed: dict = {}
    restarted: dict = {}
    declined: dict = {}
    staging_by_tier: dict = {}  # priority -> (date_key, date_display, modality)

    for e in timeline:
        mod_canon = _normalize_modality(e.modality)
        if not mod_canon:
            continue
        dk = e.date_key or "9999"
        dd = e.date_display or "(undated)"

        if e.event_type == "TREATMENT_STARTED":
            if mod_canon not in started or dk < started[mod_canon][0]:
                started[mod_canon] = (dk, dd)
        elif e.event_type == "TREATMENT_COMPLETED":
            if mod_canon not in completed or dk < completed[mod_canon][0]:
                completed[mod_canon] = (dk, dd)
        elif e.event_type == "TREATMENT_RESTARTED":
            if mod_canon not in restarted or dk > restarted[mod_canon][0]:
                restarted[mod_canon] = (dk, dd)
        elif e.event_type == "TREATMENT_DECLINED":
            if mod_canon not in declined or dk > declined[mod_canon][0]:
                declined[mod_canon] = (dk, dd)
        elif e.event_type == "STAGING_DECISION":
            tier = _staging_priority(e.modality)
            if tier == 0:
                continue
            prev = staging_by_tier.get(tier)
            if (prev is None) or (dk > prev[0]):
                staging_by_tier[tier] = (dk, dd, e.modality)

    # Emit ordered rows
    rows: List[Tuple[str, str]] = []  # (date_key, phrase)
    for mod, (dk, dd) in started.items():
        rows.append((dk, f"[{dd}] started {mod}"))
    for mod, (dk, dd) in completed.items():
        rows.append((dk, f"[{dd}] completed {mod}"))
    for mod, (dk, dd) in restarted.items():
        rows.append((dk, f"[{dd}] RESTARTED {mod}"))
    for mod, (dk, dd) in declined.items():
        rows.append((dk, f"[{dd}] declined {mod}"))

    # Staging — keep only the highest-priority tier (gives one clean line)
    if staging_by_tier:
        top_tier = max(staging_by_tier.keys())
        dk, dd, modality = staging_by_tier[top_tier]
        rows.append((dk, f"[{dd}] classified as {modality}"))
        # Also keep "biochemical recurrence" if it's distinct from the top
        if top_tier > 1 and 1 in staging_by_tier:
            dk_br, dd_br, mod_br = staging_by_tier[1]
            rows.append((dk_br, f"[{dd_br}] classified as {mod_br}"))

    rows.sort(key=lambda r: r[0])
    return [phrase for _, phrase in rows]


def _format_psa_trajectory(raw_clinical_text: str, limit: int = 4) -> Tuple[str, str]:
    """Return (trajectory_text, response_assessment)."""
    if not raw_clinical_text:
        return "", ""
    from .clinical_timeline import extract_psa_trajectory
    pts = extract_psa_trajectory(raw_clinical_text)
    if not pts:
        return "", ""
    pts_recent = pts[:limit]
    # Sort oldest -> newest for narrative flow
    pts_recent_sorted = list(reversed(pts_recent))
    pieces = [f"{val} ng/mL ({display})" for _, display, val in pts_recent_sorted]
    trajectory = " -> ".join(pieces) if len(pieces) > 1 else (pieces[0] if pieces else "")

    # Assess direction
    response = ""
    if len(pts_recent) >= 2:
        first = pts_recent_sorted[0][2]
        last = pts_recent_sorted[-1][2]
        if last < first * 0.5 and last < 1.0:
            response = "excellent biochemical response"
        elif last < first * 0.8:
            response = "biochemical response"
        elif last > first * 1.5 and last > 0.2:
            response = "biochemical progression"
        else:
            response = "stable PSA trend"
    return trajectory, response


def _format_procedure_findings(procedure_findings) -> List[str]:
    """Render procedure findings the HPI should reference."""
    out: List[str] = []
    seen = set()
    for pf in procedure_findings:
        if not pf.finding:
            continue
        # Avoid duplicates by (procedure, finding[:40])
        key = (pf.procedure.lower(), pf.finding.lower()[:40])
        if key in seen:
            continue
        seen.add(key)
        date_part = f" {pf.date_display}" if pf.date_display and pf.date_display != "(undated)" else ""
        out.append(f"[{pf.date_display}] {pf.procedure}{date_part}: {pf.finding}")
        if len(out) >= 6:
            break
    return out


_REGIMEN_DROP_HINTS = (
    "completed", "started eligard and chemo recently", "feels",
    "calcium 8.8 mg/dl", "history of hypokalemia",
    "is patient on calcium/vitamin d",  # boilerplate prefix
    "restart lupron as soon",            # planning text
)
_REGIMEN_KEEP_PATTERNS = (
    re.compile(r"\bEligard\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bLupron\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bleuprolide\b[^\n]*", re.IGNORECASE),
    re.compile(r"\babiraterone\b[^\n]*", re.IGNORECASE),
    re.compile(r"\benzalutamide\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bapalutamide\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bdarolutamide\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bprednisone\b[^\n]*", re.IGNORECASE),
    re.compile(r"\btamsulosin\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bfinasteride\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bdutasteride\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bsilodosin\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bdegarelix\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bsipuleucel\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bdocetaxel\b[^\n]*", re.IGNORECASE),
    re.compile(r"\bcabazitaxel\b[^\n]*", re.IGNORECASE),
    re.compile(r"calcium\s+(?:\d+\s*mg)?\s*/?\s*(?:vit(?:amin)?\s*D)?", re.IGNORECASE),
)


def _clean_current_regimen(items: List[str]) -> List[str]:
    """Filter the raw active-treatments list down to actual med lines.

    The upstream detector pulls anything that mentions an oncology hint
    word from the most recent medications block, which sweeps in label
    fragments ("S-IV Prostate cancer ON Abiraterone + Prednisone with
    history of hypokalemia"), problem-list lines, and free-text comments
    ("He started eligard and chemo recently. He feels..."). The cleanup
    keeps only entries that match a known med-name pattern AND are
    short / well-formed enough to look like a regimen line.
    """
    if not items:
        return []
    out: List[str] = []
    seen = set()
    for raw in items:
        if not raw or not raw.strip():
            continue
        line = re.sub(r"\s+", " ", raw).strip()
        # Drop entries whose start is a known noise hint
        ll = line.lower()
        if any(ll.startswith(h) for h in _REGIMEN_DROP_HINTS):
            continue
        # Drop entries that are sentences (have multiple verbs / commas)
        if line.count(".") >= 2 or len(line) > 180:
            continue
        # Keep only if a known med name matches
        med_hit = False
        for pat in _REGIMEN_KEEP_PATTERNS:
            if pat.search(line):
                med_hit = True
                break
        if not med_hit:
            continue
        # Normalize problem-list-style prefixes
        line = re.sub(r"^[-*\d.)\s]+", "", line).strip()
        line = re.sub(r"\s+", " ", line)
        # Dedup by the canonical med name found
        canon_match = None
        for pat in _REGIMEN_KEEP_PATTERNS:
            m = pat.search(line)
            if m:
                canon_match = m.group(0).lower()
                break
        key = canon_match or line.lower()
        # Collapse near-duplicates
        normalized_key = re.sub(r"[^a-z]+", "", key)[:20]
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        out.append(line[:140])
        if len(out) >= 8:
            break
    return out


def _format_today_symptoms(gu_notes) -> Tuple[str, str]:
    """Pull TODAY symptoms from the most recent gu_note's HPI."""
    if not gu_notes:
        return "", ""
    # Take the most recent note that has an HPI / content body
    sorted_notes = sorted(
        gu_notes,
        key=lambda n: n.get("date", "") or n.get("_source_date", ""),
        reverse=True,
    )
    target = sorted_notes[0] if sorted_notes else None
    if not target:
        return "", ""
    text = target.get("content") or target.get("HPI") or ""
    if not text:
        return "", ""

    # Drop template scraps before matching (column headers, etc.)
    _NOISE = (
        "PSA-F", "PSA%", "TUMOR SCREENS", "Ref range", "PSA-F PSA%",
        "BPI ", "Pain Inventory",
    )
    if any(n.lower() in text.lower() for n in ("---- TUMOR SCREENS ----", "SERUM PSA PSA-F")):
        # Trim template tail so the regex doesn't reach into it
        cut = re.search(r"---- TUMOR SCREENS ----|SERUM PSA PSA-F", text, re.IGNORECASE)
        if cut:
            text = text[:cut.start()]

    def _accept(snippet: str) -> bool:
        if any(n in snippet for n in _NOISE):
            return False
        # Reject if snippet contains too many capital-letter tokens (templates)
        caps = re.findall(r"\b[A-Z]{2,}\b", snippet)
        if len(caps) >= 3:
            return False
        # Reject if it's mostly punctuation
        if len(re.findall(r"[A-Za-z]", snippet)) < 10:
            return False
        return True

    reports_phrases: List[str] = []
    denies_phrases: List[str] = []
    seen_r: set = set()
    seen_d: set = set()

    for m in re.finditer(
        r"(?:he\s+|she\s+|pt\s+|patient\s+)?reports?\s+(?:ongoing\s+)?"
        r"([^.]{4,150})\.",
        text, re.IGNORECASE,
    ):
        snippet = re.sub(r"\s+", " ", m.group(1)).strip()
        if not (4 < len(snippet) < 150) or not _accept(snippet):
            continue
        k = re.sub(r"[^a-z0-9]+", "", snippet.lower())[:40]
        if k in seen_r:
            continue
        seen_r.add(k)
        reports_phrases.append(snippet)
        if len(reports_phrases) >= 3:
            break

    for m in re.finditer(
        r"den(?:ies|y)\s+([^.]{4,250})\.",
        text, re.IGNORECASE,
    ):
        snippet = re.sub(r"\s+", " ", m.group(1)).strip()
        if not (4 < len(snippet) < 250) or not _accept(snippet):
            continue
        k = re.sub(r"[^a-z0-9]+", "", snippet.lower())[:50]
        if k in seen_d:
            continue
        seen_d.add(k)
        denies_phrases.append(snippet)
        if len(denies_phrases) >= 2:
            break

    return ("; ".join(reports_phrases[:3]), "; ".join(denies_phrases[:2]))


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------
def build_hpi_skeleton(
    facts,
    raw_clinical_text: str,
    patient_name: str = "",
    age: str = "",
    sex: str = "",
    pathology_data: str = "",
    gu_notes: Optional[List[dict]] = None,
) -> HPISkeleton:
    """Build the HPI skeleton from facts + raw text + per-note context."""
    skel = HPISkeleton(
        patient_name=patient_name or "",
        age=age or "",
        sex=sex or "",
        phase=facts.current_phase or "UNCERTAIN",
        intro_clause=_PHASE_INTRO.get(facts.current_phase, _PHASE_INTRO["UNCERTAIN"]),
    )

    dx_summary, dx_grade, dx_extras = _format_diagnosis(
        facts.clinical_timeline, facts.cancer_evidence, pathology_data,
    )
    skel.diagnosis_summary = dx_summary
    skel.diagnosis_grade = dx_grade
    skel.diagnosis_stage = dx_extras

    skel.prior_treatment_events = _format_treatment_timeline(facts.clinical_timeline)
    skel.psa_trajectory_text, skel.response_assessment = _format_psa_trajectory(
        raw_clinical_text or "",
    )
    skel.procedure_findings_text = _format_procedure_findings(facts.procedure_findings)
    skel.current_regimen = _clean_current_regimen(facts.current_active_treatments or [])

    reports, denies = _format_today_symptoms(gu_notes or [])
    skel.today_symptoms_reports = reports
    skel.today_symptoms_denials = denies

    return skel


# ---------------------------------------------------------------------------
# Render skeleton as prompt input
# ---------------------------------------------------------------------------
def format_skeleton_for_prompt(skel: HPISkeleton) -> str:
    """Render the skeleton as a structured prompt block for the HPI agent."""
    lines = ["=== HPI STORY SKELETON (render every section, in order) ==="]

    # 1. INTRO
    intro = "1. INTRO:"
    name_age = " ".join(filter(None, [
        skel.patient_name,
        f"{skel.age}-year-old" if skel.age else "",
        skel.sex.lower() if skel.sex else "",
    ])).strip()
    if name_age:
        intro += f"\n   Open with: '{name_age} {skel.intro_clause}.'"
    else:
        intro += f"\n   Open with: 'Patient {skel.intro_clause}.'"
    lines.append(intro)

    # 2. DIAGNOSIS
    if skel.diagnosis_summary:
        d_parts = [skel.diagnosis_summary]
        if skel.diagnosis_grade:
            d_parts.append(f"({skel.diagnosis_grade})")
        if skel.diagnosis_stage:
            d_parts.append(skel.diagnosis_stage)
        lines.append("2. DIAGNOSIS:")
        lines.append(f"   Describe: {' '.join(d_parts)}.")

    # 3. PRIOR TREATMENT TIMELINE
    if skel.prior_treatment_events:
        lines.append("3. TREATMENT HISTORY (walk in order, do NOT collapse, do NOT skip):")
        for evt in skel.prior_treatment_events:
            lines.append(f"   - {evt}")

    # 4. PSA / RESPONSE
    if skel.psa_trajectory_text:
        line = f"4. PSA TRAJECTORY: {skel.psa_trajectory_text}"
        if skel.response_assessment:
            line += f"  -> {skel.response_assessment}"
        lines.append(line)

    # 5. PROCEDURE FINDINGS
    if skel.procedure_findings_text:
        lines.append("5. PROCEDURE FINDINGS (reference these by date):")
        for pf in skel.procedure_findings_text:
            lines.append(f"   - {pf}")

    # 6. CURRENT REGIMEN
    if skel.current_regimen:
        lines.append("6. CURRENT REGIMEN (these are the patient's currently active meds — name them all):")
        for med in skel.current_regimen:
            lines.append(f"   - {med}")

    # 7. TODAY
    today_lines = []
    if skel.today_symptoms_reports:
        today_lines.append(f"reports {skel.today_symptoms_reports}")
    if skel.today_symptoms_denials:
        today_lines.append(f"denies {skel.today_symptoms_denials}")
    if today_lines:
        lines.append("7. TODAY:")
        lines.append("   " + "; ".join(today_lines))

    lines.append("=== END HPI SKELETON ===")
    lines.append(
        "RENDER RULES:\n"
        "  - Walk sections 1-7 IN ORDER. Do not reorder, merge, or skip.\n"
        "  - Use only the dated facts in the skeleton; do NOT invent dates,\n"
        "    PSA values, treatments, biopsy grades, or imaging findings.\n"
        "  - Every TREATMENT HISTORY bullet MUST appear in the rendered prose\n"
        "    with its date and verb (started / completed / RESTARTED /\n"
        "    declined / classified as). Especially: a RESTARTED event MUST\n"
        "    be rendered as a restart — never as 'continued' or 'completed'.\n"
        "  - The CURRENT REGIMEN list IS the patient's current medication\n"
        "    plan. Every med listed must be named in the narrative (or in\n"
        "    a 'continues' summary clause) so downstream Plan / Assessment\n"
        "    do not drop a continuing therapy.\n"
        "  - Use the PROCEDURE FINDINGS section to reference cystoscopy /\n"
        "    urodynamics / biopsy / DEXA results by date when present.\n"
        "  - Output 1-2 paragraphs of fluent clinical prose. No bullets in\n"
        "    the final HPI. No meta-commentary. Start directly with the\n"
        "    INTRO sentence."
    )
    return "\n".join(lines)
