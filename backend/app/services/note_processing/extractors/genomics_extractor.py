"""Germline / somatic genomic test reports -> PATHOLOGY RESULTS entries.

VA genetics notes (GENOMIC VVC FOLLOW-UP NOTE, GENETICS NOTE) and outside
reports document a test as a block of labelled lines:

    Laboratory: Fulgent Therapeutics LLC
    TEST: Prostate Cancer Comprehensive Panel with 20 genes:
    ABRAXAS1, ATM, ATR, BRCA1, ... TP53
    Collected: Mar 09,2026
    Report Date: Mar 23,2026
    Result:  NEGATIVE
    No clinically significant sequence or copy-number variants were identified ...

None of the tissue-pathology extractors see this, so the result was missing
from the structured note even when the HPI prose mentioned it. Rendered as:

    03/23/2026 - Germline genetic testing (Fulgent Therapeutics LLC; Prostate
    Cancer Comprehensive Panel with 20 genes: ...; collected 03/09/2026,
    reported 03/23/2026): NEGATIVE - No clinically significant ...
"""
import re
from typing import List, Optional

_LAB_NAMES = (r"Fulgent|Invitae|Myriad|Ambry|Color\s+Genomics|GeneDx|Tempus|"
              r"Foundation\s*(?:One|Medicine)|Caris|Guardant|Decipher|Prolaris|"
              r"Oncotype|NeoGenomics|LabCorp|Quest|Natera|Veracyte|Exact\s+Sciences")
_SOMATIC_HINT = re.compile(r"\b(?:somatic|tumou?r\s+(?:tissue|profiling|sequencing)|tissue\s+(?:NGS|sequencing)|"
                           r"Tempus|Foundation|Caris|Guardant|ctDNA|liquid\s+biopsy|TMB|MSI)\b", re.I)
_MON3 = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _fmt_date(raw: str) -> str:
    """'Mar 09,2026' / 'Mar 9, 2026' / '3/9/2026' -> '03/09/2026'."""
    raw = (raw or "").strip()
    m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s*(\d{4})", raw)
    if m and _MON3.get(m.group(1).lower()):
        return f"{_MON3[m.group(1).lower()]:02d}/{int(m.group(2)):02d}/{m.group(3)}"
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", raw)
    if m:
        y = int(m.group(3)); y = y + 2000 if y < 100 else y
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{y}"
    return raw


def _field(block: str, label: str) -> str:
    m = re.search(rf"(?im)^\s*{label}\s*:\s*([^\n]+)", block)
    return m.group(1).strip() if m else ""


def _genes_after_test(block: str) -> str:
    """The gene list that follows 'TEST: ... genes:' (wrapped lines until a
    blank line or the next labelled field)."""
    m = re.search(r"(?is)TEST\s*:[^\n]*?genes?\s*:\s*\n((?:[^\n]*\S[^\n]*\n?){1,6}?)(?=\s*\n\s*\n|\s*(?:Collected|Result|Report)\s*:)", block)
    if not m:
        return ""
    genes = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(".")
    return genes if re.search(r"[A-Z0-9]{3,}(?:,\s*[A-Z0-9]{3,})+", genes) else ""


