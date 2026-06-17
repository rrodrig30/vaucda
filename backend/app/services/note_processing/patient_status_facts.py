"""
Patient Status Facts Extractor & Context Sanitizer.

Pre-LLM defense layer for the Stage 2 Assessment & Plan agents.

This module exists because the LLM-generated A&P agents have been observed
to confabulate a coherent post-treatment-surveillance narrative (e.g.
"completed definitive focal therapy for prostate cancer", "biochemical
recurrence", "Phoenix criteria", "salvage therapy") for patients who are
in fact treatment-naive with negative biopsies. The trigger is usually
keyword contamination — a dermatology mention of "cryotherapy of actinic
keratoses" plus rising PSA plus ASAP on biopsy is enough for the model
to reach for its "rising-PSA-after-treatment" template.

Strategy
--------
1. Parse the Stage 1 note (the deterministic, extractor-built source of
   truth) and produce a structured PatientStatusFacts verdict: is there
   cancer? are there confirmed treatments? is Phoenix applicable?
2. Sanitize the downstream context artifacts (prior assessments / prior
   plans / visit-progression analysis / prior A&P context) by stripping
   sentences that ASSERT facts contradicting the verdict, breaking the
   prior-LLM-hallucination feedback loop. Stripped sentences are logged.
3. Render the verdict as a "PATIENT GROUND TRUTH" prompt block that
   gets prepended to both Assessment and Plan LLM contexts with
   ABSOLUTE-RULES framing so the LLM treats it as authoritative.

Detection is intentionally conservative: negation guards prevent
"no family history of prostate cancer" from being read as a positive
finding; ambiguous treatment words (cryotherapy, ablation) require an
explicit "prostate" qualifier; treatment claims require a completion
verb (s/p, underwent, completed, ...) before the treatment noun.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cancer-positive evidence patterns. Each must survive the negation guard.
# ---------------------------------------------------------------------------
_CANCER_POSITIVE_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"\bGleason\s*\d+\s*[\+/]\s*\d+", re.IGNORECASE),
    re.compile(r"\bGrade\s+Group\s+[1-5]\b", re.IGNORECASE),
    re.compile(r"\bGG[1-5]\b"),
    re.compile(r"\bprostate\s+adenocarcinoma\b", re.IGNORECASE),
    re.compile(r"\bprostate\s+cancer\b", re.IGNORECASE),
    re.compile(r"\bcarcinoma\s+of\s+(?:the\s+)?prostate\b", re.IGNORECASE),
    re.compile(r"\bCaP\b"),
    re.compile(r"\bCa\s+prostate\b", re.IGNORECASE),
)

_NEGATION_TOKEN_RE = re.compile(
    r"\b(?:"
    r"no(?:t)?|negative\s+for|without|denies|denied|"
    r"ruled?\s+out|r/o|absent|free\s+of|"
    r"no\s+family\s+history\s+of|no\s+evidence\s+of|"
    r"no\s+history\s+of"
    r")\b",
    re.IGNORECASE,
)


def _preceded_by_negation(text: str, match_start: int, window: int = 80) -> bool:
    """True if the span starting at ``match_start`` is preceded by a
    negation token within the prior ``window`` characters. The window
    crosses newlines because phrases like 'No family history of\\nprostate
    cancer' span lines in real VistA dumps."""
    snippet = text[max(0, match_start - window):match_start]
    return bool(_NEGATION_TOKEN_RE.search(snippet))


def find_cancer_evidence(text: str) -> List[str]:
    """Return positive (un-negated) cancer evidence quotes from ``text``.

    Each returned string is the literal match (e.g. 'Gleason 4+3=7',
    'Grade Group 3', 'prostate adenocarcinoma'). The caller treats a
    non-empty list as authoritative evidence the patient has prostate
    cancer.
    """
    found: List[str] = []
    for pattern in _CANCER_POSITIVE_PATTERNS:
        for m in pattern.finditer(text):
            if _preceded_by_negation(text, m.start()):
                continue
            found.append(m.group(0))
    # Dedup case-insensitively while preserving first-seen order
    seen, deduped = set(), []
    for q in found:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            deduped.append(q)
    return deduped


