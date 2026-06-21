"""VistA -> CPRS section normalizer.

VistA exports use short uppercase section codes followed by " - " and a
human-readable description (e.g. "PLL - ALL Problems"). The body of
each section runs from that header to the next section header. There
are no explicit footer markers.

Source-code map (per provider direction, 2026-06-20):

    PLL  - ALL Problems            -> PAST MEDICAL HISTORY (authoritative
                                       source; preserve onset/active dates)
    PLA  - Active Problems         -> ignored (PLL is the truth source)
    RXOP - OUTPT RX-ACTIVE ONLY    -> MEDICATIONS (CPRS Active Outpatient
                                       Medications layout)
    SR   - Surgery Rpt (OR/NON)    -> PAST SURGICAL HISTORY (authoritative
                                       source for dated procedures)
    SP   - Surgical Pathology      -> PATHOLOGY RESULTS (largely compatible
                                       with existing CPRS extractor)
    II   - Imaging Impression      -> IMAGING (FILTERED to urologic only:
                                       CT, MRI, US, Bone Scan, PET/CT/PSMA)
    SLT  - Lab Tests Selected      -> LABS (subset)
    CH   - Chem & Hematology       -> LABS
    MIC  - Microbiology            -> LABS (UA / cultures)
    AR   - Adverse React/Allerg    -> ALLERGIES
    SPN  - TUMOR BOARD             -> pass-through (preserved as cross-
                                       specialty context for the agents)

Every rewriter MUST be:
  - idempotent (running twice produces the same result), and
  - CPRS-safe (running on already-CPRS text MUST NOT corrupt it).

These two properties let the toggle run on mixed-format pastes without
garbling already-correct sections, and let _normalize fail safe.

Body parsers are filled in opportunistically. When the body shape for
a section is not yet known, the rewriter still emits the correct CPRS
section header and passes the raw body through — downstream extractors
will then find the section by header even if their internal parsing is
imperfect, which is strictly better than dropping the section entirely.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# VistA section-header detection
#
# Header shape: "<CODE> - <Description>"  (with one or more spaces between
# the dash and the description). The body runs from the line after the
# header to the line before the next header (or end of document).
# ---------------------------------------------------------------------------
# A header line ends after the description and is immediately followed by
# a blank line (in the TOC) or by body content. We allow either.
_KNOWN_CODES = (
    "PLL", "PLA", "RXOP", "SR", "SP", "II",
    "SLT", "CH", "MIC", "AR", "SPN", "CT",
)

# Real-world VistA headers are surrounded by dash padding so they look
# like ASCII separator bars:
#
#     ----------------------------- PLL - All Problems -----------------------------
#
# The dash padding is optional in our match because some exports omit it
# (e.g. when the section is the first / last in the document). We accept
# either form. The description portion is captured up to the first run
# of trailing dashes or end of line.
_HEADER_RE = re.compile(
    r"^(?:-+\s+)?"
    r"(?P<code>(?:" + "|".join(re.escape(c) for c in _KNOWN_CODES) + r"))"
    r"\s*-\s*"
    r"(?P<desc>[A-Za-z][^\n-]*?(?:\([^)]*\)[^\n-]*?)?)"
    r"\s*(?:-+\s*)?$",
    re.MULTILINE,
)


def split_vista_sections(raw_text: str) -> Dict[str, str]:
    """Split a VistA dump into {code: body_text} pairs.

    Body for code C runs from the line after C's header to the line
    before the next recognized header (or end of document). Body text
    is returned trimmed but with internal newlines preserved.

    When the same code appears more than once, later occurrences
    overwrite earlier ones (most VistA dumps only emit each code once
    but we don't depend on that). To preserve duplicates, switch to
    list semantics in the future.
    """
    if not raw_text:
        return {}

    matches = list(_HEADER_RE.finditer(raw_text))
    if not matches:
        return {}

    sections: Dict[str, str] = {}
    for i, m in enumerate(matches):
        code = m.group("code")
        body_start = m.end()
        body_end = matches[i + 1].start() if (i + 1) < len(matches) else len(raw_text)
        body = raw_text[body_start:body_end].strip("\n")
        sections[code] = body
    return sections


# ---------------------------------------------------------------------------
# Urologic-imaging filter for II (Imaging Impression)
#
# Per provider direction, only the following modalities are clinically
# relevant for the urology note:
#   - CT
#   - MRI
#   - Ultrasound (US)
#   - Bone Scan
#   - PET/CT, specifically PSMA PET/CT
# ---------------------------------------------------------------------------
_UROLOGIC_IMAGING_MODALITY_RE = re.compile(
    r"\b("
    r"CT[\s\-]?\w*|"           # CT, CT-Abd, CT/PEL, etc.
    r"MRI|"                    # any MRI study
    r"MR[\s\-]?(?:[A-Za-z]+)?|"  # MR PROSTATE, MR PELVIS
    r"US|U/?S|Ultrasound|"     # US, U/S, ultrasound
    r"bone\s+scan|"
    r"nuclear\s+med(?:icine)?\s+bone|"
    r"PSMA(?:[\s\-]?PET(?:/CT)?)?|"
    r"PET[\s/]?CT"
    r")\b",
    re.IGNORECASE,
)


def _is_urologic_imaging_study(study_block: str) -> bool:
    """True if the imaging-study block represents one of the urologic
    modalities the provider wants preserved (CT, MRI, US, Bone Scan,
    PSMA PET/CT)."""
    if not study_block:
        return False
    # Limit search to the first ~3 lines — that is where the study
    # name lives in II output. Avoids matching mentions of imaging
    # inside the IMPRESSION prose ("compared to prior CT...").
    head = "\n".join(study_block.split("\n")[:4])
    return bool(_UROLOGIC_IMAGING_MODALITY_RE.search(head))


# ---------------------------------------------------------------------------
# Section rewriters
#
# Each rewriter takes the raw body text of one VistA section and returns
# the CPRS-formatted text for the equivalent CPRS section (including the
# CPRS-style section header). The orchestrator concatenates the outputs.
# Empty / unknown bodies return "".
# ---------------------------------------------------------------------------


_PLL_ROW_RE = re.compile(
    r"^([AI])\s{2,}"                           # Status code A (Active) / I (Inactive)
    r"(.+?)\s{2,}"                             # Problem text (ends at >=2-space gap)
    r"(\d{1,2}/\d{1,2}/\d{4})\s+"              # Last-modified date
    r"(\S.*?)\s*$",                            # Provider name
    re.MULTILINE,
)


def _render_pmh_from_pll(pll_body: str) -> str:
    """Render the CPRS PAST MEDICAL HISTORY section from VistA PLL body.

    VistA PLL format (real):
        ST PROBLEM                                           LAST MOD    PROVIDER
        A  Bacterial dysentery                               02/26/2026  DOE,JOHN W
        A  Hyperlipidemia                                    11/07/2024  DOE,JOHN
        I  Acute sinusitis                                   03/10/2020  DOE,JOHN

    The existing CPRS extract_pmh() function parses per-problem blocks
    that look like the VA "Provider Narrative" shape:
        ===============================================================================
        Provider Narrative
         <DIAGNOSIS> (SCT 12345) (ICD-10-CM Z00.00)
        Date of Onset

    To make extract_pmh() pick up VistA PLL rows, we synthesize that
    shape per active problem. ICD code is set to the placeholder
    "(VISTA-PMH)" so the downstream filter doesn't drop it as
    administrative. Inactive (I) rows are skipped because the
    provider-direction default treats PLL Active as PMH; inactive
    can be added explicitly later if needed.
    """
    if not pll_body or not pll_body.strip():
        return ""

    out_lines: List[str] = []
    seen = set()
    for m in _PLL_ROW_RE.finditer(pll_body):
        status = m.group(1)
        diagnosis = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(",")
        date_mod = m.group(3)
        if status != "A":  # Only active problems
            continue
        if diagnosis.lower() in seen:
            continue
        seen.add(diagnosis.lower())
        # Build a Provider Narrative block with synthetic ICD marker so
        # the existing extractor's diagnosis regex matches.
        out_lines.append("=" * 79)
        out_lines.append("Provider Narrative")
        out_lines.append(f" {diagnosis} (ICD-10-CM VISTA.PLL)")
        out_lines.append("Date of Onset")
        out_lines.append("")
        out_lines.append("Date Modified")
        out_lines.append(f" {date_mod}")
        out_lines.append("Facility: VISTA EXPORT")

    if not out_lines:
        # No parseable rows — fall back to pass-through under CPRS header
        # so the agent at least sees the section.
        return "==================== PAST MEDICAL HISTORY ====================\n" + pll_body.strip() + "\n"

    out_lines.append("=" * 79)
    return (
        "==================== PAST MEDICAL HISTORY ====================\n"
        + "\n".join(out_lines)
        + "\n"
    )


def _render_psh_from_sr(sr_body: str) -> str:
    """Render the CPRS PAST SURGICAL HISTORY section from VistA SR body.

    Per provider: SR is the authoritative source for dated surgeries.
    Other dates/surgeries can be added later. Pass-through with a CPRS
    section header for now.
    """
    if not sr_body or not sr_body.strip():
        return ""
    return "==================== PAST SURGICAL HISTORY ====================\n" + sr_body.strip() + "\n"


def _render_medications_from_rxop(rxop_body: str) -> str:
    """Render the CPRS MEDICATIONS section from VistA RXOP body.

    TODO: VistA's RXOP column layout differs from CPRS — fill in column
    parser once a real RXOP sample is provided. Until then, emit the
    canonical CPRS 'Active Outpatient Medications' header followed by
    the raw body so the medications extractor can still find the block.
    """
    if not rxop_body or not rxop_body.strip():
        return ""
    return "Active Outpatient Medications (including Supplies):\n" + rxop_body.strip() + "\n"


def _render_imaging_from_ii(ii_body: str) -> str:
    """Render the CPRS IMAGING section from VistA II body.

    Per provider: keep ONLY urologic modalities (CT, MRI, US, Bone Scan,
    PSMA PET/CT). Other studies (CXR, mammography, knee X-ray, etc.)
    are dropped.

    VistA II body format:
      Date        Procedure                         CPT   Status      Case #
      04/09/2026  CT ABD & PELVIS W/O IV CONTRAST   74176 Verified    5053
      <blank>
                  Right renal punctate nonobstructing calyceal calculus.
                  Signed by ...
      02/26/2026  CT ABD & PELVIS W/ IV CONTRAST    74177 Verified    5105
      <blank>
                  Short sigmoid colonic segment ...

    Each study row begins with MM/DD/YYYY at column 0; the impression
    text follows on indented lines. We split on the date-prefix pattern,
    parse the title + impression, urologic-filter, and emit each kept
    study in CPRS canonical form:
        STUDY (MMM DD, YYYY):
        IMPRESSION: <impression text>
    """
    if not ii_body or not ii_body.strip():
        return ""

    # Drop the header table row if present
    body = re.sub(
        r"^\s*Date\s+Procedure\s+CPT\s+Status\s+Case\s*#\s*$\n?",
        "", ii_body, count=1, flags=re.IGNORECASE | re.MULTILINE,
    )

    # Split on every line that starts with MM/DD/YYYY (the study header)
    study_starts = [
        m.start() for m in re.finditer(
            r"^\d{1,2}/\d{1,2}/\d{4}\b", body, re.MULTILINE,
        )
    ]
    if not study_starts:
        return ""

    study_blocks: List[str] = []
    for i, start in enumerate(study_starts):
        end = study_starts[i + 1] if (i + 1) < len(study_starts) else len(body)
        chunk = body[start:end].rstrip()
        if chunk:
            study_blocks.append(chunk)

    rendered_studies: List[str] = []
    for chunk in study_blocks:
        # First line: "MM/DD/YYYY  PROCEDURE NAME  CPT  Status  Case#"
        first_line, _, rest = chunk.partition("\n")
        m = re.match(
            r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(.+?)\s+\d{3,5}\s+\w+\s+\d+\s*$",
            first_line,
        )
        if not m:
            # Tolerate slightly different shapes
            m = re.match(
                r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(.+)$", first_line,
            )
            if not m:
                continue
            mm, dd, yyyy = m.group(1), m.group(2), m.group(3)
            title = m.group(4).strip()
            # Strip trailing CPT/status if present
            title = re.sub(r"\s+\d{3,5}\s+\w+(?:\s+\d+)?\s*$", "", title).strip()
        else:
            mm, dd, yyyy, title = m.group(1), m.group(2), m.group(3), m.group(4).strip()

        # Apply urologic filter on the title
        if not _UROLOGIC_IMAGING_MODALITY_RE.search(title) and not _is_urologic_imaging_study(chunk):
            continue
        # Additional drop list: knee, shoulder, spine plain films, IACS MRI,
        # etc. that match "CT" / "MRI" generically but are clearly not GU.
        if re.search(
            r"\b(?:knee|shoulder|spine|cervical|thoracic\s+spine|lumbar\s+spine|"
            r"foot|ankle|hand|wrist|chest|cardiac|brain|head|sinus|"
            r"IACS|internal\s+auditory)\b",
            title, re.IGNORECASE,
        ):
            # ... unless it's GU-specific (CT abd/pel, CT urogram, MR prostate)
            if not re.search(
                r"\b(?:abd|pelvis|pel|urogram|renal|kidney|prostate|"
                r"retroperitoneal|bladder|adrenal)\b",
                title, re.IGNORECASE,
            ):
                continue

        # Parse the impression text from the indented body
        impression_lines: List[str] = []
        for line in rest.split("\n"):
            ln = line.strip()
            if not ln:
                continue
            if ln.startswith("Signed by"):
                continue
            if "READING PHYSICIAN" in ln.upper():
                continue
            if "VHA National Teleradiology" in ln:
                continue
            if "Attention Patients" in ln or "ordering provider" in ln.lower():
                continue
            impression_lines.append(ln)
        impression = " ".join(impression_lines).strip()
        if not impression:
            impression = "(no impression text)"

        # Build CPRS-format header. The downstream extract_human_readable_imaging
        # expects the date in MM/DD/YYYY form and the section header to use
        # 30+ '=' chars on each side.
        date_disp = f"{int(mm):d}/{int(dd):d}/{yyyy}"

        rendered_studies.append(
            f"{title.upper()} ({date_disp}):\nIMPRESSION: {impression}"
        )

    if not rendered_studies:
        return ""
    return (
        "=" * 36 + " IMAGING " + "=" * 36 + "\n"
        + "\n\n".join(rendered_studies)
        + "\n"
        + "=" * 81 + "\n"
    )


def _render_pathology_from_sp(sp_body: str) -> str:
    """Render the CPRS PATHOLOGY RESULTS section from VistA SP body.

    Real VistA SP differences vs CPRS:
      1. Header is " Microscopic Exam:" (note leading space, no
         "/DIAGNOSIS" suffix). CPRS expects "MICROSCOPIC EXAM/DIAGNOSIS:".
      2. The biopsy date sits on the "Collected: MM/DD/YYYY HH:MM" line
         instead of a "Date obtained:" header. CPRS strategy 1b expects
         "Date obtained:" or "Received MMM DD, YYYY".

    We rewrite both so the existing pathology extractor handles the body
    unchanged. Multiple Collected: blocks in the same SP body each get
    their own SURGICAL PATHOLOGY divider so reports stay separable.
    """
    if not sp_body or not sp_body.strip():
        return ""
    body = sp_body

    # Normalize "Microscopic Exam:" -> "** MICROSCOPIC EXAM/DIAGNOSIS:"
    body = re.sub(
        r"^\s*Microscopic\s+Exam\s*:\s*$",
        "** MICROSCOPIC EXAM/DIAGNOSIS:",
        body, flags=re.IGNORECASE | re.MULTILINE,
    )

    # Convert "Collected: MM/DD/YYYY HH:MM" -> "Date obtained: MMM DD, YYYY"
    # (the existing extractor's high-priority strategy 1b key).
    def _collected_to_date_obtained(m: re.Match) -> str:
        mm, dd, yyyy = m.group(1), m.group(2), m.group(3)
        try:
            from datetime import date as _date
            d = _date(int(yyyy), int(mm), int(dd))
            return f"---- SURGICAL PATHOLOGY ----\nDate obtained: {d.strftime('%b %d, %Y')}"
        except Exception:
            return m.group(0)

    body = re.sub(
        r"Collected:\s*(\d{1,2})/(\d{1,2})/(\d{4})\b[^\n]*",
        _collected_to_date_obtained,
        body,
    )

    return "---- SURGICAL PATHOLOGY ----\n" + body.strip() + "\n"


_VISTA_LAB_ROW_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}:\d{2})\s+"
    r"(\S+)\s+"           # specimen (SERUM / URINE / FECES / BLOOD / etc.)
    r"(.+?)\s{2,}"        # test name (variable spaces; ends at >=2-space gap)
    r"([<>]?\d+\.?\d*)"   # numeric result
    r"\s*([HL]?)\s*"      # H / L flag
    r"([A-Za-z%/0-9.]*)"  # units
    r"\s*(.*)$",          # ref range
    re.MULTILINE,
)


def _extract_psa_rows_from_lab_table(body: str) -> List[Tuple[str, str, str]]:
    """Find PSA TOTAL rows in a VistA lab table and return
    [(date_disp, time, value), ...] in source order.
    """
    out: List[Tuple[str, str, str]] = []
    seen = set()
    for m in _VISTA_LAB_ROW_RE.finditer(body):
        mm, dd, yyyy, hhmm = m.group(1), m.group(2), m.group(3), m.group(4)
        test_name = m.group(6).strip().upper()
        value = m.group(7)
        if "PSA" not in test_name:
            continue
        if any(skip in test_name for skip in ("FREE PSA", "%PSA", "PSA%", "PSA-F", "DENSITY")):
            # Only TOTAL PSA enters the curve
            if "TOTAL" not in test_name:
                continue
        try:
            from datetime import date as _date
            d = _date(int(yyyy), int(mm), int(dd))
            date_disp = d.strftime("%b %d, %Y")
        except Exception:
            date_disp = f"{mm}/{dd}/{yyyy}"
        key = (date_disp, hhmm, value)
        if key in seen:
            continue
        seen.add(key)
        out.append((date_disp, hhmm.replace(":", ""), value))
    return out


def _extract_non_psa_lab_lines(body: str) -> List[str]:
    """Pass non-PSA lab rows through in the CPRS '... [671] (date)' shape
    the labs extractor already handles."""
    out: List[str] = []
    seen = set()
    for m in _VISTA_LAB_ROW_RE.finditer(body):
        mm, dd, yyyy = m.group(1), m.group(2), m.group(3)
        test_name = m.group(6).strip()
        value = m.group(7)
        flag = m.group(8)
        units = m.group(9)
        ref = m.group(10).strip()
        if "PSA" in test_name.upper():
            continue
        try:
            from datetime import date as _date
            d = _date(int(yyyy), int(mm), int(dd))
            date_disp = d.strftime("%b %d, %Y")
        except Exception:
            date_disp = f"{mm}/{dd}/{yyyy}"
        # Build CPRS-style line: "NAME  VALUE [H/L]  UNITS  REF  ({date})"
        parts = [test_name.upper(), value]
        if flag:
            parts.append(flag)
        if units:
            parts.append(units)
        if ref:
            parts.append(ref)
        parts.append(f"({date_disp})")
        rendered = "  ".join(parts)
        key = (test_name.upper(), date_disp, value)
        if key in seen:
            continue
        seen.add(key)
        out.append(rendered)
    return out


def _render_labs_from_ch_slt_mic(ch_body: str, slt_body: str, mic_body: str) -> str:
    """Render the CPRS LABS section + PSA CURVE block.

    VistA SLT / CH rows look like:

        MM/DD/YYYY HH:MM  SERUM      TEST NAME            VALUE H  UNITS  REF
        10/20/2025 11:25  SERUM      PSA TOTAL            5.52 H   ng/mL  0.2 - 4.0

    The existing CPRS PSA extractor wants a 'PSA CURVE:' header block
    with rows shaped 'MMM DD, YYYY HHMM  VALUE'. The labs extractor
    wants 'NAME  VALUE  UNITS  REF  (MMM DD, YYYY)'. We synthesize
    both shapes from the parsed VistA rows.

    Source order:
      - PSA TOTAL rows -> consolidated PSA CURVE block (sorted newest
        first as the extractor expects).
      - All other rows from SLT + CH -> CPRS-style LABS lines.
      - MIC rows -> appended verbatim under a MICROBIOLOGY: header
        (the labs extractor passes microbiology through).
    """
    combined_lab_body = "\n".join(b for b in (slt_body, ch_body) if b and b.strip())

    out_parts: List[str] = []

    # PSA CURVE block
    psa_rows = _extract_psa_rows_from_lab_table(combined_lab_body)
    if psa_rows:
        # Newest first
        def _date_key(row):
            from datetime import datetime
            try:
                return datetime.strptime(row[0], "%b %d, %Y")
            except Exception:
                return datetime.min
        psa_rows.sort(key=_date_key, reverse=True)
        psa_lines = ["PSA CURVE:"]
        for date_disp, hhmm, value in psa_rows:
            psa_lines.append(f"[r] {date_disp} {hhmm or '0000'}    {value}")
        out_parts.append("\n".join(psa_lines))

    # Non-PSA labs
    other_lab_lines = _extract_non_psa_lab_lines(combined_lab_body)
    if other_lab_lines:
        out_parts.append("==================== LABS ====================\n" + "\n".join(other_lab_lines))

    if mic_body and mic_body.strip():
        out_parts.append("MICROBIOLOGY:\n" + mic_body.strip())

    if not out_parts:
        return ""
    return "\n\n".join(out_parts) + "\n"


def _render_allergies_from_ar(ar_body: str) -> str:
    """Render CPRS ALLERGIES from VistA AR body. Pass-through under
    the CPRS allergies header."""
    if not ar_body or not ar_body.strip():
        return ""
    return "ALLERGIES:\n" + ar_body.strip() + "\n"


def _render_cross_specialty_from_spn(spn_body: str) -> str:
    """Pass-through for SPN (TUMOR BOARD). Preserved as a labeled block
    so the cross-specialty scanner can pick it up."""
    if not spn_body or not spn_body.strip():
        return ""
    return "==================== TUMOR BOARD ====================\n" + spn_body.strip() + "\n"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def normalize_vista_to_cprs(raw_text: str) -> str:
    """Rewrite a VistA-formatted document into CPRS section layout.

    Strategy:
      1. Split on VistA section headers ("<CODE> - <Description>").
      2. If no recognized headers, return raw_text unchanged (this is
         already-CPRS text or an unrecognized format — the safe choice).
      3. Render each known section into its CPRS equivalent, applying
         the urologic-imaging filter for II.
      4. Append any leading content (text before the first VistA
         header) and any non-routed-but-recognized blocks (e.g. SPN
         tumor board pass-through) so nothing important is silently
         dropped.

    The function is idempotent: running on its own output is a no-op
    because the second pass finds no VistA headers.
    """
    if not raw_text:
        return raw_text or ""

    sections = split_vista_sections(raw_text)
    if not sections:
        # Either CPRS text or an unrecognized format — leave alone.
        return raw_text

    out_parts: List[str] = []

    # Preserve any leading content before the first recognized header
    # (typically a patient-banner or demographic block). We use the
    # raw_text up to the first header position.
    first_header = _HEADER_RE.search(raw_text)
    if first_header and first_header.start() > 0:
        prefix = raw_text[: first_header.start()].rstrip()
        if prefix:
            out_parts.append(prefix)

    # PMH from PLL (authoritative per provider direction)
    out_parts.append(_render_pmh_from_pll(sections.get("PLL", "")))

    # PSH from SR (authoritative per provider direction)
    out_parts.append(_render_psh_from_sr(sections.get("SR", "")))

    # Medications from RXOP
    out_parts.append(_render_medications_from_rxop(sections.get("RXOP", "")))

    # Pathology from SP
    out_parts.append(_render_pathology_from_sp(sections.get("SP", "")))

    # Imaging from II, urologic-only filter
    out_parts.append(_render_imaging_from_ii(sections.get("II", "")))

    # Labs from CH + SLT + MIC
    out_parts.append(_render_labs_from_ch_slt_mic(
        sections.get("CH", ""),
        sections.get("SLT", ""),
        sections.get("MIC", ""),
    ))

    # Allergies from AR
    out_parts.append(_render_allergies_from_ar(sections.get("AR", "")))

    # Tumor board pass-through (SPN)
    out_parts.append(_render_cross_specialty_from_spn(sections.get("SPN", "")))

    # PLA (Active Problems) is intentionally NOT rendered — PLL is the
    # authoritative source per provider direction. The same applies to
    # the standalone CT code in the TOC (subset of II already covered).

    rendered = "\n".join(p for p in out_parts if p)
    return rendered
