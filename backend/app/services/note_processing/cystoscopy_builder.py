"""Cystoscopy procedure-note builder.

A cystoscopy note is a PROCEDURE note with a fixed template (see cysto.txt), not
a clinic note, so it gets its own single-pass builder rather than the Stage-1/
Stage-2 clinic pipeline. It:

  1. Extracts the header (name / SSN-last4 / date), the indication, and the
     relevant imaging + labs for the visit from the source document.
  2. Emits the fixed procedure narrative, branching MALE vs FEMALE for the
     urethral / pelvic exam portion.
  3. LLM-generates the per-patient sections — anticipated bladder/urethra
     Findings, Assessment, Plan, and Disposition — grounded ONLY in that
     patient's indication, imaging, labs, and known GU diagnoses.

The generated sections are anticipatory (the provider edits them after the
actual procedure); they are specific to the patient's workup, never a fixed
template.
"""
import re
from typing import Optional

from .llm_helper import synthesize_with_llm
from .extractors import extract_imaging
from .extractors.lab_extractor import extract_labs
from .gu_diagnoses import detect_patient_sex, detect_gu_diagnoses

_FIXED_INTRO = (
    "After informed consent was obtained, the patient was brought to the "
    "procedure room, disrobed, draped, and prepped in the usual sterile "
    "fashion. 2% Lidocaine jelly was placed into the urethra by the nurse/"
    "medical assistant. A flexible cystoscope with a video camera was placed "
    "into the urethra and advanced through the urethra forward towards the "
    "bladder."
)
_MALE_EXAM = (
    "The Fossa Navicularis and anterior urethra were examined, as well as the "
    "bulbar urethra, membranous urethra and prostatic urethra."
)
_FEMALE_EXAM = (
    "A bimanual pelvic exam was performed, examining for pelvic floor descent, "
    "weakness, leakage with valsalva, and urethral hypermobility (Q-tip test). "
    "The urethra was examined for strictures, diverticula, or lesions."
)
_BLADDER_INSPECTION = (
    "The bladder was fully inspected, including the trigone, floor, posterior "
    "wall, lateral walls, dome and the bladder neck through retroflexion. "
    "Findings included:"
)

_CYSTO_SYSTEM = (
    "You are a board-certified urologist documenting a flexible cystoscopy. "
    "Using ONLY the patient's clinical data provided, write concise, specific, "
    "clinically-appropriate sections for the cystoscopy note. Anticipate the "
    "findings from the indication and imaging (e.g., a lesion the imaging "
    "flagged, or 'no new lesions' on surveillance). Do NOT invent data that "
    "isn't supported by the workup, do NOT restate the whole history, and do "
    "NOT use markdown. If the patient is female, never reference prostate."
)


def _clean_name(raw: str) -> str:
    """'DOE,JANE MARIE' or 'Lydia Soto' -> 'Lydia Hateya Soto'."""
    raw = raw.strip().strip("|").strip()
    if "," in raw:
        last, first = raw.split(",", 1)
        raw = f"{first.strip()} {last.strip()}"
    return " ".join(w.capitalize() for w in raw.split())


def _extract_header(text: str) -> dict:
    name = ""
    m = re.search(r"^\s*(?:PATIENT|Patient)\s*[:|]\s*([^\n|(]+)", text, re.MULTILINE)
    if m:
        name = _clean_name(m.group(1))
    ssn4 = ""
    m = re.search(r"\b(?:SSN|Social)\D{0,10}(\d{3}[-\s]?\d{2}[-\s]?(\d{4})|\d{5}(\d{4}))",
                  text, re.IGNORECASE)
    if m:
        ssn4 = (m.group(2) or m.group(3) or "")
    else:
        m = re.search(r"\bxxx[-\s]?xx[-\s]?(\d{4})\b", text, re.IGNORECASE)
        if m:
            ssn4 = m.group(1)
    date = ""
    m = re.search(r"(?:VISIT\s+DATE|DATE\s+OF\s+PROCEDURE|DATE)\s*[:]\s*"
                  r"(\d{1,2}/\d{1,2}/\d{2,4})", text, re.IGNORECASE)
    if m:
        date = m.group(1)
    return {"name": name, "ssn4": ssn4, "date": date}


def _parse_llm_sections(raw: str) -> dict:
    """Split the LLM response into FINDINGS / ASSESSMENT / PLAN / DISPOSITION."""
    keys = ["FINDINGS", "ASSESSMENT", "PLAN", "DISPOSITION"]
    out = {k: "" for k in keys}
    # Match each header and capture until the next known header (or end).
    for i, k in enumerate(keys):
        nxt = "|".join(keys[i + 1:]) or r"\Z"
        m = re.search(rf"{k}\s*:\s*(.*?)(?=\n\s*(?:{nxt})\s*:|\Z)", raw, re.S | re.I)
        if m:
            out[k] = re.sub(r"\s+\n", "\n", m.group(1)).strip()
    return out