# ---------------------------------------------------------------------------
# Treatment-completed detection
#
# Unambiguous patterns are treatments whose mere presence with a completion
# verb is sufficient. Ambiguous patterns (cryotherapy, ablation) share
# their wording with dermatology / nephrology / GI procedures and require
# both a 'prostate' qualifier nearby AND a completion verb.
# ---------------------------------------------------------------------------
_UNAMBIGUOUS_TREATMENT_TOKENS: Tuple[str, ...] = (
    r"radical\s+prostatectomy",
    r"\bprostatectomy\b",
    r"\bRALP\b",
    r"\bRARP\b",
    r"\bRRP\b",
    r"\bLRP\b",
    r"\bORP\b",
    r"external\s+beam\s+radiation(?:\s+therapy)?",
    r"\bEBRT\b",
    r"\bIMRT\b",
    r"\bSBRT\b",
    r"\bIGRT\b",
    r"\bXRT\b",
    r"radiation\s+therapy\s+to\s+(?:the\s+)?prostate",
    r"\bbrachytherapy\b",
    r"seed\s+implant(?:ation)?",
    r"\bHIFU\b",
    r"\bTULSA(?:-PRO)?\b",
    r"high[\s-]?intensity\s+focused\s+ultrasound",
    r"focal\s+therapy",
    r"focal\s+ablation",
    r"focal\s+cryoablation",
    r"focal\s+cryotherapy",
    r"focal\s+laser\s+ablation",
    r"androgen\s+deprivation\s+therapy",
    r"\bADT\b",
    r"\bleuprolide\b",
    r"\bLupron\b",
    r"\bEligard\b",
    r"\bdegarelix\b",
    r"\babiraterone\b",
    r"\benzalutamide\b",
    r"\bapalutamide\b",
    r"\bdarolutamide\b",
)

_AMBIGUOUS_TREATMENT_TOKENS: Tuple[Tuple[str, str], ...] = (
    # (treatment regex, required nearby qualifier regex)
    (r"\bcryoablation\b", r"\bprostate\b"),
    (r"\bcryotherapy\b", r"\bprostate\b"),
    (r"\bablation\b", r"\bprostate\b"),
)

_COMPLETION_VERB_PATTERN = (
    r"(?:s/p|status\s+post|underwent|completed|received|"
    r"is\s+s/p|"
    r"following|after|"
    r"post-?treatment\s+(?:status|for))"
)
_COMPLETION_VERB_RE = re.compile(_COMPLETION_VERB_PATTERN, re.IGNORECASE)


def _completion_verb_nearby(text: str, position: int, window: int = 60) -> bool:
    """True if a completion verb appears within the ``window`` chars BEFORE
    ``position``. Anchoring before-only avoids matching 'underwent' at the
    end of an unrelated downstream sentence."""
    return bool(_COMPLETION_VERB_RE.search(text[max(0, position - window):position]))


def find_completed_treatments(text: str) -> List[str]:
    """Find evidence the patient has actually undergone urologic treatment.

    Returns a list of quoted assertions (e.g. 's/p radical prostatectomy
    2019', 'underwent EBRT'). An empty list means the patient is
    treatment-naive for prostate cancer.
    """
    found: List[str] = []

    for tx in _UNAMBIGUOUS_TREATMENT_TOKENS:
        for m in re.finditer(tx, text, re.IGNORECASE):
            if _preceded_by_negation(text, m.start()):
                continue
            if not _completion_verb_nearby(text, m.start()):
                continue
            # Capture the verb..noun span for a readable quote
            quote_start = max(0, m.start() - 60)
            raw = text[quote_start:m.end()]
            # Trim back to last sentence boundary so quotes are tight
            for sep in (". ", "\n"):
                idx = raw.rfind(sep, 0, len(raw) - (m.end() - m.start()))
                if idx != -1:
                    raw = raw[idx + len(sep):]
                    break
            found.append(raw.strip())

    for tx_pat, qualifier in _AMBIGUOUS_TREATMENT_TOKENS:
        qualifier_re = re.compile(qualifier, re.IGNORECASE)
        for m in re.finditer(tx_pat, text, re.IGNORECASE):
            if _preceded_by_negation(text, m.start()):
                continue
            # qualifier must appear in a tight window around the match
            window_text = text[max(0, m.start() - 60):m.end() + 60]
            if not qualifier_re.search(window_text):
                continue
            if not _completion_verb_nearby(text, m.start()):
                continue
            found.append(m.group(0))

    seen, deduped = set(), []
    for q in found:
        k = q.lower().strip()
        if k and k not in seen:
            seen.add(k)
            deduped.append(q)
    return deduped


