"""Cystoscopy procedure-note builder.

A cystoscopy note is a PROCEDURE note with a fixed template (cysto_template.txt),
not a clinic note, so it gets its own single-pass builder rather than the
Stage-1/Stage-2 clinic pipeline. The output follows cysto_template.txt exactly:

  Name/SSN/Date header -> INDICATION -> HPI -> IMAGING -> LABS (last 6 months) ->
  UA WITH CULTURES -> PATHOLOGY -> CONSENT (fixed) -> OPERATOR (fixed) ->
  NARRATIVE (fixed boilerplate + fixed physical-exam skeleton) -> ASSESSMENT ->
  PLAN.

Data-driven sections (indication, HPI, imaging, labs, UA/cultures, pathology) are
auto-populated from the source; CONSENT / OPERATOR / the NARRATIVE + exam skeleton
are fixed template text; the exam findings (prostatic-urethra length/pattern,
bladder mucosa, ureteral orifices) are left as fill-in prompts the provider
completes during/after the procedure. ASSESSMENT and PLAN are LLM-anticipated
from the workup and edited by the provider. For female patients the prostatic-
urethra exam line is dropped (no prostate).
"""
import re
from typing import Optional

from .llm_helper import synthesize_with_llm
from .extractors import extract_imaging, extract_medications, extract_pathology
from .extractors.lab_extractor import extract_labs
from .gu_diagnoses import detect_patient_sex, detect_gu_diagnoses

_MON3 = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _parse_mdy(s: str):
    from datetime import date
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{2,4})", s or "")
    if not m:
        return None
    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y = y + 2000 if y < 100 else y
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _filter_labs_recent(labs: str, ref_date_str: str, months: int = 6) -> str:
    """Keep only lab lines dated within `months` of the procedure date (per the
    template's 'only last 6 months or less'). Lines without a parseable date
    (section headers, notes) are kept."""
    if not labs:
        return labs
    from datetime import date, timedelta
    ref = _parse_mdy(ref_date_str) or date.today()
    cutoff = ref - timedelta(days=int(months * 30.5))
    kept = []
    for line in labs.splitlines():
        ld = None
        # "(Aug 04, 2026)" month-name format
        dm = re.search(r"\(([A-Za-z]{3})[a-z]*\s+(\d{1,2}),?\s+(\d{4})\)", line)
        if dm and _MON3.get(dm.group(1).lower()):
            try:
                ld = date(int(dm.group(3)), _MON3[dm.group(1).lower()], int(dm.group(2)))
            except ValueError:
                ld = None
        if ld is None:
            # "(12/03/2025)" numeric M/D/Y format
            dn = re.search(r"\((\d{1,2})/(\d{1,2})/(\d{2,4})\)", line)
            if dn:
                y = int(dn.group(3))
                y = y + 2000 if y < 100 else y
                try:
                    ld = date(y, int(dn.group(1)), int(dn.group(2)))
                except ValueError:
                    ld = None
        if ld is None:
            kept.append(line)      # header / undated line — keep
        elif ld >= cutoff:
            kept.append(line)
    return "\n".join(kept).strip()

# Clinical context the cysto HPI needs beyond imaging/labs/diagnoses.
_ANTICOAG_RE = re.compile(
    r"\b(apixaban|Eliquis|rivaroxaban|Xarelto|dabigatran|Pradaxa|edoxaban|"
    r"warfarin|Coumadin|clopidogrel|Plavix|ticagrelor|prasugrel|aspirin|"
    r"enoxaparin|Lovenox|heparin)\b", re.IGNORECASE)
_HELD_RE = re.compile(
    r"\b(held|hold|holding|stopped?|discontinued?|paused?|d/c'?d?|last\s+dose)\b",
    re.IGNORECASE)
