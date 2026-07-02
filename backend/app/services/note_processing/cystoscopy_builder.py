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
    imaging = (extract_imaging(text) or "").strip()
    try:
        labs = (extract_labs(text, header.get("date", "")) or "").strip()
    except Exception:
        labs = ""

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
        f"RELEVANT IMAGING:\n{imaging or '(none on file)'}\n\n"
        f"RELEVANT LABS:\n{labs or '(none on file)'}\n"
    )
    prompt = (
        ctx + "\n"
        "Write the following sections for this cystoscopy note, each on its own "
        "line and prefixed EXACTLY with the header shown (uppercase, colon):\n"
        "INDICATION: a one-line indication for the cystoscopy (the reason it is "
        "being performed for THIS patient).\n"
        "FINDINGS: the anticipated cystoscopic findings of the urethra and "
        "bladder based on the indication and imaging (name a specific lesion/"
        "location if the imaging flagged one; otherwise state no new lesions).\n"
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
        f"Narrative: {narrative}",
        "",
        f"Assessment: {sections['ASSESSMENT']}",
        "",
        f"Plan: {sections['PLAN']}",
        "",
        "Complications: None.",
        f"Disposition: {sections['DISPOSITION'] or 'Patient tolerated the procedure well and was discharged in stable condition.'}",
    ]
    return "\n".join(lines).strip() + "\n"