# ---------------------------------------------------------------------------
# Raw clinical-document treatment-status scanner.
#
# The PMH + PSH + pathology search above is intentionally conservative —
# it ignores narrative text because LLM-synthesized HPI / Assessment
# content can contain confabulated treatments. The cost of that
# conservatism: when the clinician writes the treatment history ONLY in
# the narrative ("...subsequently received high-dose radiation therapy in
# Atlanta...", "Problem #1: prostate adenocarcinoma, status post
# radiation therapy and intermittent ADT..."), the verdict comes back as
# TREATMENT_NAIVE=True. The downstream ABSOLUTE-RULES block then tells
# the LLM to NOT mention radiation / Phoenix / recurrence — actively
# suppressing real clinical history. This is the failure mode the
# scanner below closes.
#
# Safety: the scanner ONLY emits a treatment when an explicit completion
# verb + treatment word sit inside a prostate-cancer context window. A
# stray "cryotherapy of actinic keratoses" (dermatology) does NOT match
# because no prostate-cancer marker sits within ±300 chars of it.
# ---------------------------------------------------------------------------

# Markers that signal we're in a prostate-cancer paragraph. Any one of
# these within ±300 chars of a treatment match licenses the match.
_PROSTATE_CONTEXT_RE = re.compile(
    r"(?:\bprostate\s+(?:cancer|adenocarcinoma|carcinoma|Ca|CaP)\b|"
    r"\bprostatic\s+adenocarcinoma\b|"
    r"\bGleason\b|\bGrade\s+Group\b|\bGG[1-5]\b|"
    r"\bCAPRA\b|\bD[''`]Amico\b)",
    re.IGNORECASE,
)

# Wide completion-verb vocabulary used only inside the raw-text scanner.
# Adds verbs that the conservative PMH/PSH search omits ("initiated",
# "started", "began", "opted for", "treated with", "is on", "was on",
# "has been on", "history of") because in narrative text those reliably
# mark a real prior treatment.
_WIDE_COMPLETION_VERB_RE = re.compile(
    r"(?:s/p|status\s+post|underwent|completed|received|"
    r"following|after|prior|"
    r"initiated|started|began|opted\s+for|treated\s+with|"
    r"is\s+(?:on|s/p)|was\s+(?:on|s/p)|has\s+been\s+on|history\s+of(?!\s+no))",
    re.IGNORECASE,
)

# Treatment-keyword patterns scanned in raw clinical text. Each requires
# a wide completion verb within 80 chars BEFORE the keyword AND a
# prostate-cancer context marker within ±300 chars (verified separately).
_RAW_TREATMENT_TOKENS: Tuple[str, ...] = (
    # Radiation (any form). Pattern allows "high-dose radiation",
    # "definitive radiation", "external beam radiation", "XRT", "EBRT",
    # "radiation therapy", or bare "radiation" — but only when a wide
    # completion verb sits before it.
    r"(?:high[\-\s]?dose\s+|definitive\s+|external\s+beam\s+|"
    r"intensity[\-\s]?modulated\s+)?radiation(?:\s+therapy)?",
    r"\bXRT\b",
    r"\bEBRT\b",
    r"\bIMRT\b",
    r"\bSBRT\b",
    r"\bIGRT\b",
    r"\bbrachytherapy\b",
    r"seed\s+implant(?:ation)?",
    # Surgery
    r"radical\s+prostatectomy",
    r"\bprostatectomy\b",
    r"\bRALP\b",
    r"\bRARP\b",
    r"\bRRP\b",
    # ADT / hormonal
    r"androgen\s+deprivation(?:\s+therapy)?",
    r"\bADT\b",
    r"\bleuprolide\b",
    r"\bLupron\b",
    r"\bEligard\b",
    r"\bdegarelix\b",
    r"\babiraterone\b",
    r"\benzalutamide\b",
    r"\bapalutamide\b",
    r"\bdarolutamide\b",
    # Focal
    r"focal\s+(?:therapy|ablation|cryoablation|cryotherapy|laser\s+ablation)",
    r"\bHIFU\b",
    r"\bTULSA(?:-PRO)?\b",
)

# Treatment effect / atypia markers that imply prior radiation even
# without a co-located completion verb (the pathologist commenting on
# "post-radiation atypia" is direct evidence radiation occurred).
_POST_RADIATION_EVIDENCE_RE = re.compile(
    r"(?:post[\-\s]?radiation|radiation)\s+(?:atypia|effect|change|fibrosis)|"
    r"treatment\s+effect[^.]{0,30}(?:radiation|XRT|EBRT)",
    re.IGNORECASE,
)


