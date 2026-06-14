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


def extract_patient_status_facts(stage1_note: str) -> PatientStatusFacts:
    """Compute deterministic ground-truth facts from the Stage 1 note.

    The Stage 1 note is the authoritative source. We deliberately do NOT
    scan raw input documents here — that's where dermatology cryotherapy
    and other cross-specialty noise lives, and the whole point of this
    layer is to avoid the LLM seeing those tokens as if they were part of
    the urologic story.
    """
    if not stage1_note:
        return PatientStatusFacts(cancer_status="UNCERTAIN")

    pmh = extract_section(stage1_note, "PAST MEDICAL HISTORY") or \
        extract_section(stage1_note, "PMH")
    pathology = extract_section(stage1_note, "PATHOLOGY RESULTS")
    psh = extract_section(stage1_note, "PAST SURGICAL HISTORY") or \
        extract_section(stage1_note, "PSH")
    hpi = extract_section(stage1_note, "HPI")

    # Search spaces are narrowed deliberately:
    #   cancer evidence -> PMH + pathology + PSH + HPI
    #   treatment evidence -> PMH + PSH + HPI (NOT pathology — pathology
    #     reports never declare a treatment was performed; using them as
    #     a treatment source produced false positives in testing).
    cancer_search = "\n".join(filter(None, (pmh, pathology, psh, hpi)))
    treatment_search = "\n".join(filter(None, (pmh, psh, hpi)))

    cancer_evidence = find_cancer_evidence(cancer_search)
    treatments = find_completed_treatments(treatment_search)
    biopsy_count, neg_count = count_biopsies_and_negatives(pathology)
    biopsy_all_negative = (
        biopsy_count > 0 and neg_count > 0 and not cancer_evidence
    )
    asap = find_asap(pathology) or find_asap(hpi)

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

    radiation_re = re.compile(
        r"(?:radiation\s+therapy|EBRT|IMRT|SBRT|IGRT|XRT|brachytherapy)",
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
