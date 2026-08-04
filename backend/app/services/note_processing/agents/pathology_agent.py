"""
Pathology Agent

Combines and presents pathology reports preserving clinical detail.
Pathology results are critical for clinical decision-making and must retain
specimen-level detail including locations, grades, and percentages.

Includes HALLUCINATION DETECTION via deterministic fact verification.
All synthesized pathology is checked against ground truth extracted from source.
"""

from typing import List, Dict, Tuple, Optional, Union
import re
import logging
from ..llm_helper import combine_sections_with_llm
from .history_cleaners import clean_llm_commentary
from ..extractors.pathology_fact_verifier import (
    PathologyFactVerifier,
    VerificationResult,
    verify_pathology_against_source
)

logger = logging.getLogger(__name__)


# Critical, high-value pathology findings an LLM composer sometimes drops when
# reformatting the section. Each entry: (label, SOURCE capture pattern, SECTION
# presence pattern). The source pattern captures the finding verbatim from the
# DETERMINISTIC regex extraction; the (looser) presence pattern decides whether
# the rendered section already covers the concept. A finding documented in the
# deterministic extraction but absent from the section is restored — so the
# PATHOLOGY section can never silently lose documented staging / margin /
# invasion detail regardless of LLM behavior. Grade-agnostic (works for prostate
# pT/margin/PNI, renal pT, urothelial invasion, etc.).
_PATH_CRITICAL = [
    ("stage",
     re.compile(r"\bp?T\d[a-d]?(?:\s*,?\s*p?N\d[a-c]?)?(?:\s*,?\s*p?M\d)?", re.I),
     re.compile(r"\bp?T\d", re.I)),
    ("surgical margin",
     re.compile(r"(?:positive|negative|involved|close|uninvolved)\s+(?:surgical\s+)?"
                r"margins?[^.\n;,]{0,45}|margins?\s+(?:are\s+|were\s+)?"
                r"(?:positive|negative|involved|free|uninvolved)[^.\n;,]{0,30}", re.I),
     re.compile(r"margins?\b", re.I)),
    ("perineural invasion",
     re.compile(r"perineural\s+invasion(?:\s+(?:present|identified))?", re.I),
     re.compile(r"perineural|\bPNI\b", re.I)),
    ("lymphovascular invasion",
     re.compile(r"lymphovascular\s+invasion(?:\s+(?:present|identified))?", re.I),
     re.compile(r"lymphovascular|\bLVI\b", re.I)),
]


def ensure_pathology_completeness(section: str, deterministic_pathology: str) -> str:
    """Deterministic backstop: guarantee the rendered PATHOLOGY section retains the
    critical documented findings (stage / margin / perineural + lymphovascular
    invasion) an LLM composer sometimes drops. Compares against the DETERMINISTIC
    regex extraction and appends any dropped finding verbatim. Never removes
    content; a no-op when the section already covers every documented finding."""
    if not section or not deterministic_pathology:
        return section
    missing = []
    for _label, source_pat, present_pat in _PATH_CRITICAL:
        m = source_pat.search(deterministic_pathology)
        if m and not present_pat.search(section):
            missing.append(re.sub(r"\s+", " ", m.group(0)).strip(" ;,."))
    if not missing:
        return section
    seen, uniq = set(), []
    for s in missing:
        if s.lower() not in seen:
            seen.add(s.lower())
            uniq.append(s)
    logger.info(f"[PATHOLOGY] deterministic backstop restored dropped finding(s): {uniq}")
    return (section.rstrip()
            + "\n\nAdditional documented pathology (retained from source): "
            + "; ".join(uniq) + ".")