def extract_genomic_testing(clinical_document: str) -> List[str]:
    """Return one formatted PATHOLOGY-style line per distinct genomic report."""
    if not clinical_document:
        return []
    out: List[str] = []
    seen = set()
    for m in re.finditer(rf"(?im)^\s*Laboratory\s*:\s*((?:{_LAB_NAMES})[^\n]*)$", clinical_document):
        block = clinical_document[m.start(): m.start() + 2500]
        # stop at the next note header / signature so one report never swallows the next
        cut = re.search(r"\n\s*(?:IMPRESSION|RECOMMENDATIONS?|ASSESSMENT|/es/|LOCAL TITLE|DATE OF NOTE)\s*:?", block)
        if cut:
            block = block[:cut.start()]
        lab = m.group(1).strip()
        test = _field(block, "TEST")
        collected = _fmt_date(_field(block, "Collected"))
        reported = _fmt_date(_field(block, "Report\s+Date"))
        result = _field(block, "Result")
        if not (test or result):
            continue
        # The sentence after Result: ("No clinically significant ... identified")
        detail = ""
        rm = re.search(r"(?im)^\s*Result\s*:[^\n]*\n\s*([^\n]+(?:\n(?![ \t]*[A-Z][A-Za-z ]+:)[^\n]+)?)", block)
        if rm:
            detail = re.sub(r"\s+", " ", rm.group(1)).strip()
            detail = re.split(r"(?<=\.)\s", detail)[0]
        genes = _genes_after_test(block)
        kind = "Somatic/tumor genomic testing" if _SOMATIC_HINT.search(block) and not re.search(r"germline", block, re.I) \
            else "Germline genetic testing"
        key = (lab.lower(), test.lower(), collected)
        if key in seen:
            continue
        seen.add(key)
        parts = [lab]
        if test:
            parts.append(test.rstrip(":") + (f": {genes}" if genes else ""))
        dates = []
        if collected:
            dates.append(f"collected {collected}")
        if reported:
            dates.append(f"reported {reported}")
        if dates:
            parts.append(", ".join(dates))
        head = reported or collected
        line = (f"{head + ' - ' if head else ''}{kind} ({'; '.join(parts)}): "
                f"{result.upper() if result else 'see report'}"
                + (f" - {detail}" if detail else ""))
        out.append(line)
    return out


def extract_genetics_family_history(clinical_document: str, note_date: str = "") -> Optional[str]:
    """Family-history and risk statements from a genetics evaluation (the
    numbered IMPRESSION lines 'Family history of ...', the germline result, and
    the NCCN-criteria statement). None when no genetics note is present. The
    IMPRESSION is looked up INSIDE the genetics note (after its title), never in
    an unrelated note's impression."""
    if not clinical_document:
        return None
    t = re.search(r"(?i)(?:LOCAL|STANDARD)\s+TITLE\s*:[^\n]*(?:GENETIC|GENOMIC)", clinical_document)
    region = clinical_document[t.start():t.start() + 12000] if t else (
        clinical_document if re.search(r"GENETIC|GENOMIC", clinical_document, re.I) else "")
    if not region:
        return None
    m = re.search(r"(?is)IMPRESSION\s*:\s*\n(.*?)(?=\n\s*RECOMMENDATIONS?\s*:|\n\s*/es/|\Z)", region)
    if not m:
        return None
    body = m.group(1)
    items = re.split(r"\n\s*(?=\d+[.)]\s)", "\n" + body)
    keep = []
    for it in items:
        s = re.sub(r"\s+", " ", it).strip()
        s = re.sub(r"^\d+[.)]\s*", "", s)
        if not s:
            continue
        if re.search(r"family history|genetic testing is|does not meet .* criteria|meets? .* criteria", s, re.I):
            keep.append(s)
    if not keep:
        return None
    dm = re.search(r"DATE OF NOTE:\s*([A-Za-z]{3}\s+\d{1,2},\s*\d{4})", region[:m.start()])
    stamp = _fmt_date(dm.group(1)) if dm else _fmt_date(note_date)
    stamp = f" ({stamp})" if stamp else ""
    return f"Genetics evaluation{stamp}: " + " ".join(keep)


_GENOMIC_LINE_RE = re.compile(r"(?im)^[^\n]*\b(?:Germline genetic testing|Somatic/tumor genomic testing)\b[^\n]*$")


def ensure_genomic_lines(synthesized: str, document_pathology: str) -> str:
    """Re-append any genomic-report line from the deterministic pathology
    extraction that the LLM pathology synthesis dropped. A negative germline
    panel is a result, not narrative — it must survive synthesis."""
    if not document_pathology:
        return synthesized
    out = synthesized or ""
    for m in _GENOMIC_LINE_RE.finditer(document_pathology):
        line = m.group(0).strip()
        key = re.sub(r"\s+", " ", line.lower())[:60]
        if key not in re.sub(r"\s+", " ", out.lower()):
            out = (out.rstrip() + "\n\n" + line) if out.strip() else line
    return out