def _in_prostate_context(text: str, match_pos: int, window: int = 300) -> bool:
    """True if a prostate-cancer marker appears within ±window chars."""
    snippet = text[max(0, match_pos - window):match_pos + window]
    return bool(_PROSTATE_CONTEXT_RE.search(snippet))


def find_treatment_in_raw_clinical_text(text: str) -> List[str]:
    """Scan raw clinician-written clinical text for prostate-cancer
    treatment-status statements.

    Returns quoted assertions (e.g. "underwent prior radiation therapy",
    "initiated androgen deprivation therapy with Eligard"). The list is
    non-empty only when the patient has documented prior urologic cancer
    treatment.

    Safety guards (all must hold for a match):
      1. A wide completion verb sits within 80 chars BEFORE the treatment
         keyword (filters "considering radiation", "options include
         brachytherapy", "discussion of focal therapy").
      2. The match is not preceded by a negation token ("no", "denies",
         "declined", "refused").
      3. The match falls inside a prostate-cancer context window
         (filters dermatology cryotherapy, stone-cryoablation, etc.).
    """
    if not text:
        return []

    declined_re = re.compile(
        r"\b(?:declined|declines|refuses|refused|deferred|not\s+a\s+candidate)\b",
        re.IGNORECASE,
    )

    found: List[str] = []
    for tx_pattern in _RAW_TREATMENT_TOKENS:
        for m in re.finditer(tx_pattern, text, re.IGNORECASE):
            if _preceded_by_negation(text, m.start()):
                continue
            # Wide completion verb within 80 chars BEFORE the match.
            preceding_80 = text[max(0, m.start() - 80):m.start()]
            if not _WIDE_COMPLETION_VERB_RE.search(preceding_80):
                continue
            # Reject "declined / refused / deferred" in the same window
            # (these mean the patient did NOT receive the treatment).
            if declined_re.search(preceding_80):
                continue
            # Require prostate-cancer context within ±300 chars.
            if not _in_prostate_context(text, m.start()):
                continue
            # Capture a readable quote: from the completion verb to the
            # end of the treatment keyword.
            verb_match = _WIDE_COMPLETION_VERB_RE.search(preceding_80)
            quote_start = max(0, m.start() - 80) + (verb_match.start() if verb_match else 0)
            quote = text[quote_start:m.end()].strip()
            quote = re.sub(r"\s+", " ", quote)
            found.append(quote)

    # Direct evidence of past radiation via post-radiation atypia in a
    # pathology specimen. The pathologist describing "viable tumor with
    # no radiation atypia" or "post-radiation atypia in non-neoplastic
    # cells" is reporting on tissue from a patient who definitely had
    # radiation.
    for m in _POST_RADIATION_EVIDENCE_RE.finditer(text):
        if _preceded_by_negation(text, m.start()):
            continue
        if not _in_prostate_context(text, m.start()):
            continue
        found.append(f"pathology cites {m.group(0)!r}")

    # Dedup while preserving first-seen order
    seen, deduped = set(), []
    for q in found:
        k = q.lower().strip()
        if k and k not in seen:
            seen.add(k)
            deduped.append(q)
    return deduped


# ---------------------------------------------------------------------------
# Biopsy / ASAP detection
# ---------------------------------------------------------------------------
_BIOPSY_HEADER_RE = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{2,4}|[A-Za-z]{3}\s+\d{1,2},?\s+\d{4})"
    r"\s*[:.,]?\s*Prostate\s+biopsy",
    re.IGNORECASE,
)
_NEGATIVE_BIOPSY_RE = re.compile(
    r"(?:Negative\s+for\s+malignancy|"
    r"no\s+evidence\s+of\s+malignancy|"
    r"benign\s+prostat(?:e|ic)\s+tissue)",
    re.IGNORECASE,
)
_ASAP_RE = re.compile(
    r"(?:\batypical\s+small\s+acinar\s+proliferation\b|\bASAP\b)",
    re.IGNORECASE,
)