# Markers that distinguish a real pathology REPORT (with specimen-level
# findings) from a narrative MENTION of cancer ("history of prostate
# cancer per outside biopsy"). Per-note Pathology extractions only
# survive into LLM synthesis when at least one of these markers is
# present — narrative mentions are the primary source of pathology
# hallucinations (LLM promotes "patient has cancer" to an invented
# biopsy result, sometimes for an organ the patient never had biopsied).
_REAL_PATHOLOGY_MARKERS = re.compile(
    r"\bGleason(?:'?s)?\s+(?:score|grade|grade\s+group)\s*\d"
    r"|\bGleason(?:'?s)?\s+\d\s*\+\s*\d"
    r"|\bGrade\s+Group\s+\d\b"
    r"|\bGG\s*[1-5]\b"
    r"|involving\s+(?:approximately\s+)?\d+\s*%"
    r"|involving\s+\d+/\d+\s+cores?"
    r"|perineural\s+invasion"
    r"|(?:negative|positive)\s+for\s+malignancy"
    r"|atypical\s+small\s+acinar\s+proliferation"
    r"|\bASAP\b|\bHGPIN\b"
    r"|adenocarcinoma\b.*?(?:Gleason|Grade\s+Group|\d+\s*%)"
    r"|\b[A-N]\.\s+PROSTATE\b.*?BIOPSY"
    r"|\bTRUS\s*[-/]?\s*BX\b"
    r"|carcinoma\s+in\s+situ\b"
    r"|\bpT[0-4]\b|\bpN[0-3]\b|\bpM[0-1]\b"
    r"|extracapsular\s+extension"
    r"|seminal\s+vesicle\s+invasion"
    r"|margin(?:s)?\s+(?:positive|negative|involved|free)"
    r"|urothelial\s+carcinoma\b.*?(?:grade|stage|invasion)"
    r"|renal\s+cell\s+carcinoma\b.*?(?:Fuhrman|grade|stage)",
    re.IGNORECASE | re.DOTALL,
)


# Organ → markers used to detect whether the source actually has
# pathology for that organ. Used by _strip_cross_organ_pathology to
# delete LLM-synthesized paragraphs that assert pathology for an organ
# the source never biopsied.
_ORGAN_DETECTORS = {
    'prostate': re.compile(
        r'\bprostate\b.*?(?:biopsy|adenocarcinoma|Gleason|Grade\s+Group|prostatectomy)',
        re.IGNORECASE | re.DOTALL,
    ),
    'kidney': re.compile(
        r'\b(?:kidney|renal)\b.*?(?:biopsy|RCC|renal\s+cell|Fuhrman|nephrectomy|carcinoma|mass)',
        re.IGNORECASE | re.DOTALL,
    ),
    'bladder': re.compile(
        r'\bbladder\b.*?(?:biopsy|TURBT|urothelial|Ta\b|T1\b|T2\b|carcinoma|tumor)'
        r'|TURBT\s+(?:specimen|biopsy)',
        re.IGNORECASE | re.DOTALL,
    ),
    'testis': re.compile(
        r'\b(?:testis|testicle|testicular)\b.*?(?:biopsy|orchiectomy|seminoma|non[-\s]?seminoma|germ\s+cell|carcinoma)',
        re.IGNORECASE | re.DOTALL,
    ),
    'penis': re.compile(
        r'\bpen(?:is|ile)\b.*?(?:biopsy|carcinoma|squamous)',
        re.IGNORECASE | re.DOTALL,
    ),
    'ureter': re.compile(
        r'\bureter(?:al)?\b.*?(?:biopsy|urothelial|carcinoma|tumor)',
        re.IGNORECASE | re.DOTALL,
    ),
}

# Per-organ assertion markers: if a synthesis paragraph contains one of
# these AND the organ isn't documented in the source, the paragraph is
# considered a hallucination and is dropped.
_ORGAN_ASSERTION = {
    'prostate': re.compile(
        r'\bprostat(?:e|ic)\b.*?'
        r'(?:adenocarcinoma|Gleason|Grade\s+Group|GG\s*[1-5]|biopsy|carcinoma|cancer)',
        re.IGNORECASE | re.DOTALL,
    ),
    'kidney': re.compile(
        r'\b(?:renal\s+cell\s+(?:carcinoma|cancer)|RCC|kidney\s+(?:cancer|carcinoma|mass))',
        re.IGNORECASE | re.DOTALL,
    ),
    'bladder': re.compile(
        r'\b(?:urothelial\s+carcinoma|bladder\s+(?:cancer|carcinoma|tumor)|TURBT)',
        re.IGNORECASE | re.DOTALL,
    ),
    'testis': re.compile(
        r'\b(?:seminoma|non[-\s]?seminoma|testicular\s+(?:cancer|tumor|germ\s+cell))',
        re.IGNORECASE | re.DOTALL,
    ),
    'penis': re.compile(
        r'\bpenile\s+(?:cancer|carcinoma|squamous)',
        re.IGNORECASE | re.DOTALL,
    ),
    'ureter': re.compile(
        r'\bureteral?\s+(?:carcinoma|cancer|urothelial)',
        re.IGNORECASE | re.DOTALL,
    ),
}