_CULTURE_RE = re.compile(r"urine\s+cultur|urine\s+cx|\bUCx\b|no\s+growth", re.IGNORECASE)
_SYMPTOM_RE = re.compile(
    r"\b(gross|painless|microscopic|micro(?:hematuria)?)?\s*hematuria|"
    r"blood\s+in\s+(?:the\s+)?urine|dysuria|urinary\s+frequency|"
    r"lower\s+urinary\s+tract\s+symptoms|\bLUTS\b|irritative\s+voiding", re.IGNORECASE)


def _scan_sentences(text: str, pattern, max_n: int = 4) -> str:
    """Return up to max_n de-duplicated source sentences matching `pattern`."""
    seen, out = set(), []
    for sent in re.split(r"(?<=[.\n])\s+", text):
        s = re.sub(r"\s+", " ", sent).strip()
        if not s or len(s) < 8 or not pattern.search(s):
            continue
        # Surgery-booking / export boilerplate is not a presenting symptom.
        if re.search(r"Pre-op\s+Diag|Post-op\s+Diag|Operative\s+Proc|Prin\s+Anest|"
                     r"VISTA\s+EXPORT|Facility:", s, re.I):
            continue
        key = s.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(s[:220])
        if len(out) >= max_n:
            break
    return "\n".join(f"- {s}" for s in out)

# Fixed procedure template (cysto_template.txt). The NARRATIVE boilerplate and
# the physical-exam skeleton are verbatim; the exam findings are left as fill-in
# prompts the provider completes during/after the procedure.
_OPERATOR = "Ronald Rodriguez, MD"
_TEMPLATE_NARRATIVE = (
    "After informed consent was obtained and the risk and benefits discussed "
    "with the patient, they were brought to the holding area, and then brought "
    "to the procedure room, where they were prepped and draped in the normal "
    "sterile fashion.  A time out was performed and the patient confirmed an "
    "understanding of the procedure and its indication.  2% Lidocaine jelly was "
    "instilled into the urethra sterilely, and then the patient underwent "
    "flexible cystoscopy with a 16 Fr flexible cystoscope.  The findings were as "
    "follows:"
)
_MALE_EXAM_SKELETON = (
    "-Anterior urethra:  Fossa navicularis, pendulous urethra, bulbar urethra "
    "and membranous urethra were unremarkable.\n\n"
    "-Prostatic urethra:  XXX Length.  Pattern was:\n\n"
    "-Bladder:  The bladder mucosa was inspected and found to have:\n"
    "Retroflexion was performed demonstrating--\n\n"
    "-UO's were orthotopic single systems bilaterally and demonstrated:"
)
# Female patients have no prostatic urethra — drop that line to avoid an
# anatomically-impossible finding.
_FEMALE_EXAM_SKELETON = (
    "-Anterior urethra:  The urethra was unremarkable.\n\n"
    "-Bladder:  The bladder mucosa was inspected and found to have:\n"
    "Retroflexion was performed demonstrating--\n\n"
    "-UO's were orthotopic single systems bilaterally and demonstrated:"
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


_SECTION_KEYS = ["HPI", "INDICATION", "FINDINGS", "ASSESSMENT", "PLAN", "DISPOSITION"]


def _parse_llm_sections(raw: str) -> dict:
    """Split the LLM response into its labeled sections. Each header captures until
    the NEXT known header (in ANY order) or end-of-text, so a section can never
    swallow a following section's content."""
    out = {k: "" for k in _SECTION_KEYS}
    others = "|".join(_SECTION_KEYS)
    for k in _SECTION_KEYS:
        # stop at any OTHER known header (order-independent)
        m = re.search(rf"(?:^|\n)\s*{k}\s*:\s*(.*?)(?=\n\s*(?:{others})\s*:|\Z)",
                      raw, re.S | re.I)
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


# ---- procedure history --------------------------------------------------------
# TURBT (bladder) vs TURP / other OUTLET procedures (prostate) are different
# operations; a "transurethral resection" match alone conflated them and sent a
# scheduled TURP to the model as a PRIOR TURBT.
_TURBT_RE = re.compile(
    r"\bTURBT\b|transurethral\s+resection\s+of\s+(?:the\s+)?bladder(?:\s+tumou?r)?", re.I)
_TURP_RE = re.compile(
    r"\bTURP\b|transurethral\s+resection\s+of\s+(?:the\s+)?prostate|\bHoLEP\b|\bPVP\b|"
    r"photoselective\s+vaporization|\bUroLift\b|\bRezum\b|simple\s+prostatectomy|"
    r"aquablation|\bTUIP\b", re.I)
# Language that means the procedure is proposed / booked / discussed — NOT done.
_PLANNED_RE = re.compile(
    r"\b(?:recommend\w*|plan(?:ned|s|ning)?\s+(?:for|to|on)|scheduled|requested|"
    r"will\s+(?:undergo|proceed|schedule|need|be)|candidate\s+for|consider\w*|"
    r"discuss\w*|interested\s+in|offer\w*|pending|upcoming|to\s+be\s+performed|"
    r"book\w*|prior\s+to\s+(?:planned\s+)?|preop\w*|pre-op\w*)\b", re.I)
# One VistA "SR - Surgery Rpt" entry: date / Status / Operative Proc(s).
_SR_ENTRY_RE = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{4})[ \t]+\S[^\n]*\n[ \t]*Status:[ \t]*\(?([A-Za-z][A-Za-z \-]*?)\)?"
    r"[ \t]{2,}[\s\S]{0,500}?Operative\s+Proc\(s\):[ \t]*([^\n]+(?:\n[ \t]{12,}[^\n]+)*)",
    re.M)
