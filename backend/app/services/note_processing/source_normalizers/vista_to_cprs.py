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

_HEADER_RE = re.compile(
    r"^(?P<code>(?:" + "|".join(re.escape(c) for c in _KNOWN_CODES) + r"))"
    r"\s*-\s*"
    r"(?P<desc>[A-Za-z][^\n]*)$",
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


def _render_pmh_from_pll(pll_body: str) -> str:
    """Render the CPRS PAST MEDICAL HISTORY section from VistA PLL body.

    Conservative line-level pass-through: keep each non-empty body line
    as-is under a CPRS section header. The PMH extractor already handles
    a wide variety of bullet / numbered shapes, so preserving the
    original layout is safer than parsing prematurely. When the user
    sends a real PLL sample we can add ICD-code stripping and date
    normalization here.
    """
    if not pll_body or not pll_body.strip():
        return ""
    return "==================== PAST MEDICAL HISTORY ====================\n" + pll_body.strip() + "\n"


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
    PSMA PET/CT). Other studies (CXR, mammography, etc.) are dropped.

    Study boundary heuristic: studies inside II are typically separated
    by a blank line. We split on >=1 blank line, classify each chunk by
    modality, and keep only urologic chunks. Each kept chunk passes
    through unchanged so the downstream imaging extractor can parse
    titles + dates + impressions from it.
    """
    if not ii_body or not ii_body.strip():
        return ""
    # Split on a blank line followed by another non-blank line — these
    # mark study boundaries in II output.
    chunks = re.split(r"\n\s*\n+", ii_body.strip())
    kept: List[str] = []
    for chunk in chunks:
        c = chunk.strip("\n")
        if not c.strip():
            continue
        if _is_urologic_imaging_study(c):
            kept.append(c)
    if not kept:
        return ""
    return (
        "==================== IMAGING ====================\n"
        + "\n\n".join(kept)
        + "\n"
    )


def _render_pathology_from_sp(sp_body: str) -> str:
    """Render the CPRS PATHOLOGY RESULTS section from VistA SP body.

    The existing pathology extractor already handles VistA-style
    'SURGICAL PATHOLOGY REPORT' headers (Strategy 1b added in 4684f27).
    Wrap the SP body in a CPRS-style header so the extractor's section
    locator finds it predictably.
    """
    if not sp_body or not sp_body.strip():
        return ""
    return "---- SURGICAL PATHOLOGY ----\n" + sp_body.strip() + "\n"


def _render_labs_from_ch_slt_mic(ch_body: str, slt_body: str, mic_body: str) -> str:
    """Render the CPRS LABS section from CH (Chem & Hematology),
    SLT (Lab Tests Selected), and MIC (Microbiology) bodies.

    TODO: each of these has its own table layout. For now pass through
    under the CPRS LABS header. Real column parsing follows the lab
    sample.
    """
    parts: List[str] = []
    if ch_body and ch_body.strip():
        parts.append(ch_body.strip())
    if slt_body and slt_body.strip():
        parts.append(slt_body.strip())
    if mic_body and mic_body.strip():
        parts.append("MICROBIOLOGY:\n" + mic_body.strip())
    if not parts:
        return ""
    return (
        "==================== LABS ====================\n"
        + "\n\n".join(parts)
        + "\n"
    )


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