_MONTHS_RE = (r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*")


def _parse_year(s: str) -> Optional[int]:
    m = re.search(r"\b(19|20)\d{2}\b", s)
    return int(m.group(0)) if m else None


def _filter_imaging_recent(imaging: str, ref_year: int, years: int = 2) -> str:
    """Keep only imaging study blocks dated within `years` of ref_year. Each
    block starts with a 'STUDY (m/d/yyyy):' header; blocks without a parseable
    recent date are dropped. Cysto notes only show the last 2 years of imaging."""
    if not imaging or not ref_year:
        return imaging
    # Split into blocks at each study header line ("... (date):").
    blocks = re.split(r"(?m)(?=^[A-Z][A-Z0-9,/&\-\. ]+\([\d/]+\):)", imaging)
    kept = []
    for b in blocks:
        if not b.strip():
            continue
        hdr = b.split("\n", 1)[0]
        dm = re.search(r"\((\d{1,2})/(\d{1,2})/(\d{2,4})\)", hdr)
        yr = None
        if dm:
            yr = int(dm.group(3))
            yr = yr + 2000 if yr < 100 else yr
        else:
            yr = _parse_year(hdr)
        if yr is not None and (ref_year - yr) <= years:
            kept.append(b.strip())
    return "\n".join(kept).strip()


def _turbt_history(patient_facts, text: str):
    """Return prior TURBTs as (date_display, finding), oldest -> most recent
    last. Prefers the deterministic clinical timeline; falls back to a text
    scan of sentences mentioning TURBT."""
    rows = {}
    events = getattr(patient_facts, "clinical_timeline", None) or []
    for e in events:
        blob = f"{getattr(e, 'modality', '')} {getattr(e, 'detail', '')} {getattr(e, 'source_quote', '')}"
        if re.search(r"\bTURBT\b|transurethral\s+resection", blob, re.IGNORECASE):
            key = getattr(e, "date_key", "") or getattr(e, "date_display", "")
            rows[key] = (getattr(e, "date_display", "") or "(undated)",
                         (getattr(e, "detail", "") or getattr(e, "modality", "")).strip())
    if not rows:
        for sent in re.split(r"(?<=[.\n])\s+", text):
            if not re.search(r"\bTURBT\b|transurethral\s+resection", sent, re.IGNORECASE):
                continue
            dm = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b", sent) or \
                re.search(rf"{_MONTHS_RE}\.?\s+\d{{4}}", sent)
            disp = dm.group(0) if dm else "(undated)"
            rows[disp] = (disp, re.sub(r"\s+", " ", sent).strip()[:160])
    return [rows[k] for k in sorted(rows.keys())]


def _surveillance_table() -> str:
    """A 45-char-wide ASCII table of the routine post-treatment surveillance
    follow-up timeline (NMIBC-style: cystoscopy + cytology + upper-tract
    imaging at risk-adapted intervals). Every line is exactly 45 chars."""
    W = 45
    C1, C2 = 16, 26  # 1 + 16 + 1 + 26 + 1 = 45
    def row(a, b):
        return "|" + f" {a:<{C1 - 1}}" + "|" + f" {b:<{C2 - 1}}" + "|"
    bar = "+" + "-" * (C1) + "+" + "-" * (C2) + "+"
    title = "|" + "ROUTINE SURVEILLANCE TIMELINE".center(W - 2) + "|"
    lines = [
        "+" + "-" * (W - 2) + "+",
        title,
        bar,
        row("Interval", "Studies"),
        bar,
        row("3 months", "Cystoscopy + cytology"),
        row("6 months", "Cystoscopy + cytology"),
        row("9 months", "Cystoscopy + cytology"),
        row("12 months", "Cysto + cytology + CT"),
        row("18 months", "Cystoscopy + cytology"),
        row("24 months", "Cysto + cytology + CT"),
        row("Then q6 mo", "Cystoscopy + cytology"),
        row("Yearly", "Upper-tract imaging"),
        bar,
    ]
    return "\n".join(lines)


def build_cystoscopy_note(
    clinical_text: str,
    task_config: Optional["object"] = None,
    source_format: str = "cprs",
    patient_facts: Optional["object"] = None,
) -> str:
    """Build a complete cystoscopy procedure note from a clinical document."""
    # Normalize source so extractors see CPRS-canonical layout.
    try:
        from .source_normalizers import normalize_to_cprs
        text = normalize_to_cprs(clinical_text, source_format) or clinical_text
    except Exception:
        text = clinical_text

    header = _extract_header(clinical_text)  # header lives in the raw banner
    sex = (getattr(patient_facts, "patient_sex", "") or detect_patient_sex(text) or "").lower()
    # Cysto notes: only show radiology from the last 2 years.
    ref_year = _parse_year(header.get("date", "") or "") or _parse_year(clinical_text[:4000])
    from datetime import date as _date
    if not ref_year:
        try:
            ref_year = _date.today().year
        except Exception:
            ref_year = None
    imaging = (extract_imaging(text) or "").strip()
    if ref_year:
        imaging = _filter_imaging_recent(imaging, ref_year, years=2)
    try:
        labs = (extract_labs(text, header.get("date", "")) or "").strip()
    except Exception:
        labs = ""

    # Prior TURBTs (dates + findings), oldest first / most recent last.
    turbts = _turbt_history(patient_facts, text)
    turbt_ctx = "\n".join(f"- {d}: {finding}" for d, finding in turbts) if turbts else "(none documented)"

    # Known GU diagnoses give the LLM the indication anchor (bladder tumor,
    # hematuria workup, renal mass, etc.).
    gu = getattr(patient_facts, "other_gu_diagnoses", None) or detect_gu_diagnoses(text)
    dx_summary = "; ".join(
        f"{d.organ} {d.name} [{d.category}]" for d in gu
    ) or "none documented"

    # LLM: indication + the four per-patient sections in one call.
    ctx = (
        f"PATIENT SEX: {sex or 'unknown'}\n"
        f"KNOWN UROLOGIC DIAGNOSES: {dx_summary}\n"
        f"PRIOR TURBTs (oldest first, most recent last):\n{turbt_ctx}\n\n"
        f"RELEVANT IMAGING (last 2 years):\n{imaging or '(none on file)'}\n\n"
        f"RELEVANT LABS:\n{labs or '(none on file)'}\n"
    )
    prompt = (
        ctx + "\n"
        "Write the following sections for this cystoscopy note, each on its own "
        "line and prefixed EXACTLY with the header shown (uppercase, colon):\n"
        "INDICATION: a one-line indication for the cystoscopy (the reason it is "
        "being performed for THIS patient).\n"
        "FINDINGS: the anticipated cystoscopic findings of the urethra and "
        "bladder based on the indication, imaging, and PRIOR TURBT findings "
        "(name a specific lesion/location if flagged; otherwise state no new "
        "lesions; note the resection site of the most recent TURBT if any).\n"
        "ASSESSMENT: a brief clinical impression.\n"
        "PLAN: the next steps (biopsy, fulguration, surveillance interval, "
        "imaging, referrals) appropriate to the findings.\n"
        "DISPOSITION: the post-procedure disposition.\n"
    )
    try:
        llm_raw = synthesize_with_llm(
            prompt, task_config=task_config, system_prompt=_CYSTO_SYSTEM,
            max_tokens=900,
        ) or ""
    except Exception:
        llm_raw = ""

    sections = _parse_llm_sections(llm_raw)
    ind_m = re.search(r"INDICATION\s*:\s*(.*?)(?=\n\s*FINDINGS\s*:|\Z)", llm_raw, re.S | re.I)
    indication = (ind_m.group(1).strip() if ind_m else "").strip()
    if not indication:
        indication = (gu[0].name if gu else "Cystoscopic evaluation of the lower urinary tract")

    exam = _FEMALE_EXAM if sex == "female" else _MALE_EXAM
    findings = sections["FINDINGS"] or "No mucosal lesions, tumors, or stones were identified."
    narrative = f"{_FIXED_INTRO}\n\n{exam}\n\n{_BLADDER_INSPECTION} {findings}"

    lines = [
        "                                              CYSTOSCOPY NOTE",
        f"Patient Name: {header['name']}",
        f"Last 4 SSN: {header['ssn4']}",
        f"Date of Procedure: {header['date']}",
        "",
        f"Indication for Procedure: {indication}",
        "",
        "Relevant Imaging for this Visit:",
        (imaging or "None available for this visit."),
        "",
        "Relevant Labs for this Visit:",
        (labs or "None available for this visit."),
        "",
    ]

    # Prior TURBT history — oldest first, most recent presented last.
    if turbts:
        lines.append("Prior TURBT History (most recent last):")
        for d, finding in turbts:
            lines.append(f"  - {d}: {finding}")
        lines.append("")

    lines += [
        f"Narrative: {narrative}",
        "",
        f"Assessment: {sections['ASSESSMENT']}",
        "",
        f"Plan: {sections['PLAN']}",
        "",
        "Surveillance Schedule (routine post-treatment follow-up):",
        _surveillance_table(),
        "",
        "Complications: None.",
        f"Disposition: {sections['DISPOSITION'] or 'Patient tolerated the procedure well and was discharged in stable condition.'}",
    ]
    return "\n".join(lines).strip() + "\n"