_DATE_TOKEN_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b|" + _MONTHS_RE + r"\.?\s+(?:\d{1,2},?\s+)?\d{4}")


def _surgery_report_entries(text: str):
    """[(date, status_lower, procedure)] from the VistA surgery-report block."""
    out = []
    for m in _SR_ENTRY_RE.finditer(text or ""):
        proc = re.sub(r"\s+", " ", m.group(3)).strip()
        out.append((m.group(1), m.group(2).strip().lower(), proc))
    return out


def _is_planned_status(status: str) -> bool:
    return bool(re.search(r"request|schedul|pending|planned|not\s+started|book", status or ""))


def _is_completed_status(status: str) -> bool:
    return "complet" in (status or "")


def _planned_procedures(text: str):
    """Booked / requested operations that have NOT been performed: [(date, proc, status)]."""
    return [(d, proc, st) for d, st, proc in _surgery_report_entries(text)
            if _is_planned_status(st)]


def _completed_outlet_procedures(text: str):
    """Prior COMPLETED prostate/outlet procedures (TURP, HoLEP, ...): [(date, detail)]."""
    rows = {}
    for d, st, proc in _surgery_report_entries(text):
        if _is_completed_status(st) and _TURP_RE.search(proc):
            rows[d] = (d, proc)
    for sent in re.split(r"(?<=[.\n])\s+", text or ""):
        s = re.sub(r"\s+", " ", sent).strip()
        if not _TURP_RE.search(s) or _PLANNED_RE.search(s):
            continue
        if not re.search(r"\bs/p\b|status[\s-]post|history\s+of|underwent|\bprior\b|"
                         r"\bprevious\b|\bhad\s+a\b|\bpost[\s-]?TURP", s, re.I):
            continue
        dm = _DATE_TOKEN_RE.search(s)
        disp = dm.group(0) if dm else "(undated)"
        rows.setdefault(disp, (disp, s[:160]))
    return [rows[k] for k in sorted(rows)]