def count_biopsies_and_negatives(pathology_section: str) -> Tuple[int, int]:
    """Return ``(distinct_biopsy_dates, lines_with_negative_finding)``."""
    if not pathology_section:
        return 0, 0
    dates = {m.group(1) for m in _BIOPSY_HEADER_RE.finditer(pathology_section)}
    negs = len(_NEGATIVE_BIOPSY_RE.findall(pathology_section))
    return len(dates), negs


def find_asap(text: str) -> bool:
    return bool(_ASAP_RE.search(text or ""))


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------
def extract_section(stage1_note: str, section_name: str) -> str:
    """Pull a single Stage 1 section by its header (case-insensitive).

    Sections end at either the next ``=====`` separator line or the next
    ALL-CAPS header followed by a colon.
    """
    if not stage1_note:
        return ""
    header_re = re.compile(
        r"^\s*" + re.escape(section_name) + r"\s*:?\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    m = header_re.search(stage1_note)
    if not m:
        return ""
    start = m.end()
    end_re = re.compile(
        r"^\s*(?:={4,}|[A-Z][A-Z\s/]{3,}:)\s*$",
        re.MULTILINE,
    )
    m2 = end_re.search(stage1_note, start)
    end = m2.start() if m2 else len(stage1_note)
    return stage1_note[start:end].strip()


# ---------------------------------------------------------------------------
# Main fact extraction
# ---------------------------------------------------------------------------
@dataclass
class PatientStatusFacts:
    """Deterministic ground-truth for the Stage 2 LLM agents."""

    cancer_status: str = "UNCERTAIN"
    """One of: ABSENT | PRESENT | TREATED | UNCERTAIN."""

    cancer_evidence: List[str] = field(default_factory=list)
    """Positive cancer evidence quotes pulled from the source."""

    confirmed_urologic_treatments: List[str] = field(default_factory=list)
    """Quoted assertions of completed treatments. Empty -> treatment-naive."""

    treatment_naive: bool = True
    """True if no confirmed prior urologic cancer treatments."""

    phoenix_applicable: bool = False
    """True only if at least one confirmed prior radiation treatment exists."""

    biopsy_count: int = 0
    biopsy_all_negative: bool = False
    asap_present: bool = False

    inconsistencies: List[str] = field(default_factory=list)
    """Source-internal contradictions surfaced for the provider."""


def extract_patient_status_facts(
    stage1_note: str,
    raw_clinical_text: Optional[str] = None,
) -> PatientStatusFacts:
    """Compute deterministic ground-truth facts from clinical sources.

    Args:
        stage1_note: The structured Stage 1 note text (PMH, PSH, pathology
            sections deterministically extracted). This is the conservative
            search space.
        raw_clinical_text: Optional raw clinician-written document. When
            provided, the function additionally scans it for explicit
            prior-treatment-status statements in narrative HPI / Assessment
            / Problem-list text. Matches require BOTH a wide completion
            verb adjacent to the treatment keyword AND a prostate-cancer
            context marker within ±300 chars, which filters dermatology /
            stone / other-specialty noise. Pass the raw input whenever
            available — without it, patients whose only treatment record
            lives in narrative ("underwent high-dose radiation in Atlanta")
            will be mis-classified as treatment-naive and the downstream
            ABSOLUTE-RULES block will actively suppress correct clinical
            framing.
    """
    if not stage1_note:
        return PatientStatusFacts(cancer_status="UNCERTAIN")

    pmh = extract_section(stage1_note, "PAST MEDICAL HISTORY") or \
        extract_section(stage1_note, "PMH")
    pathology = extract_section(stage1_note, "PATHOLOGY RESULTS")
    psh = extract_section(stage1_note, "PAST SURGICAL HISTORY") or \
        extract_section(stage1_note, "PSH")

    # Search spaces are narrowed to DETERMINISTIC sources only.
    #   cancer evidence  -> PMH + pathology + PSH
    #   treatment evidence -> PMH + PSH (NOT pathology — pathology reports
    #     never declare a treatment was performed; using them as a
    #     treatment source produced false positives in testing).
    # HPI is excluded deliberately even though it sits inside the Stage 1
    # note: the HPI is LLM-synthesized by the upstream HPI agent and
    # may itself contain confabulated treatments (e.g. "completed
    # definitive focal therapy"). Reading HPI as ground truth would let
    # that hallucination flip treatment_naive to False and silently
    # poison the rest of this layer. The HPI agent has its own
    # protection (it also receives the authoritative_facts block).
    cancer_search = "\n".join(filter(None, (pmh, pathology, psh)))
    treatment_search = "\n".join(filter(None, (pmh, psh)))

    cancer_evidence = find_cancer_evidence(cancer_search)
    treatments = find_completed_treatments(treatment_search)

    # Raw clinical-document augmentation. The PMH/PSH/pathology search
    # above is conservative; treatments described only in narrative
    # ("Problem #1: prostate cancer s/p radiation", "received Eligard in
    # November 2023") would be missed. The raw scanner closes that gap
    # using strict co-occurrence requirements that filter cross-specialty
    # noise. Run only when raw_clinical_text was supplied; merge findings
    # into the treatment list.
    if raw_clinical_text:
        raw_treatments = find_treatment_in_raw_clinical_text(raw_clinical_text)
        for t in raw_treatments:
            if t.lower() not in {x.lower() for x in treatments}:
                treatments.append(t)
        # Also broaden cancer-evidence pickup: an explicit prostate-cancer
        # diagnosis in the raw narrative (e.g. prior assessment problem
        # list) is reliable ground truth that PMH may have logged only as
        # the bare phrase "Prostate cancer".
        for ev in find_cancer_evidence(raw_clinical_text):
            if ev.lower() not in {x.lower() for x in cancer_evidence}:
                cancer_evidence.append(ev)

    biopsy_count, neg_count = count_biopsies_and_negatives(pathology)
    biopsy_all_negative = (
        biopsy_count > 0 and neg_count > 0 and not cancer_evidence
    )
    asap = find_asap(pathology)

    if cancer_evidence:
        status = "TREATED" if treatments else "PRESENT"
    elif biopsy_all_negative:
        status = "ABSENT"
    elif biopsy_count == 0 and not cancer_evidence and not treatments:
        # No biopsy, no cancer markers, no treatments: safe default is ABSENT
        # for the purpose of authorizing cancer-state vocabulary.
        status = "ABSENT"
    else:
        status = "UNCERTAIN"

    # Phoenix criteria apply post-radiation. Match any radiation phrasing
    # the raw-text scanner might produce: bare "radiation", "high-dose
    # radiation", "external beam", IMRT/SBRT/IGRT/XRT, brachytherapy,
    # plus pathology-cited post-radiation atypia (which directly evidences
    # prior radiation even when treatment history wasn't otherwise stated).
    radiation_re = re.compile(
        r"(?:radiation|EBRT|IMRT|SBRT|IGRT|XRT|brachytherapy|"
        r"seed\s+implant|post[\-\s]?radiation\s+atypia)",
        re.IGNORECASE,
    )
    phoenix = any(radiation_re.search(t) for t in treatments)

    inconsistencies: List[str] = []
    if treatments and status == "ABSENT":
        inconsistencies.append(
            "Source asserts treatment(s) " + repr(treatments[:3]) +
            " but pathology shows no cancer evidence."
        )

    return PatientStatusFacts(
        cancer_status=status,
        cancer_evidence=cancer_evidence,
        confirmed_urologic_treatments=treatments,
        treatment_naive=(len(treatments) == 0),
        phoenix_applicable=phoenix,
        biopsy_count=biopsy_count,
        biopsy_all_negative=biopsy_all_negative,
        asap_present=asap,
        inconsistencies=inconsistencies,
    )


# ---------------------------------------------------------------------------
# Context sanitizer
# ---------------------------------------------------------------------------
# Sentence-level assertion that the patient HAS undergone a treatment.
# Conditional phrasings ("considering focal therapy", "patient declined
# focal therapy", "if focal therapy is offered") do NOT match because they
# lack a completion verb.
_TREATMENT_ASSERTION_RE = re.compile(
    r"(?:" + _COMPLETION_VERB_PATTERN + r")"
    r"(?:\s+\S+){0,8}?"
    r"\s*(?:" + "|".join(_UNAMBIGUOUS_TREATMENT_TOKENS) + r")",
    re.IGNORECASE,
)

# Cancer-state vocabulary that is only valid if there is a prior cancer
# diagnosis (and, for Phoenix specifically, prior radiation). The
# [\s\-]+ tolerances handle compound forms like "biochemical-recurrence",
# "post-treatment", "Phoenix-criteria".
_CANCER_STATE_RE = re.compile(
    r"\b(?:"
    r"biochemical[\s\-]+(?:recurrence|failure|relapse)|"
    r"Phoenix[\s\-]+(?:criteria|threshold|definition|biochemical|recurrence|nadir)|"
    r"exceeding\s+the\s+(?:Phoenix|biochemical[\s\-]+\S+\s+)?(?:threshold|criteria)|"
    r"nadir\s*\+\s*2(?:\.0)?|"
    r"salvage\s+(?:therapy|treatment|radiation|EBRT|prostatectomy|chemo)|"
    r"post[\s\-]?treatment\s+(?:surveillance|recurrence|PSA|status)|"
    r"recurrent\s+(?:prostate\s+)?(?:cancer|disease)|"
    r"diagnosis\s+of\s+prostate\s+(?:cancer|adenocarcinoma)|"
    r"history\s+of\s+prostate\s+(?:cancer|adenocarcinoma)|"
    r"completed\s+definitive\s+(?:focal\s+therapy|radiation|treatment|brachytherapy)|"
    r"after\s+(?:definitive\s+)?(?:focal\s+therapy|focal\s+ablation|"
    r"radiation|radiation\s+therapy|EBRT|brachytherapy|HIFU|TULSA|"
    r"prostatectomy|radical\s+prostatectomy)"
    r")\b",
    re.IGNORECASE,
)


def sanitize_context_against_facts(
    context_text: str,
    facts: PatientStatusFacts,
) -> Tuple[str, List[str]]:
    """Strip sentences that contradict the ground-truth ``facts``.

    Returns ``(sanitized_text, list_of_stripped_sentences)``. The stripped
    list is logged at INFO level by the caller for traceability.

    Sentences are matched at predicate-level: only sentences ASSERTING a
    contradicting treatment / cancer state are dropped. Discussion,
    options, and declined-treatment mentions are preserved.
    """
    if not context_text or not context_text.strip():
        return context_text, []

    stripped: List[str] = []
    keep: List[str] = []

    # Split on real sentence terminators (period/?/!) followed by whitespace,
    # OR on paragraph breaks (blank lines). A single \n inside a paragraph is
    # NOT a sentence boundary — long sentences wrapped across multiple lines
    # by a prior renderer must stay joined so the negation guard works.
    for raw in re.split(r"(?<=[.!?])\s+|\n\s*\n+", context_text):
        sentence = raw.strip()
        if not sentence:
            continue

        drop_reason = None

        if facts.treatment_naive:
            if _TREATMENT_ASSERTION_RE.search(sentence):
                drop_reason = "treatment assertion (patient is treatment-naive)"
            else:
                # Ambiguous treatments asserted with prostate qualifier
                for amb_pat, qual_pat in _AMBIGUOUS_TREATMENT_TOKENS:
                    if (re.search(amb_pat, sentence, re.IGNORECASE)
                            and re.search(qual_pat, sentence, re.IGNORECASE)
                            and _COMPLETION_VERB_RE.search(sentence)):
                        drop_reason = (
                            "ambiguous treatment assertion w/ prostate qualifier"
                        )
                        break

        if not drop_reason and facts.cancer_status == "ABSENT":
            m = _CANCER_STATE_RE.search(sentence)
            # Skip the strip if the cancer-state phrase is itself negated
            # ("No family history of prostate cancer", "no biochemical
            # recurrence detected").
            if m and not _preceded_by_negation(sentence, m.start()):
                drop_reason = "cancer-state vocabulary (no cancer evidence)"

        if not drop_reason and not facts.phoenix_applicable:
            # Phoenix without radiation is always wrong, even for cancer-present
            # patients (Phoenix is post-radiation specifically).
            phoenix_m = re.search(
                r"\b(?:Phoenix[\s\-]+(?:criteria|threshold|definition|biochemical|recurrence|nadir)|"
                r"nadir\s*\+\s*2(?:\.0)?|"
                r"exceeding\s+the\s+(?:Phoenix|biochemical))",
                sentence, re.IGNORECASE,
            )
            if phoenix_m and not _preceded_by_negation(sentence, phoenix_m.start()):
                drop_reason = "Phoenix vocabulary (no prior radiation)"

        if drop_reason:
            stripped.append(sentence)
            logger.info(
                "PatientStatusFacts sanitizer dropped sentence | reason=%s | text=%s",
                drop_reason, sentence[:160],
            )
            continue

        keep.append(sentence)

    sanitized = "\n".join(keep).strip()
    return sanitized, stripped


# ---------------------------------------------------------------------------
# Prompt formatter
# ---------------------------------------------------------------------------
def format_facts_for_prompt(facts: PatientStatusFacts) -> str:
    """Render the verdict as the authoritative prompt block prepended to
    both Assessment and Plan LLM contexts."""
    lines: List[str] = [
        "=== PATIENT GROUND TRUTH (AUTHORITATIVE - NEVER CONTRADICT) ===",
        "Derived deterministically from the Stage 1 source documents.",
        "Treat the following as fact. If your generated text contradicts",
        "any line below, your answer is wrong and will be rejected.",
        "",
        f"PROSTATE_CANCER_STATUS: {facts.cancer_status}",
    ]
    if facts.cancer_evidence:
        lines.append("  Evidence found:")
        for ev in facts.cancer_evidence[:5]:
            lines.append(f"    - {ev}")
    else:
        lines.append(
            "  No positive cancer evidence found in PATHOLOGY, PMH, PSH or HPI."
        )

    lines.append("")
    lines.append(f"TREATMENT_NAIVE: {facts.treatment_naive}")
    if facts.confirmed_urologic_treatments:
        lines.append("  Confirmed urologic treatments:")
        for tx in facts.confirmed_urologic_treatments[:5]:
            lines.append(f"    - {tx}")
    else:
        lines.append("  No confirmed prior urologic treatments in the source.")

    lines.append("")
    lines.append(f"PHOENIX_CRITERIA_APPLICABLE: {facts.phoenix_applicable}")
    if not facts.phoenix_applicable:
        lines.append(
            "  Phoenix criteria (nadir+2) apply only to post-radiation patients; "
            "this patient has no documented radiation history."
        )

    if facts.biopsy_count > 0:
        lines.append("")
        verdict = "all negative for malignancy" if facts.biopsy_all_negative else "mixed/positive"
        lines.append(
            f"BIOPSY_HISTORY: {facts.biopsy_count} prostate biopsy report(s), {verdict}"
        )

    if facts.asap_present:
        lines.append("")
        lines.append("ASAP_PRESENT: TRUE")
        lines.append(
            "  Significance: Atypical small acinar proliferation is a "
            "SURVEILLANCE indicator, NOT a cancer diagnosis. It does NOT "
            "authorize the language 'biochemical recurrence', 'salvage', "
            "'post-treatment', or claims of completed treatment."
        )

    if facts.inconsistencies:
        lines.append("")
        lines.append("INCONSISTENCIES_DETECTED:")
        for inc in facts.inconsistencies:
            lines.append(f"  - {inc}")
        lines.append("  -> Resolve in favor of the deterministic verdicts above.")

    lines.append("")
    lines.append("ABSOLUTE RULES based on the above:")
    if facts.treatment_naive:
        lines.append(
            "  - The patient is TREATMENT-NAIVE for prostate cancer. "
            "DO NOT use any of: 'focal therapy', 'focal ablation', "
            "'radiation therapy', 'EBRT', 'IMRT', 'SBRT', 'brachytherapy', "
            "'HIFU', 'TULSA', 'radical prostatectomy', 'ADT', "
            "'androgen deprivation', 'salvage', 'biochemical recurrence', "
            "'Phoenix criteria', 'post-treatment', 's/p <any treatment>'."
        )
        lines.append(
            "  - DO NOT state or imply the patient has undergone any "
            "prostate-cancer-directed treatment."
        )
    if facts.cancer_status == "ABSENT":
        lines.append(
            "  - The patient has NO confirmed prostate cancer diagnosis. "
            "Rising PSA is a workup question for NEW disease, NOT "
            "biochemical recurrence."
        )
        lines.append(
            "  - DO NOT title any problem 'Biochemical recurrence' or "
            "'Rising PSA after <treatment>'. Acceptable Problem #1 framings: "
            "'Episodic PSA elevation', 'Elevated PSA - workup', "
            "'PSA surveillance with ASAP on prior biopsy'."
        )
    if facts.asap_present and facts.cancer_status != "PRESENT":
        lines.append(
            "  - ASAP warrants continued PSA trending and consideration of "
            "repeat or MRI-guided biopsy per AUA. It does NOT warrant "
            "cancer-directed therapy."
        )
    if not facts.phoenix_applicable:
        lines.append(
            "  - DO NOT invoke Phoenix criteria, nadir+2, or describe any "
            "PSA value as 'exceeding the biochemical-recurrence threshold'."
        )

    return "\n".join(lines)
