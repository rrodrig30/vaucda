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
# Description can contain internal dashes (e.g. "OUTPT RX-ACTIVE ONLY",
# "All Problems", "Chem & Hematology (max 20 occurrences or 6 months)").
# We use a non-greedy capture and require the trailing dash-padding to be
# at least 2 dashes to distinguish "padding dashes" from a "hyphen inside
# the description". The leading prefix requires at least 2 dashes for the
# same reason.
_HEADER_RE = re.compile(
    r"^(?:-{2,}\s+)?"
    r"(?P<code>(?:" + "|".join(re.escape(c) for c in _KNOWN_CODES) + r"))"
    r"\s+-\s+"
    r"(?P<desc>[A-Za-z][^\n]*?)"
    r"\s*(?:-{2,}\s*)?$",
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
# Modalities the provider asked us to preserve.
_UROLOGIC_IMAGING_MODALITY_RE = re.compile(
    r"\b(?:"
    r"CT(?:A|U)?\b|"             # CT / CTA / CTU
    r"MRI|"                      # any MRI study
    r"MR\b|"                     # bare MR (e.g. "MR PROSTATE")
    r"US|U/S|Ultrasound|"        # ultrasound
    r"bone\s+scan|"
    r"nuclear\s+med(?:icine)?\s+bone|"
    r"PSMA(?:[\s\-]?PET(?:/CT)?)?|"
    r"PET[\s/]?CT"
    r")\b",
    re.IGNORECASE,
)

# Urologic anatomy / region keywords. A CT or MRI or US is only
# urologically-relevant when one of these anatomy markers appears in the
# study name. The list is conservative and explicit so non-GU CT/MRI
# (CT MAXILLOFACIAL, CT CHEST, MRI BRAIN, MRI SHOULDER, etc.) drop out.
_UROLOGIC_ANATOMY_RE = re.compile(
    r"\b(?:"
    r"abd(?:omen|ominal)?|"        # CT abd, ABDOMEN, abdominal
    r"pelvis|pelvic|pel\b|"
    r"abd[/&]?\s*pel(?:vis)?|"
    r"urogram|"
    r"renal|kidney|"
    r"retroperitoneal|"
    r"bladder|cystogram|"
    r"prostate|prostatic|"
    r"adrenal|"
    r"scrotum|scrotal|testic|epididym|"
    r"penis|penile|"
    r"ureter|"
    r"renal\s+stone|"
    r"KUB"
    r")\b",
    re.IGNORECASE,
)

# Studies that are urologic by modality alone (no anatomy gate needed).
_UROLOGIC_BY_MODALITY_ALONE_RE = re.compile(
    r"\b(?:"
    r"bone\s+scan|"
    r"nuclear\s+med(?:icine)?\s+bone|"
    r"PSMA(?:[\s\-]?PET(?:/CT)?)?|"
    r"MR\s*UROGRAM"
    r")\b",
    re.IGNORECASE,
)


def _is_urologic_imaging_study(study_block: str) -> bool:
    """True if the imaging-study block represents one of the urologic
    modalities the provider wants preserved.

    Rule: study is urologic if EITHER
      - the modality alone is inherently urologic (bone scan, PSMA PET,
        MR urogram), OR
      - the modality matches CT / CTA / CTU / MRI / MR / US / Ultrasound
        AND the title contains a urologic anatomy keyword (abd / pelvis /
        renal / kidney / bladder / prostate / adrenal / scrotum / testis /
        ureter / urogram / retroperitoneal / KUB).

    Non-urologic CT / MRI titles (CT MAXILLOFACIAL, CT CHEST, MRI BRAIN,
    MRI SHOULDER, KNEE X-ray, etc.) lack a urologic anatomy match and
    correctly drop.
    """
    if not study_block:
        return False
    # Limit search to the first ~3 lines so a passing mention of CT in
    # the IMPRESSION prose ("compared to prior CT") does not promote a
    # non-urologic study into the urologic set.
    head = "\n".join(study_block.split("\n")[:4])
    if _UROLOGIC_BY_MODALITY_ALONE_RE.search(head):
        return True
    if (_UROLOGIC_IMAGING_MODALITY_RE.search(head)
            and _UROLOGIC_ANATOMY_RE.search(head)):
        return True
    return False


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
        # Pre-strip column-truncated SNOMED / ICD code fragments. PLL
        # tables routinely cut "(SNOMED CT 12345)" mid-string at the
        # column boundary, leaving "(SNOMED" alone. Without this, the
        # year-suffix append below produces leaks like "Asthma (SNOMED
        # (2016)" that the downstream extractor's strip regex misses.
        diagnosis = re.sub(r"\s*\((?:SNOMED|SCT|ICD-?(?:9|10)(?:-CM)?)\b[^)]*\)?",
                           "", diagnosis, flags=re.IGNORECASE).rstrip(", *")
        date_mod = m.group(3)
        if status != "A":  # Only active problems
            continue
        if diagnosis.lower() in seen:
            continue
        seen.add(diagnosis.lower())
        # Build a Provider Narrative block with a synthetic ICD-10-CM code
        # so the extractor's diagnosis regex matches AND its strip-codes
        # post-processor removes it from the rendered output. The strip
        # regex requires the code to be shaped [A-Z]\d{1,2}\.?\d*\w* (i.e.
        # real ICD-10) — placeholders like "VISTA.PLL" or "Z00.00" would
        # leak (the former isn't stripped; the latter is on the
        # administrative drop list and would delete every PMH row).
        #
        # N99.89 (other postprocedural complications of genitourinary
        # system) is a real ICD-10-CM code that matches the strip regex,
        # is NOT on any administrative/Z-code drop list, and is
        # urology-adjacent so an unstripped fallthrough would still look
        # plausible. The visible PMH the provider sees is the diagnosis
        # text only; the code is purely a parser anchor that the
        # extractor strips before rendering.
        # Append the year from the LAST MOD date to the diagnosis text
        # so the rendered PMH carries temporal context. After the
        # extractor's strip pass removes the "(ICD-10-CM ...)" anchor,
        # the line reads e.g. "Hyperlipidemia (2024)" — clean and
        # informative, no junk codes. The full date sits in the
        # Date Modified field below for downstream code that wants it.
        year_match = re.search(r"\b(19|20)\d{2}\b", date_mod)
        year_suffix = f" ({year_match.group(0)})" if year_match else ""
        out_lines.append("=" * 79)
        out_lines.append("Provider Narrative")
        out_lines.append(f" {diagnosis}{year_suffix} (ICD-10-CM N99.89)")
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

    Per provider direction: SR is the authoritative source for dated
    surgeries. When SR exists but contains only the literal "No data
    available", we still emit the PSH section header so downstream
    extractors / agents see an explicit "no surgeries documented"
    signal instead of falling back to scraping arbitrary surgical-
    sounding phrases from the rest of the document.
    """
    if not sr_body:
        return ""
    body = sr_body.strip()
    if not body:
        return ""
    if re.fullmatch(r"no\s+data\s+available", body, re.IGNORECASE):
        body = "No prior surgical procedures documented."
    return "==================== PAST SURGICAL HISTORY ====================\n" + body + "\n"


def _render_medications_from_rxop(rxop_body: str) -> str:
    """Render the CPRS MEDICATIONS section from VistA RXOP body.

    VistA RXOP format (real):
        Drug....................................                         Last
                          Rx #         Stat          Qty      Issued     Filled  Rem
        TIRZEPATIDE WL 5MG/0.5ML SOLN INJ PEN
                          34396659A    ACTIVE        8        05/27/2026 05/30/2026 (0)
          SIG: INJECT 5MG (0.5ML) SUBCUTANEOUSLY EVERY WEEK FOR WEIGHT LOSS
            Indication: FOR WEIGHT LOSS
            Provider: DOE,JANE MARIE     Cost/Fill: $582.24

        GABAPENTIN 100MG CAP
                          43406880A    ACTIVE        540      11/06/2025 ...

    Each med starts at column 0 with the drug name; subsequent indented
    lines carry the Rx# / SIG / Indication / Provider. Blocks are
    separated by a blank line.

    The CPRS extract_medications() parses VA-formatted blocks shaped:
        ===============================================================================
        Drug Name
         <NAME>
        Issue Date
         <MM/DD/YYYY>
        SIG
         <SIG TEXT>
        Facility: <FAC>
        ===============================================================================

    We rewrite each RXOP med into that shape.
    """
    if not rxop_body or not rxop_body.strip():
        return ""

    blocks: List[str] = []
    cur_name = ""
    cur_issued = ""
    cur_sig_lines: List[str] = []
    in_sig = False

    def _flush():
        if cur_name:
            block = [
                "=" * 79,
                "Drug Name",
                f" {cur_name}",
                "Issue Date",
                f" {cur_issued}",
                "SIG",
                f" {' '.join(cur_sig_lines).strip()}",
                "Facility: VISTA EXPORT",
            ]
            blocks.append("\n".join(block))

    for raw_line in rxop_body.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            # Blank line ends the current med
            if cur_name:
                _flush()
                cur_name = ""
                cur_issued = ""
                cur_sig_lines = []
                in_sig = False
            continue

        # New drug starts at column 0 with all-caps text (not "Drug...."
        # / "Rx #" header).
        if (not raw_line.startswith(" ")
                and not raw_line.startswith("\t")
                and line.upper() == line
                and not line.startswith("DRUG..")
                and "RX #" not in line.upper()
                and re.match(r"^[A-Z][A-Z0-9 /,.%()'\-]+$", line)):
            # New med — flush prior
            if cur_name:
                _flush()
                cur_issued = ""
                cur_sig_lines = []
                in_sig = False
            cur_name = line.title()
            continue

        # Rx# line: capture issue date from "ACTIVE  QTY  MM/DD/YYYY"
        m_rx = re.search(
            r"\bACTIVE\b.*?\b(\d{1,2}/\d{1,2}/\d{4})\b",
            line,
        )
        if m_rx and not cur_issued and cur_name:
            cur_issued = m_rx.group(1)
            continue

        # SIG line(s)
        m_sig = re.match(r"\s+SIG:\s*(.*)$", raw_line, re.IGNORECASE)
        if m_sig:
            in_sig = True
            cur_sig_lines = [m_sig.group(1).strip()]
            continue

        # SIG continuation: indented non-section line while in_sig
        if in_sig:
            stripped = line.strip()
            # Stop on Indication / Provider / Cost lines
            if re.match(r"(?i)^(indication|provider|cost|status|refills?):",
                        stripped):
                in_sig = False
                continue
            if stripped:
                cur_sig_lines.append(stripped)
            continue

    # Final flush
    if cur_name:
        _flush()

    if not blocks:
        return ("Active Outpatient Medications (including Supplies):\n"
                + rxop_body.strip() + "\n")

    return (
        "Active Outpatient Medications (including Supplies):\n"
        + "\n".join(blocks)
        + "\n"
        + "=" * 79
        + "\n"
    )


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

        # Apply urologic filter on the TITLE. Both checks are required:
        #   1. _is_urologic_imaging_study() — modality + anatomy or
        #      inherently-urologic modality (bone scan / PSMA PET).
        #   2. An explicit drop list for studies whose title still
        #      matches an anatomy keyword but is really non-urologic
        #      (chest CTA, maxillofacial CT, etc.).
        if not _is_urologic_imaging_study(title):
            continue
        # Explicit non-urologic anatomy drop list. A small number of
        # study titles can sneak past (1) when they contain BOTH a
        # non-GU anatomy word and a GU-ish word — e.g. "CTA ABDOMINAL
        # AORTA" satisfies the abdominal anatomy gate but the study is
        # really vascular, not urologic. Drop when title contains a
        # non-urologic anatomy word UNLESS it also contains a urologic-
        # primary keyword (urogram / renal / kidney / bladder / prostate
        # / adrenal / scrotum / testis / etc.).
        if re.search(
            r"\b(?:knee|shoulder|spine|cervical|thoracic\s+spine|lumbar\s+spine|"
            r"foot|ankle|hand|wrist|chest|cardiac|brain|head|sinus|"
            r"maxillofacial|mandib|sialo|parotid|salivary|dental|"
            r"IACS|internal\s+auditory|"
            r"aortic|aorta|iliac|vascular|EVAR|carotid|peripheral)\b",
            title, re.IGNORECASE,
        ):
            if not re.search(
                r"\b(?:urogram|renal|kidney|prostate|adrenal|scrotum|"
                r"scrotal|testic|epididym|penis|penile|ureter|bladder|"
                r"cystogram|KUB|retroperitoneal)\b",
                title, re.IGNORECASE,
            ):
                continue

        # Parse the impression text from the indented body. VistA II
        # report bodies are indented continuation lines under the
        # study header; sometimes the impression is labeled with an
        # explicit "Impression:" line, sometimes it's just free-text.
        impression_lines: List[str] = []
        # Outside-study marker. When a study was performed at an
        # outside facility and VA radiology has not read it, VistA
        # emits a "Report:" block followed by "Electronically generated
        # report for outside study." The impression therefore reflects
        # the outside facility's read (or is absent). Per provider
        # direction (2026-06-21), the rendered IMAGING section must
        # explicitly flag these so the clinician knows the study has
        # not been re-read by VA.
        outside_study_marker_re = re.compile(
            r"electronically\s+generated\s+report\s+for\s+outside\s+study",
            re.IGNORECASE,
        )
        is_outside_study = bool(outside_study_marker_re.search(rest))
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
            # Drop the outside-study sentinel line — its presence is
            # captured in is_outside_study and surfaced as a prefix
            # below; leaving the raw VistA boilerplate in the impression
            # adds clutter without clinical value.
            if outside_study_marker_re.search(ln):
                continue
            if re.match(r"^report\s*:\s*$", ln, re.IGNORECASE):
                continue
            # Drop telephone / fax footer lines that some sites paste
            # below the impression — "877-780-5559", "phone:", etc.
            if re.match(r"^[\s\-]*(?:\(?\d{3}\)?[\s\-]?){2}\d{4}[\s\-]*$", ln):
                continue
            if re.match(r"^(?:phone|fax|tel)\s*[:\-]", ln, re.IGNORECASE):
                continue
            # If we see an explicit "Impression:" / "IMPRESSION:" header
            # WITH text on the same line OR following lines, prefer that
            # specifically — it's the radiologist's bottom-line summary
            # and is more useful than concatenated body text.
            m_imp = re.match(r"^impression\s*:?\s*(.*)$", ln, re.IGNORECASE)
            if m_imp:
                tail_text = m_imp.group(1).strip()
                if tail_text:
                    impression_lines = [tail_text]
                else:
                    impression_lines = []
                continue
            impression_lines.append(ln)
        impression = " ".join(impression_lines).strip()
        if not impression and not is_outside_study:
            # No usable body content for this study AND not flagged as
            # an outside study. Per provider direction, do NOT emit a
            # "(no impression text)" placeholder — the LLM has been
            # observed to treat that string as a real finding ("imaging
            # was inconclusive"). Drop the study entirely.
            continue
        # Prefix outside-study impressions with the provider-mandated
        # disclaimer so the clinician (and downstream LLM) cannot
        # mistake the outside read for a VA-validated interpretation.
        # When there is no impression text at all, the disclaimer
        # stands alone as the impression — better to surface the
        # existence of an unread outside study than to drop the row.
        if is_outside_study:
            disclaimer = ("This study originated from outside the VA and "
                          "has not been read by VA radiology.")
            impression = (
                f"{disclaimer} {impression}".strip()
                if impression else disclaimer
            )

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


# Per provider direction (2026-06-20): pathology section should ONLY
# include specimens from urologic organs. Other specimens (colon polyp,
# skin biopsy, lung biopsy, etc.) are filtered out.
_UROLOGIC_PATHOLOGY_ORGAN_RE = re.compile(
    r"\b("
    r"adrenal(?:\s+gland)?|"
    r"kidney|renal|nephr(?:ectomy|olithotomy)?|"
    r"ureter(?:al)?|"
    r"bladder|urothelial|urothelium|"
    r"urethra(?:l)?|"
    r"prostate|prostatic|prost(?:\s+bx|\s+core|\s+biopsy)?|"
    r"penis|penile|"
    r"foreskin|preputial|"
    r"test(?:is|es|icular)|"
    r"vas(?:\s+deferens)?|"
    r"spermatic\s+cord|"
    r"epididym(?:is|al)|"
    r"scrotum|scrotal|"
    r"seminal\s+vesicle"
    r")\b",
    re.IGNORECASE,
)


def _is_urologic_pathology_block(block_text: str) -> bool:
    """True if a pathology block describes a specimen from a urologic
    organ.

    A SP block has the urologic anatomy either at the very top (in the
    Specimen: manifest, before that's stripped) or further down in the
    DIAGNOSIS list as "A. PROSTATE, RIGHT MED APEX, BIOPSY:". We scan
    the FIRST 1500 chars so a stripped manifest doesn't hide the
    diagnosis labels, and also explicitly look at the DIAGNOSIS block
    if present.

    A passing narrative mention of "kidney" (e.g. inside "Brief Clinical
    Hx: ... history of kidney stones") would still pass — but pathology
    blocks are organ-specific by construction, so this is unlikely to
    cause real false positives in practice.
    """
    if not block_text:
        return False
    head = block_text[:1500]
    if _UROLOGIC_PATHOLOGY_ORGAN_RE.search(head):
        return True
    # Fallback: look in the DIAGNOSIS block (the structured part) for
    # urologic anatomy labels even when the head is truncated.
    diag_match = re.search(
        r"(?:\*\*\s*MICROSCOPIC\s+EXAM/DIAGNOSIS|DIAGNOSIS:)\s*\n(.{0,1200})",
        block_text, re.IGNORECASE | re.DOTALL,
    )
    if diag_match and _UROLOGIC_PATHOLOGY_ORGAN_RE.search(diag_match.group(1)):
        return True
    return False


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

    # Strip the long pre-diagnosis "Specimen: A. R MED. APEX PROSTATE BX
    # CORES / B. R MED. MID..." manifest. The same labels reappear under
    # the DIAGNOSIS block where the cores actually have findings. Leaving
    # the manifest in place lets the downstream pathology extractor
    # accidentally pair the bare "Specimen: A. R MED. ..." line with
    # whatever narrative appears after the SP body, producing phantom
    # "A. R MED. APEX PROSTATE BX CORES: , new medications ordered..."
    # entries scraped from unrelated ED-discharge text.
    body = re.sub(
        r"^\s*Specimen:\s*A\.\s+.*?(?=^\s*(?:Brief\s+Clinical|Gross\s+Description|"
        r"Microscopic\s+Exam|\*\*\s*MICROSCOPIC|Date\s+obtained|----|$))",
        "",
        body,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
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

    # Urologic-organ filter (provider direction). Split the SP body on
    # per-report boundaries (allow leading whitespace because the
    # Collected: rewrite preserves the original indentation) and keep
    # only blocks describing one of the allowed urologic organs.
    blocks = re.split(
        r"(?=^\s*---- SURGICAL PATHOLOGY ----)",
        body, flags=re.MULTILINE,
    )
    kept_blocks: List[str] = []
    leading = ""
    for blk in blocks:
        if not blk.strip():
            continue
        if not re.match(r"^\s*----\s*SURGICAL\s+PATHOLOGY\s*----", blk, re.IGNORECASE):
            leading = blk
            continue
        if _is_urologic_pathology_block(blk):
            # Strip leading whitespace from the divider line so the
            # downstream pathology extractor's section regex matches.
            kept_blocks.append(re.sub(r"^\s+", "", blk.lstrip("\n")).rstrip())

    if not kept_blocks:
        return ""

    parts: List[str] = []
    if leading.strip() and _is_urologic_pathology_block(leading):
        parts.append("---- SURGICAL PATHOLOGY ----\n" + leading.strip())
    parts.extend(kept_blocks)
    return "\n\n".join(parts) + "\n"


_VISTA_LAB_ROW_RE = re.compile(
    # CRITICAL: every inter-field separator uses [ \t]+ rather than \s+
    # so a missing trailing field (e.g. "STRUVITE (442)  0.04" with no
    # units/ref) does NOT let the regex engine slide past the newline
    # into the next row's text. Previously this caused alternating rows
    # to be dropped (e.g. SR-CREA, TOTAL U.VOLUME) when the preceding
    # row had empty units/ref.
    r"^(\d{1,2})/(\d{1,2})/(\d{4})[ \t]+(\d{1,2}:\d{2})[ \t]+"
    r"(\S+)[ \t]+"             # specimen (SERUM / URINE / FECES / BLOOD)
    r"(.+?)[ \t]{2,}"          # test name (ends at >=2-space gap)
    r"([<>]?\d+\.?\d*)"        # numeric result
    r"[ \t]*([HL]?)[ \t]*"     # H / L flag
    r"([A-Za-z%/0-9.]*)"       # units
    r"[ \t]*([^\n]*)$",        # ref range — explicit non-newline
    re.MULTILINE,
)

# VistA "ditto" continuation rows under a date+specimen header — the
# date/specimen literally repeat as quotation marks: '   "        "   '
_VISTA_LAB_DITTO_RE = re.compile(
    r'^\s*"\s+"\s+"?\s*'
    r"(.+?)\s{2,}"
    r"([<>]?\d+\.?\d*)\s*([HL]?)\s*"
    r"([A-Za-z%/0-9.]*)\s*(.*)$",
    re.MULTILINE,
)


def _normalize_vista_lab_dittos(body: str) -> str:
    """VistA labs use ditto-mark continuation rows under a single
    date+specimen header:
        05/02/2026 23:34  BLOOD      POC SODIUM       139    mmol/L  138 - 146
           "        "       "        POC POTASSIUM    3.3 L  mmol/L  3.5 - 4.9
           "        "       "        POC CHLORIDE     106    mmol/L  98 - 109

    Replace the dittos with the inherited date / specimen so each row
    is independently parseable. Performs a single forward pass.
    """
    if not body:
        return body
    out_lines: List[str] = []
    cur_date = ""
    cur_spec = ""
    for line in body.split("\n"):
        m = re.match(
            r"^(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2})\s+(\S+)\s+(.*)$",
            line,
        )
        if m:
            cur_date = m.group(1)
            cur_spec = m.group(2)
            out_lines.append(line)
            continue
        # Ditto-row: replace with the inherited prefix
        m2 = re.match(
            r'^\s*"\s+"\s+"?\s*(.*)$',
            line,
        )
        if m2 and cur_date and cur_spec:
            out_lines.append(f"{cur_date}  {cur_spec}      {m2.group(1)}")
            continue
        out_lines.append(line)
    return "\n".join(out_lines)


# Test-name classifier. Each entry is (regex, bucket).
# Buckets:
#   "psa"       -> PSA CURVE block (already handled)
#   "endocrine" -> ENDOCRINE LABS section
#   "stone"     -> STONE LABS section
#   "skip"      -> drop (e.g. stool pathogens, irrelevant POC tests)
#   "general"   -> regular LABS section
_LAB_BUCKET_RULES: Tuple[Tuple[re.Pattern, str], ...] = (
    # PSA family — pulled into PSA CURVE
    (re.compile(r"\bPSA\s+TOTAL\b", re.IGNORECASE), "psa"),
    (re.compile(r"\bPSA-?F\b|FREE\s+PSA|\bPSA\s*%|%\s*FREE\s+PSA", re.IGNORECASE), "psa_free"),

    # Endocrine
    (re.compile(r"TESTOSTERONE.*FREE|FREE\s+TESTOSTERONE", re.IGNORECASE), "endocrine"),
    (re.compile(r"%\s*FREE\s+TESTOSTERONE", re.IGNORECASE), "endocrine"),
    (re.compile(r"TESTOSTERONE", re.IGNORECASE), "endocrine"),
    (re.compile(r"ESTROGEN|ESTRADIOL|TOTAL\s+ESTROGENS?", re.IGNORECASE), "endocrine"),
    (re.compile(r"\bLH\b|LUTEINIZING\s+HORMONE", re.IGNORECASE), "endocrine"),
    (re.compile(r"\bFSH\b|FOLLICLE\s+STIM", re.IGNORECASE), "endocrine"),
    (re.compile(r"\bHCG\b|HUMAN\s+CHORIONIC", re.IGNORECASE), "endocrine"),
    (re.compile(r"\bAFP\b|ALPHA[- ]?FETOPROTEIN", re.IGNORECASE), "endocrine"),
    (re.compile(r"\bLDH\b|LACTATE\s+DEHYDROGENASE", re.IGNORECASE), "endocrine"),
    (re.compile(r"\bHB?A1C\b|HEMOGLOBIN\s+A1C|GLYCATED\s+HEMOGLOBIN", re.IGNORECASE), "endocrine"),
    (re.compile(r"\bTSH\b|THYROID\s+STIM", re.IGNORECASE), "endocrine"),
    (re.compile(r"\bPRL\b|PROLACTIN", re.IGNORECASE), "endocrine"),
    (re.compile(r"\bSHBG\b|SEX\s+HORMONE\s+BIND", re.IGNORECASE), "endocrine"),

    # Stone-panel (24-hour urine + stone composition). VistA SLT/CH
    # rows for the urorisk panel use a urine specimen and one of these
    # test-name shapes:
    #   - Supersaturations:  CALCIUM OXALATE, BRUSHITE, SODIUM URATE,
    #                        STRUVITE, URIC ACID (no "URINE" suffix —
    #                        but specimen = URINE, distinguishing from
    #                        SERUM uric acid)
    #   - Metabolic urine excretions:  <ANALYTE> URINE  or  URINE <ANALYTE>
    #   - VistA-specific abbreviations: SR-CREA (24-hr creatinine),
    #                                   PO4-SR (24-hr phosphorus),
    #                                   TOTAL U.VOLUME (24-hr volume)
    (re.compile(r"\bSTONERISK\b|STONE\s+(?:RISK|COMPOSITION|ANALYSIS)|CALCULUS\s+ANALYSIS",
                re.IGNORECASE), "stone"),
    (re.compile(r"CALCIUM\s+OXALATE|CALCIUM\s+PHOSPHATE|BRUSHITE|"
                r"STRUVITE|URIC\s+ACID\s+(?:CRYST|SS)|URIC\s+ACID,\s*URINE|"
                r"SODIUM\s+URATE|TOTAL\s+URINE\s+VOLUME|TOTAL\s+U\.?\s*VOLUME",
                re.IGNORECASE), "stone"),
    (re.compile(r"\b(?:OXALATE|CITRATE|MAGNESIUM|SODIUM|POTASSIUM|"
                r"PHOSPHORUS|PHOSPHATE|SULFATE|AMMONIUM|CREATININE|"
                r"CALCIUM|URIC\s+ACID),?\s+URINE\b",
                re.IGNORECASE), "stone"),
    (re.compile(r"\bURINE\s+(?:OXALATE|CITRATE|MAGNESIUM|SODIUM|POTASSIUM|"
                r"PHOSPHORUS|PHOSPHATE|SULFATE|AMMONIUM|CALCIUM|CREATININE|"
                r"URIC\s+ACID)\b",
                re.IGNORECASE), "stone"),
    (re.compile(r"\bURINE\s+PH\b|\bpH\s+URINE\b", re.IGNORECASE), "stone"),
    (re.compile(r"\bCYSTINE\b", re.IGNORECASE), "stone"),
    # VistA-specific 24-hr abbreviations
    (re.compile(r"\bSR-CREA\b|\bPO4-SR\b", re.IGNORECASE), "stone"),

    # Stool pathogen panel — drop, not clinically relevant in urology note
    (re.compile(r"CAMPYLO|VIBRIO|SHIGELLA|SALMONELLA|YERSINIA|"
                r"ROTAVIRUS|NOROVIRUS|ASTROVIRUS|SAPOVIRUS|ADENOV|"
                r"CRYPTOSPORIDIUM|CYCLOSPORA|G LAMBLIA|E HISTOLYTICA|"
                r"PLESIOMONAS|SHIGA-TOX|ENTERO E COLI|ENTEROPATH E COLI|"
                r"ENTERTOX E COLI|A/B TOXIN", re.IGNORECASE), "skip"),
)


def _classify_lab_test(test_name: str, specimen: str = "") -> str:
    """Return the bucket for a VistA lab test name.

    When the specimen is URINE and the test is one of the bare-name
    stone-panel components ("URIC ACID", "CITRATE", "OXALATE", etc.
    without a URINE suffix that the keyword rules require), promote to
    the stone bucket. This catches VistA's 24-hr urorisk panel rows
    where the test name was truncated to a single word.
    """
    for pat, bucket in _LAB_BUCKET_RULES:
        if pat.search(test_name):
            return bucket
    # Specimen-aware fallback: urine + bare stone-component name -> stone
    if specimen.upper() == "URINE":
        if re.search(
            r"\b(?:URIC\s+ACID|CITRATE|OXALATE|MAGNESIUM|CALCIUM|"
            r"SULFATE|AMMONIUM|PHOSPHORUS|PHOSPHATE|POTASSIUM|SODIUM)\b",
            test_name, re.IGNORECASE,
        ):
            return "stone"
    return "general"


def _clean_truncated_test_name(name: str) -> str:
    """VistA's fixed-column SLT/CH layout truncates long test names at
    the column edge, often mid-site-code:

        CALCIUM OXALATE(4         -> CALCIUM OXALATE
        MAGNESIUM URINE(4         -> MAGNESIUM URINE
        SODIUM URINE (442         -> SODIUM URINE
        TOTAL U.VOLUME(55         -> TOTAL U.VOLUME
        AMMONIUM URINE (4         -> AMMONIUM URINE

    Strip both complete "(NNN)" / "(NNN" suffixes and open-paren-only
    truncated suffixes so the downstream stone-extractor label lookup
    can match.
    """
    if not name:
        return name
    # Strip a trailing "(<digits>" with or without a closing ")"
    cleaned = re.sub(r"\s*\(\d+\)?\s*$", "", name)
    # Strip a trailing bare "(" left over after truncation
    cleaned = re.sub(r"\s*\(\s*$", "", cleaned)
    # Squeeze whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _parse_lab_rows(body: str) -> List[Tuple[str, str, str, str, str, str, str, str]]:
    """Parse VistA lab rows into (date_disp, hhmm, specimen, test_name,
    value, flag, units, ref) tuples. Dittos are expanded first."""
    body = _normalize_vista_lab_dittos(body or "")
    out: List[Tuple[str, str, str, str, str, str, str, str]] = []
    for m in _VISTA_LAB_ROW_RE.finditer(body):
        mm, dd, yyyy, hhmm = m.group(1), m.group(2), m.group(3), m.group(4)
        specimen = m.group(5).strip().upper()
        # Test name often carries a truncated VistA site-code suffix
        # ("CALCIUM OXALATE(4", "MAGNESIUM URINE (442"). Strip it so
        # downstream classifiers and the stone-panel label lookup match.
        test_name = _clean_truncated_test_name(m.group(6).strip().upper())
        value = m.group(7)
        flag = m.group(8) or ""
        units = m.group(9) or ""
        ref = (m.group(10) or "").strip()
        try:
            from datetime import date as _date
            d = _date(int(yyyy), int(mm), int(dd))
            date_disp = d.strftime("%b %d, %Y")
        except Exception:
            date_disp = f"{mm}/{dd}/{yyyy}"
        out.append((date_disp, hhmm.replace(":", ""), specimen, test_name,
                    value, flag, units, ref))
    return out


def _format_cprs_lab_line(test_name: str, value: str, flag: str, units: str,
                          ref: str, date_disp: str) -> str:
    """Render a single CPRS-canonical lab line.

    Shape: "NAME  VALUE [H/L]  UNITS  REF  (MMM DD, YYYY)"
    Downstream lab + endocrine extractors already parse this shape.
    """
    parts: List[str] = [test_name, value]
    if flag:
        parts.append(flag)
    if units:
        parts.append(units)
    if ref:
        parts.append(ref)
    parts.append(f"({date_disp})")
    return "  ".join(parts)


def _render_labs_from_ch_slt_mic(ch_body: str, slt_body: str, mic_body: str) -> str:
    """Bucket VistA lab rows by clinical category and emit each bucket
    under the matching CPRS section header.

    Buckets:
      psa       -> PSA CURVE: ... (rows shaped "[r] MMM DD, YYYY HHMM   VAL")
      endocrine -> "===== ENDOCRINE LABS =====" CPRS block
      stone     -> "===== STONE LABS =====" CPRS block
      general   -> "===== LABS =====" CPRS block
      skip      -> dropped (stool pathogens, irrelevant POC)
      psa_free  -> dropped from PSA CURVE (free PSA / %PSA noise) but
                   surfaced as a general lab line for completeness

    Dittos are expanded first so each row carries its own date/specimen.
    """
    combined = "\n".join(b for b in (slt_body, ch_body) if b and b.strip())
    rows = _parse_lab_rows(combined)
    if not rows and not (mic_body and mic_body.strip()):
        return ""

    # Bucket the rows. Deduplicate per (test_name, date_disp, value).
    psa_rows: List[Tuple[str, str, str]] = []          # (date_disp, hhmm, value)
    endocrine_rows: List[str] = []
    stone_rows: List[str] = []
    general_rows: List[str] = []
    seen_psa = set()
    seen_other = set()

    for date_disp, hhmm, specimen, test_name, value, flag, units, ref in rows:
        bucket = _classify_lab_test(test_name, specimen)
        if bucket == "skip":
            continue
        if bucket == "psa":
            key = (date_disp, hhmm, value)
            if key in seen_psa:
                continue
            seen_psa.add(key)
            psa_rows.append((date_disp, hhmm, value))
            continue

        line = _format_cprs_lab_line(test_name, value, flag, units, ref, date_disp)
        key = (test_name, date_disp, value)
        if key in seen_other:
            continue
        seen_other.add(key)

        if bucket == "endocrine":
            endocrine_rows.append(line)
        elif bucket == "stone":
            stone_rows.append(line)
        elif bucket == "psa_free":
            # Free-PSA / %PSA values are not part of PSA CURVE but the
            # provider may still want them visible — surface as general.
            general_rows.append(line)
        else:
            general_rows.append(line)

    out_parts: List[str] = []

    # PSA CURVE (newest first)
    if psa_rows:
        from datetime import datetime as _dt
        def _date_key(row):
            try:
                return _dt.strptime(row[0], "%b %d, %Y")
            except Exception:
                return _dt.min
        psa_rows.sort(key=_date_key, reverse=True)
        psa_lines = ["PSA CURVE:"]
        for date_disp, hhmm, value in psa_rows:
            psa_lines.append(f"[r] {date_disp} {hhmm or '0000'}    {value}")
        out_parts.append("\n".join(psa_lines))

    # Endocrine block (matches "===== ENDOCRINE LABS =====" section anchor)
    if endocrine_rows:
        out_parts.append(
            "=" * 31 + "ENDOCRINE LABS " + "=" * 28 + "\n"
            + "\n".join(endocrine_rows)
        )

    # Stone block. The existing CPRS stone extractor's most reliable
    # parser is extract_plain_label_stone_panel(), which keys on a
    # "24-HOUR URINE METABOLIC STONE PANEL (date):" header followed by
    # "LABEL: value" lines. Emit that shape instead of the generic
    # CPRS lab-line shape so the values are actually parsed.
    #
    # Threshold gate: only emit a STONE LABS panel when at least 3
    # distinct stone-panel analytes co-occur on the same date. A
    # single isolated row (e.g. routine 'URINE PH 5.0' from a UA) is
    # not a 24-hr urine panel and should not promote a STONE LABS
    # section that the LLM then references as if a metabolic workup
    # had been done.
    if stone_rows:
        stone_per_date: Dict[str, List[Tuple[str, str]]] = {}
        for date_disp, hhmm, specimen, test_name, value, flag, units, ref in rows:
            if _classify_lab_test(test_name, specimen) != "stone":
                continue
            label = re.sub(r"\s+", " ", test_name.title()).strip()
            value_str = value
            if flag:
                value_str += f" {flag}"
            if units:
                value_str += f" {units}"
            stone_per_date.setdefault(date_disp, []).append((label, value_str))
        # Drop dates that don't meet the cluster threshold
        stone_per_date = {
            d: rows_ for d, rows_ in stone_per_date.items()
            if len(rows_) >= 3
        }

        if stone_per_date:
            # Newest panel first
            from datetime import datetime as _dt
            def _date_key(d):
                try:
                    return _dt.strptime(d, "%b %d, %Y")
                except Exception:
                    return _dt.min
            panel_blocks: List[str] = []
            for date_disp in sorted(stone_per_date.keys(), key=_date_key, reverse=True):
                lines = [f"24-HOUR URINE METABOLIC STONE PANEL ({date_disp}):"]
                for label, val in stone_per_date[date_disp]:
                    lines.append(f"{label}: {val}")
                panel_blocks.append("\n".join(lines))

            out_parts.append(
                "=" * 30 + "STONE RELATED LABS " + "=" * 26 + "\n"
                + "\n\n".join(panel_blocks)
            )

    # General LABS block
    if general_rows:
        out_parts.append(
            "=" * 36 + " LABS " + "=" * 36 + "\n"
            + "\n".join(general_rows)
        )

    # Microbiology pass-through under its own header so the labs
    # extractor's existing UA-culture parsing can find it.
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