def _bladder_pathology_summary(text: str) -> str:
    """The most recent bladder specimen diagnosis — structured report lines
    ('A. BLADDER, TRIGONE, BIOPSY: - ... - NEGATIVE FOR MALIGNANCY.') or the
    narrative 'TURBT ... with pathology showing ...'. '' when none."""
    # The specimen's diagnosis lines run to the next BLANK line; wrapped lines
    # may continue unindented ("PRIOR\n          HEMORRHAGE."), so take every
    # non-blank line and join at the '-' bullets.
    m = re.search(
        r"(?im)^[ \t]*[A-Z]\.[ \t]*(?:URINARY\s+)?BLADDER[^\n]*(?:BIOPSY|TURBT|RESECTION|TUMOU?R|"
        r"LESION)[^\n]*:[ \t]*\n((?:[^\n]*\S[^\n]*\n?){1,12}?)(?:\n[ \t]*\n|\Z)", text or "")
    if m:
        body = re.sub(r"\s+", " ", m.group(1)).strip()
        parts = [p.strip() for p in re.split(r"\s*(?:^|\s)-\s+", body) if p.strip()]
        return "; ".join(parts)[:260]
    m = re.search(r"TURBT[^.\n]{0,80}?patholog\w*\s+(?:showing|showed|revealed|demonstrat\w+|"
                  r"consistent\s+with|:)\s*([^.\n]{5,160})", text or "", re.I)
    return m.group(1).strip() if m else ""


_MALIGNANT_TERM_RE = re.compile(
    r"carcinoma|malignant\b|\bNMIBC\b|\bMIBC\b|carcinoma\s+in\s+situ|\bCIS\b|"
    r"high[-\s]grade|low[-\s]grade|papillary\s+urothelial|urothelial\s+neoplasm|"
    r"\bcancer\b", re.I)
_NEGATED_MALIG_RE = re.compile(
    r"(?:negative\s+for|no\s+evidence\s+of|no\s+|without|free\s+of)\s+(?:\w+\s+){0,3}"
    r"(?:malignan\w*|carcinoma|cancer|dysplasia|neoplas\w*|atypia)", re.I)


def _bladder_malignancy_documented(text: str, patient_facts) -> bool:
    """True only when bladder pathology (or a facts-layer bladder diagnosis)
    asserts malignancy. 'NEGATIVE FOR MALIGNANCY' / 'reactive changes' is NOT."""
    for d in (getattr(patient_facts, "other_gu_diagnoses", None) or []):
        if "bladder" in (getattr(d, "organ", "") or "").lower() and \
                "malignant" in (getattr(d, "category", "") or "").lower():
            return True
    blob = _NEGATED_MALIG_RE.sub(" ", _bladder_pathology_summary(text))
    return bool(_MALIGNANT_TERM_RE.search(blob))