def _strip_cross_organ_pathology(synthesis: str, source_blob: str) -> str:
    """Remove paragraphs that assert pathology for organs absent from source.

    Catches the failure mode where a patient with kidney-only pathology
    ends up with a fabricated prostate-cancer entry in the synthesis,
    or where a prostate-only patient gets an invented bladder tumor.
    Operates paragraph-by-paragraph so legitimate adjacent paragraphs
    survive. Conservative: only drops a paragraph when an organ-specific
    pathology ASSERTION is detected AND the source has no pathology
    documentation for that organ at all.
    """
    if not synthesis or not source_blob:
        return synthesis

    # Determine which organs the source actually documents.
    organs_in_source = {
        organ for organ, det in _ORGAN_DETECTORS.items() if det.search(source_blob)
    }
    if not organs_in_source:
        # No organ-specific pathology detected in source at all —
        # don't strip (downstream verifier handles this case).
        return synthesis

    # Split into paragraphs (blank-line separated). Keep order.
    paragraphs = re.split(r'\n\s*\n', synthesis)
    kept: List[str] = []
    for para in paragraphs:
        drop = False
        for organ, assertion in _ORGAN_ASSERTION.items():
            if organ in organs_in_source:
                continue  # legitimate organ for this patient
            if assertion.search(para):
                logger.warning(
                    "Pathology agent: dropping paragraph asserting %s "
                    "pathology — not documented in source. "
                    "Source organs: %s. Paragraph preview: %r",
                    organ, sorted(organs_in_source), para[:120],
                )
                drop = True
                break
        if not drop:
            kept.append(para)

    return '\n\n'.join(kept).strip()


def _has_real_pathology_findings(text: str) -> bool:
    """True if `text` contains at least one specimen-level pathology marker.

    Used to filter per-note Pathology entries before LLM synthesis so
    that narrative mentions ("history of cancer", "abnormal biopsy")
    don't get promoted to canonical pathology results by the LLM. Real
    pathology reports always contain at least one of: Gleason score /
    grade group, % tissue involvement, core counts, PNI, malignancy
    status, lettered specimen markers (A. PROSTATE, ..., BIOPSY:),
    TNM staging, ECE/SVI/margin status, or specific carcinoma + grade
    combinations.
    """
    if not text or not text.strip():
        return False
    return bool(_REAL_PATHOLOGY_MARKERS.search(text))


def _clean_va_metadata(pathology_text: str) -> str:
    """
    Remove ONLY VA administrative metadata from pathology text.
    Preserves all clinical content including specimen details, grades,
    percentages, staining results, and consensus conference summaries.

    Args:
        pathology_text: Raw pathology text

    Returns:
        Pathology text with VA metadata removed but clinical content intact
    """
    if not pathology_text:
        return ""

    # Remove |_| markers
    cleaned = re.sub(r'\|_\|([^|]+)\|_\|:?', r'\1:', pathology_text)

    # Remove VA facility/administrative metadata lines
    va_metadata_patterns = [
        r'^Facility:.*$',
        r'^Printed at:.*$',
        r'^AUDIE L\. MURPHY.*$',
        r'^7400 MERTON MINTER.*$',
        r'^\[CLIA#.*?\]$',
        r'^SAN ANTONIO.*$',
        r'^As of:.*$',
        r'^typed by.*$',
        r'^\(Added/Last modified:.*?\)$',
        r'^\*\+\* SUPPLEMENTARY.*\*\+\*$',
        r'^\(Date Spec taken:.*?\)$',
        r'^Date Spec taken:.*$',
        r'^Reporting Lab:.*$',
        r'^PATHOLOGY REPORT\s+Accession.*$',
        r'^Accession No\..*$',
        r'^Specimen ID:.*$',
        r'^Performing Laboratory.*$',
        r'^/es/.*$',
        r'^Signed.*$',
        r'^\s*-{10,}\s*$',
        r'^\s*={10,}\s*$',
    ]

    lines = cleaned.split('\n')
    filtered_lines = []
    for line in lines:
        is_metadata = False
        for pattern in va_metadata_patterns:
            if re.match(pattern, line.strip(), re.IGNORECASE):
                is_metadata = True
                break
        if not is_metadata and line.strip():
            filtered_lines.append(line)

    cleaned = '\n'.join(filtered_lines)

    # Remove ** markdown formatting
    cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', cleaned)

    # Normalize excessive whitespace while preserving structure
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip()


def synthesize_pathology(
    document_pathology: str,
    gu_notes: List[Dict[str, str]],
    verify_facts: bool = True,
    return_verification: bool = False
) -> Union[str, Tuple[str, Optional[VerificationResult]]]:
    """
    Synthesize pathology results from document-level extraction and notes.

    Preserves detailed specimen-level information. Pathology results are
    clinically critical and must NOT be oversimplified.

    INCLUDES HALLUCINATION DETECTION:
    - Extracts ground truth facts from source documents BEFORE LLM synthesis
    - Verifies all claims in LLM output against ground truth
    - Flags or corrects any hallucinated content

    Args:
        document_pathology: Pathology from SURGICAL PATHOLOGY sections
        gu_notes: List of GU note dictionaries
        verify_facts: If True (default), verify synthesis against source facts
        return_verification: If True, return (text, VerificationResult) tuple

    Returns:
        Complete pathology results with specimen-level detail.
        If return_verification=True, returns (text, VerificationResult) tuple.
    """
    # Collect all pathology entries. Per-note Pathology fields often
    # contain narrative mentions (e.g. "history of prostate cancer per
    # 2017 biopsy") rather than actual specimen-level findings. When
    # those bare narrative mentions reach the LLM combination step,
    # they get hallucinated into canonical pathology claims like
    # "patient has biopsy-confirmed prostate cancer" — sometimes adding
    # cancer types the patient never had (e.g. a kidney-cancer patient
    # getting a fabricated "high-grade prostate cancer" entry). To
    # prevent this, every entry that enters all_pathology must contain
    # at least one specimen-level finding marker. document_pathology is
    # always included verbatim because it comes from the deterministic
    # pathology extractor which already requires biopsy markers.
    all_pathology = []

    # Document-level pathology (from SURGICAL PATHOLOGY sections).
    # Trusted source — extracted by deterministic regex that requires
    # actual biopsy headers, so it cannot contain a narrative-only
    # mention. Include verbatim.
    if document_pathology and document_pathology.strip():
        all_pathology.append(document_pathology)

    # Note-level pathology mentions — STRICTLY filtered: must contain
    # real specimen-level finding markers. Narrative mentions ("history
    # of cancer", "biopsy positive per outside facility") are dropped
    # because they don't carry verifiable specimen detail and they're
    # what the LLM was hallucinating from.
    for note in gu_notes:
        path_text = note.get("Pathology") or ""
        if _has_real_pathology_findings(path_text):
            all_pathology.append(path_text)
        elif path_text.strip():
            logger.debug(
                "Pathology agent: dropped per-note pathology entry "
                "lacking specimen-level markers (would be a "
                "hallucination vector). Length=%d", len(path_text),
            )

    if not all_pathology:
        if return_verification:
            return "", None
        return ""

    # STEP 1: Extract ground truth facts BEFORE any LLM synthesis
    verifier = PathologyFactVerifier()
    if verify_facts:
        for pathology_text in all_pathology:
            verifier.extract_facts_from_source(pathology_text)

        fact_summary = verifier.get_fact_summary()
        if fact_summary['total_facts'] > 0:
            logger.debug(
                f"Extracted {fact_summary['total_facts']} ground truth facts: "
                f"Gleason={fact_summary['gleason_scores']}, "
                f"GG={fact_summary['grade_groups']}, "
                f"Cores={fact_summary['core_counts']}"
            )

    # If only one instance, clean VA metadata only (preserve clinical detail)
    if len(all_pathology) == 1:
        result_text = _clean_va_metadata(all_pathology[0])
        if return_verification:
            # Single source = no LLM synthesis = no hallucination risk
            return result_text, None
        return result_text

    # STEP 2: Multiple pathology entries - combine with LLM but PRESERVE detail
    instructions = """Combine these pathology results into a single comprehensive report.

ABSOLUTE ANTI-HALLUCINATION RULES (HIGHEST PRIORITY):
A. The output MUST contain ONLY specimen results that appear verbatim
   (or near-verbatim) in the source entries above. If a specimen,
   organ, or finding is NOT in the source, it MUST NOT appear in
   the output. Never extrapolate from a diagnosis to a biopsy result.
B. Never invent a pathology result for an organ that does not have
   a documented biopsy in the source. Example: if the source contains
   ONLY renal-cell-carcinoma pathology, the output MUST NOT contain
   any prostate pathology. If the source has ONLY a prostate biopsy,
   the output MUST NOT mention kidney/bladder/testicular pathology.
C. Do NOT add new Gleason scores, Grade Groups, percentages, T-stages,
   margin statuses, or any other graded findings beyond what the source
   explicitly lists. If a number isn't in the source, it MUST NOT be
   in the output.
D. A patient's PMH or HPI mentioning "history of cancer" is NOT a
   pathology result. Only treat text as a pathology result when the
   source explicitly contains specimen markers (lettered specimens
   like "A. PROSTATE, RIGHT MEDIAL APEX, BIOPSY:", Gleason score,
   Grade Group, % tissue involvement, or comparable lab-report
   formatting).

CRITICAL RULES:
1. PRESERVE ALL specimen-level detail - do NOT summarize or truncate
2. Each specimen must retain: anatomical location, finding, grade (if applicable), percentage involvement
3. Include ALL Gleason scores, Grade Groups, and staging information EXACTLY as they appear in source
4. Include ALL immunohistochemistry/staining results
5. Include consensus conference notes if present
6. Preserve negative findings (e.g., "Negative for malignancy")
7. Organize by procedure date (most recent first)
8. Remove duplicate entries but keep ALL unique specimen results
9. DO NOT invent, interpolate, or estimate ANY values - use ONLY what is in the source documents

FORMAT:
- Group by procedure type and date
- List each specimen on its own line with full detail
- Include the date of each pathology procedure

REMOVE ONLY:
- VA facility names and addresses
- CLIA numbers
- Report modification dates
- "typed by" information
- Duplicate entries of the same specimen

DO NOT remove or shorten:
- Individual core/specimen results
- Gleason scores or Grade Groups
- Percentage of tissue involvement
- Immunohistochemistry results
- Margin status
- Consensus conference summaries

CRITICAL: Return ONLY the combined pathology. NO meta-commentary.
CRITICAL: Every Gleason score, Grade Group, core count, and percentage MUST come directly from the source.
CRITICAL: If after applying these rules nothing is left to combine (e.g. only one source had real specimen data), return that one source's content verbatim with VA metadata removed — do NOT pad."""

    synthesized = combine_sections_with_llm(
        section_name="Pathology Results",
        section_instances=all_pathology,
        instructions=instructions
    )

    if synthesized:
        # Clean VA metadata from LLM output
        synthesized = _clean_va_metadata(synthesized)
        # Clean any LLM meta-commentary
        synthesized = clean_llm_commentary(synthesized)
        # Deterministic anti-cross-contamination guard. Determine which
        # organs have ACTUAL pathology in the source, then drop any
        # paragraph in the synthesis that asserts pathology for an organ
        # that wasn't in the source. This catches the "kidney-cancer
        # patient gets a prostate-biopsy entry" failure mode regardless
        # of whether the fact verifier flagged it.
        source_blob = '\n'.join(all_pathology)
        synthesized = _strip_cross_organ_pathology(synthesized, source_blob)

    # STEP 3: Verify synthesis against ground truth facts
    verification_result = None
    if verify_facts and synthesized and verifier.ground_truth_facts:
        verification_result = verifier.verify_synthesis(synthesized)

        if not verification_result.is_verified:
            logger.warning(
                f"Pathology synthesis verification FAILED. "
                f"Confidence: {verification_result.confidence_score:.2f}. "
                f"Potential hallucinations: {verification_result.potential_hallucinations}"
            )

            # Use corrected text if available
            if verification_result.corrected_text:
                logger.info("Using corrected pathology text with hallucinations flagged")
                synthesized = verification_result.corrected_text
        else:
            logger.debug(
                f"Pathology synthesis VERIFIED. "
                f"Confidence: {verification_result.confidence_score:.2f}. "
                f"Verified claims: {verification_result.verified_claims}"
            )

    if return_verification:
        return synthesized, verification_result
    return synthesized


def synthesize_pathology_with_verification(
    document_pathology: str,
    gu_notes: List[Dict[str, str]]
) -> Tuple[str, Optional[VerificationResult]]:
    """
    Synthesize pathology with full verification result.

    Convenience wrapper that always returns verification details.

    Args:
        document_pathology: Pathology from SURGICAL PATHOLOGY sections
        gu_notes: List of GU note dictionaries

    Returns:
        Tuple of (synthesized_text, VerificationResult or None)
    """
    return synthesize_pathology(
        document_pathology,
        gu_notes,
        verify_facts=True,
        return_verification=True
    )