def _turbt_history(patient_facts, text: str):
    """Prior COMPLETED TURBTs as (date_display, finding), oldest -> most recent
    last, with the bladder pathology result attached to the most recent one.
    A recommended / planned TURBT and any TURP (prostate) are excluded."""
    rows = {}
    events = getattr(patient_facts, "clinical_timeline", None) or []
    for e in events:
        blob = f"{getattr(e, 'modality', '')} {getattr(e, 'detail', '')} {getattr(e, 'source_quote', '')}"
        if not _TURBT_RE.search(blob) or _PLANNED_RE.search(blob):
            continue
        key = getattr(e, "date_key", "") or getattr(e, "date_display", "")
        rows[key] = (getattr(e, "date_display", "") or "(undated)",
                     (getattr(e, "detail", "") or getattr(e, "modality", "")).strip())
    for d, st, proc in _surgery_report_entries(text):
        if _is_completed_status(st) and _TURBT_RE.search(proc):
            rows.setdefault(d, (d, proc))
    if not rows:
        for sent in re.split(r"(?<=[.\n])\s+", text or ""):
            s = re.sub(r"\s+", " ", sent).strip()
            if not _TURBT_RE.search(s) or _PLANNED_RE.search(s):
                continue
            dm = re.search(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b", s) or \
                re.search(rf"{_MONTHS_RE}\.?\s+\d{{4}}", s)
            disp = dm.group(0) if dm else "(undated)"
            rows.setdefault(disp, (disp, s[:160]))
    out = [rows[k] for k in sorted(rows.keys())]
    summary = _bladder_pathology_summary(text)
    if out and summary:
        d, finding = out[-1]
        out[-1] = (d, f"{finding} — pathology: {summary}")
    return out


# ---- output guards --------------------------------------------------------------
# The model is told the rules, but a claim it still makes without support is
# removed deterministically: bladder malignancy without malignant pathology, and a
# "prior TURP" / post-TURP anatomy without a completed TURP on record.
_BLADDER_CA_CLAIM_RE = re.compile(
    r"(?:bladder|urothelial|transitional[\s-]cell)\s+(?:cell\s+)?(?:cancer|carcinoma|"
    r"malignancy|neoplasm)|\bNMIBC\b|\bMIBC\b|carcinoma\s+in\s+situ|\bCIS\b|"
    r"papillary\s+urothelial|non-?invasive\s+(?:papillary\s+)?urothelial|"
    r"intravesical\s+(?:BCG|chemotherapy|gemcitabine|mitomycin)|\bBCG\b", re.I)
_CA_NEGATED_RE = re.compile(
    r"(?:no\s+(?:evidence|history|sign)s?\s+of|negative\s+for|without\s+(?:evidence\s+of\s+)?|"
    r"rule\s+out|r/o|to\s+exclude)\s+(?:\w+\s+){0,3}(?:cancer|carcinoma|malignan|urothelial|"
    r"NMIBC|CIS)", re.I)
_PRIOR_TURP_CLAIM_RE = re.compile(
    r"(?:prior|previous|history\s+of|\bs/p\b|status[\s-]post|post[\s-]?)[^.\n]{0,25}?"
    r"(?:\bTURP\b|transurethral\s+resection\s+of\s+(?:the\s+)?prostate)|post-?TURP|"
    r"\bTURP\s+(?:defect|fossa|cavity|bed)|prostatic\s+fossa|resected\s+prostat", re.I)


def _drop_sentences(txt: str, claim_rx, allow_rx=None) -> str:
    if not txt:
        return txt
    kept = []
    for sent in re.split(r"(?<=[.!?])\s+", txt.strip()):
        if claim_rx.search(sent) and not (allow_rx and allow_rx.search(sent)):
            continue
        kept.append(sent)
    return " ".join(kept).strip()


def _fallback_indication(planned, turbts, gu, malignant: bool) -> str:
    if planned:
        d, proc, _ = planned[0]
        short = "TURP" if _TURP_RE.search(proc) else proc.split("(")[0].strip()
        return (f"Pre-procedural cystoscopic evaluation of the lower urinary tract prior to "
                f"planned {short} ({d}).")
    if turbts:
        d, finding = turbts[-1]
        path = finding.split("— pathology:")[-1].strip() if "— pathology:" in finding else ""
        if path and not malignant and re.search(r"negative\s+for\s+malignan|benign|reactive", path, re.I):
            path = "benign, negative for malignancy"
        tail = (" (pathology: " + path + ")") if path else ""
        if malignant:
            return f"Surveillance cystoscopy following TURBT on {d}{tail}."
        return (f"Surveillance cystoscopy following TURBT on {d} for a bladder lesion of "
                f"uncertain significance{tail}.")
    if gu:
        return f"Cystoscopic evaluation for {gu[0].name}."
    return "Cystoscopic evaluation of the lower urinary tract."


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
        labs = _filter_labs_recent(labs, header.get("date", ""), months=6)
    except Exception:
        labs = ""
    try:
        pathology = (extract_pathology(text) or "").strip()
    except Exception:
        pathology = ""

    # Prior COMPLETED TURBTs (dates + findings + pathology), oldest first / most
    # recent last; planned bookings and prostate/outlet procedures kept separate.
    turbts = _turbt_history(patient_facts, text)
    turbt_ctx = "\n".join(f"- {d}: {finding}" for d, finding in turbts) if turbts else "(none documented)"
    planned = _planned_procedures(clinical_text) or _planned_procedures(text)
    planned_ctx = "\n".join(f"- {proc} — booked for {d} (status: {st}; NOT yet performed)"
                            for d, proc, st in planned) if planned else "(none)"
    outlet_done = _completed_outlet_procedures(clinical_text) or _completed_outlet_procedures(text)
    outlet_ctx = "\n".join(f"- {d}: {detail}" for d, detail in outlet_done) if outlet_done else "(none documented)"
    bladder_path = _bladder_pathology_summary(clinical_text) or _bladder_pathology_summary(text)
    bladder_malignant = _bladder_malignancy_documented(clinical_text, patient_facts) or \
        _bladder_malignancy_documented(text, patient_facts)

    # Known GU diagnoses give the LLM the indication anchor (bladder tumor,
    # hematuria workup, renal mass, etc.).
    gu = getattr(patient_facts, "other_gu_diagnoses", None) or detect_gu_diagnoses(text)
    dx_summary = "; ".join(
        f"{d.organ} {d.name} [{d.category}]" for d in gu
    ) or "none documented"

    # Extra clinical context the procedural HPI needs.
    try:
        meds = (extract_medications(text) or "").strip()
    except Exception:
        meds = ""
    anticoag = _scan_sentences(text, _ANTICOAG_RE, 4)
    culture = _scan_sentences(text, _CULTURE_RE, 3)
    symptoms = _scan_sentences(text, _SYMPTOM_RE, 4)
    tobacco = _scan_sentences(text, re.compile(r"tobacco|smok|cigarette|pack[\s-]?year", re.I), 2)

    # LLM: HPI + indication + the four per-patient sections in one call.
    ctx = (
        f"PATIENT SEX: {sex or 'unknown'}\n"
        f"KNOWN UROLOGIC DIAGNOSES: {dx_summary}\n"
        f"PRIOR COMPLETED TURBTs (oldest first, most recent last):\n{turbt_ctx}\n"
        f"BLADDER PATHOLOGY (most recent specimen): {bladder_path or '(none on file)'}\n\n"
        f"PRIOR COMPLETED PROSTATE / OUTLET PROCEDURES (TURP etc.):\n{outlet_ctx}\n\n"
        f"PLANNED / SCHEDULED PROCEDURES — booked but NOT performed:\n{planned_ctx}\n\n"
        f"PRESENTING SYMPTOMS / REASON:\n{symptoms or '(none stated)'}\n\n"
        f"TOBACCO / RISK FACTORS:\n{tobacco or '(none stated)'}\n\n"
        f"ANTICOAGULATION / ANTIPLATELET (and any hold):\n{anticoag or '(none stated)'}\n\n"
        f"URINE CULTURE / PRE-OP:\n{culture or '(none stated)'}\n\n"
        f"CURRENT MEDICATIONS:\n{meds or '(none on file)'}\n\n"
        f"RELEVANT IMAGING (last 2 years):\n{imaging or '(none on file)'}\n\n"
        f"RELEVANT LABS:\n{labs or '(none on file)'}\n"
    )
    prompt = (
        ctx + "\n"
        "Write the following sections for this cystoscopy note, each prefixed "
        "EXACTLY with the header shown (uppercase, colon):\n"
        "HPI: a concise NARRATIVE paragraph (flowing prose, not a list) that "
        "explains why THIS patient is undergoing cystoscopy today. Weave in, "
        "when supported by the data: prior bladder tumor and its resection "
        "date + pathology (e.g. noninvasive urothelial carcinoma), the "
        "presenting symptom (e.g. painless gross hematuria), risk factors "
        "(tobacco), the most recent relevant imaging with its date and finding "
        "(e.g. CT urogram on 6/22/26 with no upper-tract abnormality but "
        "concern for a bladder mass), the pre-procedure urine culture result, "
        "the absence of contraindications, and the anticoagulation status "
        "including when it was held (e.g. 'on apixaban, held 3 days ago'). "
        "State only what the data supports.\n"
        "RULES: (1) A procedure under PLANNED / SCHEDULED has NOT happened — never "
        "call it prior history or describe post-operative anatomy; today's "
        "cystoscopy is typically the pre-operative evaluation for it, so say so "
        "with its booked date. (2) Describe a TURP / outlet procedure as prior ONLY "
        "if it is listed under PRIOR COMPLETED PROSTATE / OUTLET PROCEDURES. (3) Use "
        "cancer / carcinoma / malignancy wording for the bladder ONLY when BLADDER "
        "PATHOLOGY documents a malignant diagnosis; a benign / reactive / "
        "negative-for-malignancy result must be stated as benign, and an "
        "unbiopsied lesion is 'a lesion of uncertain significance'.\n"
        "INDICATION: a one-line indication for the cystoscopy.\n"
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
            max_tokens=1300,
        ) or ""
    except Exception:
        llm_raw = ""

    sections = _parse_llm_sections(llm_raw)
    # Deterministic guards on the model's prose (see _BLADDER_CA_CLAIM_RE /
    # _PRIOR_TURP_CLAIM_RE): drop any sentence asserting bladder malignancy when
    # the pathology does not, and any prior-TURP / post-TURP-anatomy sentence when
    # no completed TURP is on record (a booked TURP is not history).
    for k in ("HPI", "INDICATION", "FINDINGS", "ASSESSMENT", "PLAN"):
        if not bladder_malignant:
            sections[k] = _drop_sentences(sections[k], _BLADDER_CA_CLAIM_RE, _CA_NEGATED_RE)
        if not outlet_done:
            sections[k] = _drop_sentences(sections[k], _PRIOR_TURP_CLAIM_RE)
    cysto_hpi = sections["HPI"]
    indication = sections["INDICATION"] or _fallback_indication(planned, turbts, gu, bladder_malignant)

    # Apply the same active-voice enforcement clinic notes get: no negative
    # recommendations ("no biopsy required"), no ungrounded if-then, no vague
    # "follow guidelines" hand-wave. Keeps affirmative recommendations + findings.
    try:
        from .stage2_builder import _strip_negative_recs
        sections["ASSESSMENT"] = _strip_negative_recs(sections["ASSESSMENT"], is_plan=False)
        # The cysto Plan is a prose paragraph -> sentence-based processing.
        sections["PLAN"] = _strip_negative_recs(sections["PLAN"], is_plan=False)
    except Exception:
        pass

    exam_skeleton = _FEMALE_EXAM_SKELETON if sex == "female" else _MALE_EXAM_SKELETON
    narrative = f"{_TEMPLATE_NARRATIVE}\n\n{exam_skeleton}"

    # Fixed template layout (cysto_template.txt). Data-driven sections (indication,
    # HPI, imaging, labs, UA/cultures, pathology) are auto-populated; CONSENT,
    # OPERATOR and the NARRATIVE + exam skeleton are fixed; the exam findings and
    # ASSESSMENT/PLAN are completed/edited by the provider around the procedure.
    lines = [
        f"Name: {header['name']}",
        f"SSN {header['ssn4']}",
        f"Date: {header['date']}",
        "\t\t\tCYSTOSCOPY NOTE",
        "",
        f"INDICATION: {indication}",
        "",
        f"HPI: {cysto_hpi}",
        "",
        "IMAGING:",
        (imaging or ""),
        "",
        "LABS (only last 6 months or less):",
        (labs or ""),
        "",
        "UA WITH CULTURES IF AVAILABLE:",
        (culture or ""),
        "",
        "PATHOLOGY:",
        (pathology or ""),
        "",
        "CONSENT: Obtained via Web IMED",
        "",
        f"OPERATOR: {_OPERATOR}",
        "",
        f"NARRATIVE:  {narrative}",
        "",
        f"ASSESSMENT:\n{sections['ASSESSMENT']}",
        "",
        f"PLAN:\n{sections['PLAN']}",
    ]
    return "\n".join(lines).rstrip() + "\n"
