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
from typing import Dict, List, Optional, Tuple

from .gu_diagnoses import GUDiagnosis, detect_gu_diagnoses, detect_patient_sex

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


# Family-history relatives. A positive cancer mention in the same window
# as one of these is a relative's history, NOT the patient's.
_FAMILY_HISTORY_RE = re.compile(
    r"\b(?:"
    r"father|mother|brother|sister|son|daughter|"
    r"uncle|aunt|cousin|nephew|niece|grandfather|grandmother|"
    r"grandparent|paternal|maternal|"
    r"half[\s-]?brother|half[\s-]?sister|step[\s-]?brother|step[\s-]?sister|"
    r"family\s+history\s+of|positive\s+family\s+history|fhx|fh\b"
    r")\b",
    re.IGNORECASE,
)


# Hedging vocabulary — markers of uncertainty, suspicion, or comparison
# that do NOT establish a confirmed diagnosis. A "prostate cancer"
# mention preceded by one of these is NOT cancer evidence.
_HEDGING_RE = re.compile(
    r"\b(?:"
    r"possible|suspected|suspicious(?:\s+for)?|"
    r"concern(?:ing)?(?:\s+for)?|may\s+have|might\s+have|"
    r"such\s+as|e\.?g\.?|for\s+example|including|like|"
    r"rule[\sd]?\s*out|r/o|to\s+evaluate\s+for|"
    r"workup\s+for|screening\s+for|risk\s+of|"
    r"prevention\s+of|prophylaxis\s+(?:against|for)|"
    r"high[\s-]?risk\s+(?:for|of)|elevated\s+risk\s+(?:for|of)"
    r")\b",
    re.IGNORECASE,
)


def _is_family_history_or_hedged(text: str, match_start: int, window: int = 80) -> bool:
    """True if the span at ``match_start`` is a family-history mention or
    a hedged/suspected/comparison reference rather than a confirmed
    diagnosis. Both contexts must be excluded from cancer evidence —
    otherwise "PATERNAL GREAT GRANDFATHER died of prostate cancer" and
    "workup for possible prostate cancer" would falsely promote
    cancer_status to PRESENT."""
    snippet = text[max(0, match_start - window):match_start]
    if _FAMILY_HISTORY_RE.search(snippet):
        return True
    if _HEDGING_RE.search(snippet):
        return True
    return False


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
            # Family-history mentions are about a relative, not the
            # patient. Hedged / suspected / comparison mentions are not
            # confirmed diagnoses. Both must be excluded.
            if _is_family_history_or_hedged(text, m.start()):
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
    # Each alternation anchored with \b so e.g. "was on" cannot match
    # within "was only", "is on" within "is only", "s/p" within "s/p-
    # something". Temporal connectives ('after', 'prior', 'following')
    # removed because they match harmless prose ('after the appointment',
    # 'prior to discussion', 'following the procedure note').
    r"(?:\bs/?p\b|\bstatus\s+post\b|\bunderwent\b|\bcompleted\b|"
    r"\breceived\b|"
    r"\binitiated\b|\bstarted\b|\bbegan\b|\bopted\s+for\b|"
    r"\btreated\s+with\b|"
    r"\bis\s+on\b|\bis\s+s/p\b|"
    r"\bwas\s+on\b|\bwas\s+s/p\b|"
    r"\bhas\s+been\s+on\b|\bhistory\s+of(?!\s+no)\b)",
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
    # Discussion / counseling / option-list / intent markers. When any
    # of these sit in the same window as a "completion-verb-like" token,
    # the prose is COUNSELING about the option, not asserting it was
    # performed. Without this filter, sentences like
    #   "He says that he was only offered RALP and AS at USA"
    # — where 'was on' matches inside 'was only' or where 'history of'
    # appears nearby — register as completed RALP.
    discussion_re = re.compile(
        r"\b(?:discuss(?:ed|ing|ion)?|consider(?:ed|ing|ation)?|"
        r"offer(?:ed|ing)?|interest(?:ed)?\s+in|may\s+benefit|"
        r"option(?:s)?\s+(?:of|for|include|are|to)|"
        r"candidate\s+(?:for|of)|recommend(?:ed|ing|ation)?|"
        r"plan(?:ned|ning)?\s+(?:for|to)|consult(?:ed|ation)?\s+(?:for|to)|"
        r"referred\s+(?:for|to)|scheduled\s+(?:for|to)|"
        r"await(?:ing|s)?|elect(?:ed)?\s+against|"
        r"under\s+consideration|"
        r"including|consist(?:ing|s)\s+of|such\s+as|"
        r"pursu(?:e|ing|ed)|"
        r"never\s+heard\s+of|never\s+been\s+told\s+about)\b",
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
            # Reject if the broader ±80-char window shows the prose is
            # an option discussion / counseling / intent statement.
            window = text[max(0, m.start() - 100):m.end() + 60]
            if discussion_re.search(window):
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
# Treatment current/discontinued status detection.
#
# A confirmed prior treatment is not the same thing as a currently active
# one. Hormonal therapy in particular can be intermittent: the patient
# received an LHRH agonist in November 2023, took the last injection in
# May 2024, then "declined restart in favor of monitoring." Without this
# distinction, the HPI agent writes "He remains on continuous androgen
# deprivation therapy" — directly contradicting the source. The detector
# below identifies the most common discontinuation language so the
# downstream prompt can frame each treatment category correctly.
# ---------------------------------------------------------------------------
_ADT_DISCONTINUED_RE = re.compile(
    r"(?:declined|declines|refused|refuses|elected\s+against|opted\s+against|"
    r"opt(?:ed)?\s+for\s+monitoring|favor\s+of\s+monitoring|"
    r"transition(?:ed)?\s+to\s+monitoring|"
    r"discontinued|stopped|held|off|"
    r"completed)\s+"
    r"(?:.{0,40}?)?"
    r"(?:repeat\s+|restart\s+|further\s+)?"
    r"(?:ADT|androgen\s+deprivation|Lupron|Eligard|leuprolide|degarelix)",
    re.IGNORECASE,
)
_ADT_DISCONTINUED_BY_FOLLOWING_RE = re.compile(
    r"(?:ADT|androgen\s+deprivation|Lupron|Eligard|leuprolide|degarelix)\s+"
    r"(?:.{0,40}?)?"
    r"(?:was\s+discontinued|was\s+stopped|was\s+held|was\s+completed|"
    r"is\s+off|now\s+off|currently\s+off|holiday|"
    r"declined\s+(?:restart|repeat)|elected\s+against\s+(?:restart|repeat))",
    re.IGNORECASE,
)
_ADT_ACTIVE_RE = re.compile(
    r"(?:currently\s+on|continues?\s+on|ongoing|monthly|every\s+\d+\s+months?|"
    r"q\d+\s+month)\s+"
    r"(?:.{0,30}?)?"
    r"(?:ADT|androgen\s+deprivation|Lupron|Eligard|leuprolide|degarelix)",
    re.IGNORECASE,
)
# A FINITE oncologic course that has reached its end. "completed" (not just
# "stopped/discontinued") is the phrasing the verb-based detectors miss, and
# it is the dominant context-blind-recommendation driver once both stages
# share these facts: the Plan is told to "continue Eligard" because a finished
# fixed course still looks active.
_ADT_FINITE_COMPLETED_RE = re.compile(
    r"(?:completed|finished|received\s+all\s+of)\s+(?:his\s+|her\s+|the\s+|a\s+|an\s+)?"
    r"(?:\d+[-\s]?(?:year|yr|month|mo)s?|planned|prescribed|"
    r"\d+\s*(?:of|/)\s*\d+\s*(?:dose|injection|shot|cycle))"
    r"[^.\n]{0,40}?(?:course|therapy|ADT|androgen\s+deprivation|"
    r"leuprolide|lupron|eligard|goserelin|zoladex|degarelix|"
    r"abiraterone|enzalutamide|apalutamide|darolutamide)"
    r"|(?:final|last)\s+(?:dose|injection|shot)\s+(?:of\s+)?"
    r"(?:ADT|leuprolide|lupron|eligard|goserelin|zoladex|degarelix)",
    re.IGNORECASE,
)
_ADT_TOKEN_RE = re.compile(
    r"\b(?:ADT|androgen\s+deprivation|leuprolide|lupron|eligard|goserelin|"
    r"zoladex|degarelix|relugolix|orgovyx|abiraterone|enzalutamide|"
    r"apalutamide|darolutamide)\b",
    re.IGNORECASE,
)


_ADT_CLASS_TOKENS = (
    "eligard", "leuprolide", "lupron", "degarelix", "goserelin", "zoladex",
    "zoladez", "relugolix", "orgovyx", "firmagon", "abiraterone", "zytiga",
    "enzalutamide", "xtandi", "apalutamide", "erleada", "darolutamide",
    "nubeqa", "bicalutamide", "casodex",
)
_CHEMO_CLASS_TOKENS = ("docetaxel", "cabazitaxel", "taxotere", "jevtana")


def _drop_meds_for_inactive_category(
    active_meds: List[str], status: Dict[str, str],
) -> List[str]:
    """Drop ADT/chemo-class drugs from the active-med list when the
    category-level status detector marked that class DISCONTINUED/COMPLETED."""
    if not active_meds or not status:
        return active_meds
    adt_inactive = status.get("adt") in ("DISCONTINUED", "COMPLETED")
    chemo_inactive = status.get("chemo") in ("DISCONTINUED", "COMPLETED")
    if not (adt_inactive or chemo_inactive):
        return active_meds
    kept: List[str] = []
    for med in active_meds:
        ml = med.lower()
        if adt_inactive and any(t in ml for t in _ADT_CLASS_TOKENS):
            continue
        if chemo_inactive and any(t in ml for t in _CHEMO_CLASS_TOKENS):
            continue
        kept.append(med)
    return kept


def _detect_treatment_active_status(
    raw_text: str,
    confirmed_treatments: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Return per-category treatment status verdict.

    Only categories backed by at least one entry in ``confirmed_treatments``
    are emitted — this prevents false positives from template / checkbox
    text ("Radical prostatectomy: [ ]") or option-list discussions
    ("treatment options include focal therapy") that the upstream
    treatment validator already filtered out.

    Categories: 'adt', 'radiation', 'prostatectomy', 'focal', 'chemo'.
    Verdicts: 'ACTIVE' | 'DISCONTINUED' | 'COMPLETED' | 'UNCERTAIN'.
    """
    out: Dict[str, str] = {}
    if not raw_text:
        return out
    joined = "\n".join(confirmed_treatments).lower() if confirmed_treatments else ""

    _adt_in_confirmed = bool(re.search(
        r"\b(?:adt|androgen\s+deprivation|leuprolide|lupron|eligard|"
        r"degarelix|abiraterone|enzalutamide|apalutamide|darolutamide)\b",
        joined,
    ))
    _adt_finite_completed = bool(_ADT_FINITE_COMPLETED_RE.search(raw_text))

    # ADT — explicit discontinuation language dominates over active language.
    if _adt_in_confirmed:
        has_adt_discontinued = bool(
            _ADT_DISCONTINUED_RE.search(raw_text)
            or _ADT_DISCONTINUED_BY_FOLLOWING_RE.search(raw_text)
            or _adt_finite_completed
        )
        has_adt_active = bool(_ADT_ACTIVE_RE.search(raw_text))
        if has_adt_discontinued:
            out['adt'] = 'DISCONTINUED'
        elif has_adt_active:
            out['adt'] = 'ACTIVE'
        else:
            out['adt'] = 'UNCERTAIN'
    elif _adt_finite_completed and _ADT_TOKEN_RE.search(raw_text):
        # Ungated SAFE-direction path: when confirmed_treatments missed the ADT
        # (patient_status_facts misclassified a treated patient as naive), we
        # still mark a FINITE-COMPLETED course as DISCONTINUED. We only emit in
        # the completed direction here — never ACTIVE — so this cannot create a
        # false "continue ADT" recommendation.
        out['adt'] = 'DISCONTINUED'

    # One-time treatments — confirmed-list membership IS the COMPLETED signal.
    if re.search(
        r"\b(?:radiation|xrt|ebrt|imrt|sbrt|igrt|brachytherapy|"
        r"seed\s+implant)\b",
        joined,
    ):
        out['radiation'] = 'COMPLETED'
    if re.search(r"\b(?:radical\s+)?prostatectomy|\bralp\b|\brarp\b|\brrp\b",
                 joined):
        out['prostatectomy'] = 'COMPLETED'
    if re.search(
        r"\bfocal\s+(?:therapy|ablation|cryoablation|cryotherapy|laser\s+ablation)|"
        r"\bhifu\b|\btulsa\b",
        joined,
    ):
        out['focal'] = 'COMPLETED'

    return out


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

    clinical_timeline: List["TimelineEvent"] = field(default_factory=list)
    """Chronologically-sorted dated clinical events extracted from raw
    source text. Includes DIAGNOSIS, TREATMENT_STARTED / COMPLETED /
    RESTARTED / DECLINED, PATHOLOGY, IMAGING, PROCEDURE (cystoscopy /
    urodynamics / biopsy / TURBT / DEXA / etc.), STAGING_DECISION
    (mCRPC / mHSPC / biochemical recurrence). The CC / HPI / Assessment /
    Plan agents anchor their narrative to this timeline so events that
    happened at different times (e.g. ADT completed 04/2025, then
    RESTARTED 03/2026 for mCRPC) are not averaged into a single static
    'on ADT' or 'off ADT' frame."""

    current_phase: str = "UNCERTAIN"
    """Deterministic disease/treatment-phase verdict from the timeline.
    One of: TREATMENT_NAIVE | ON_INITIAL_TREATMENT |
    POST_TREATMENT_SURVEILLANCE | BIOCHEMICAL_RECURRENCE |
    SALVAGE_OR_RESTART | METASTATIC_HORMONE_SENSITIVE |
    METASTATIC_CASTRATION_RESISTANT | PROGRESSION | UNCERTAIN.
    Surfaces in the GROUND TRUTH block to steer the narrative arc.
    mCRPC verdict in particular tells the Plan agent that ADT is
    indefinite — preventing the 'no further ADT is planned' error."""

    current_active_treatments: List[str] = field(default_factory=list)
    """Meds the patient is currently taking, anchored to the most-recent
    medications list in the source. Used by the Plan agent so it does
    not drop a continuing med (Eligard / abiraterone / prednisone) from
    the continuation list."""

    procedure_findings: List["ProcedureFinding"] = field(default_factory=list)
    """Key findings from urologic procedures (cystoscopy, urodynamics,
    biopsy, TURBT, DEXA, etc.). Surfaced separately because these were
    frequently missed by synthesis agents despite being decision-driving."""

    patient_sex: str = ""
    """'female' | 'male' | '' from demographics. Guards against
    anatomically-impossible narratives (prostate cancer in a female patient)."""

    other_gu_diagnoses: List[GUDiagnosis] = field(default_factory=list)
    """Non-prostate GU diagnoses (renal / bladder / upper-tract / testicular /
    penile / adrenal), each with organ + category (cancer / indeterminate /
    benign) + grade + status. Everything else in this layer models ONLY
    prostate cancer; without this the CC/HPI/Assessment/Plan agents have no
    structured anchor for a renal-mass or bladder-tumor primary and default to
    a prostate/PSA narrative (or hallucinate prostate cancer)."""

    treatment_active_status: Dict[str, str] = field(default_factory=dict)
    """Per-category current-status verdict for the HPI agent. Categories:
    'adt' (DISCONTINUED | ACTIVE), 'radiation'/'prostatectomy'/'focal'
    (COMPLETED if present). Empty when no treatments detected. The HPI
    prompt uses this to distinguish 'remains on continuous ADT' (wrong
    when status is DISCONTINUED) from the correct 'previously received
    ADT and elected against restart in favor of monitoring' framing."""


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

    # Per-category current-vs-discontinued verdict. Computed from raw
    # clinical text + the already-validated treatments list so checkbox /
    # template / option-list mentions cannot trip a false COMPLETED.
    treatment_active = {}
    if treatments:
        active_search = raw_clinical_text or stage1_note
        treatment_active = _detect_treatment_active_status(
            active_search, confirmed_treatments=treatments,
        )

    # Clinical timeline + phase classifier + current active treatments
    # + procedure findings. Built from the raw clinician text so the
    # CC/HPI/Assessment/Plan agents see a structured chronological view
    # of the patient rather than having to infer ordering from prose.
    # Lazy import keeps patient_status_facts importable in isolation.
    timeline: List = []
    current_phase = "UNCERTAIN"
    active_meds: List[str] = []
    proc_findings: List = []
    raw_for_timeline = raw_clinical_text or stage1_note or ""
    if raw_for_timeline:
        from .clinical_timeline import (
            extract_clinical_timeline,
            classify_current_phase,
            detect_current_active_treatments,
            extract_procedure_findings,
        )
        timeline = extract_clinical_timeline(raw_for_timeline)
        current_phase = classify_current_phase(timeline)
        # current_active_treatments now comes from the AUTHORITATIVE VistA
        # RXOP active-outpatient list (see detect_current_active_treatments).
        # That list is definitive for current meds, so we do NOT post-filter
        # it by narrative treatment-status. (ADT/Eligard is handled separately
        # via treatment_active_status because intermittent ADT is often absent
        # from the active Rx list even when ongoing.)
        active_meds = detect_current_active_treatments(raw_for_timeline)
        proc_findings = extract_procedure_findings(raw_for_timeline)

    # Multi-cancer ground truth: patient sex + non-prostate GU diagnoses. The
    # rest of this function is prostate-only; these give the CC/HPI/Assessment/
    # Plan agents a structured anchor for a renal-mass / bladder-tumor primary.
    detect_src = raw_for_timeline or stage1_note or ""
    patient_sex = detect_patient_sex(detect_src)
    other_gu = detect_gu_diagnoses(detect_src)

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
        patient_sex=patient_sex,
        other_gu_diagnoses=other_gu,
        treatment_active_status=treatment_active,
        clinical_timeline=timeline,
        current_phase=current_phase,
        current_active_treatments=active_meds,
        procedure_findings=proc_findings,
    )


# ---------------------------------------------------------------------------
# Context sanitizer
# ---------------------------------------------------------------------------
# Sentence-level assertion that the patient HAS undergone a treatment.
# Conditional phrasings ("considering focal therapy", "patient declined
# focal therapy", "if focal therapy is offered") do NOT match because they
# lack a completion verb.
# --- Treatment-fact cleaning (dedup + non-urologic / ED exclusion) ----------
_NONURO_CANCER_RE = re.compile(
    r"\blymphoma\b|\bMALT\b|gastric|\blung\b|colon|colorect|breast|pancrea|"
    r"hepatocell|esophag|melanoma|leukemia|glioma|head\s+and\s+neck|"
    r"non[\s-]?small[\s-]?cell|small[\s-]?cell|sarcoma|thyroid", re.IGNORECASE)
_URO_TX_ANCHOR_RE = re.compile(
    r"prostat|\bPSA\b|\bRRP\b|\bRALP\b|\bRARP\b|\bRP\b|bladder|renal|kidney|"
    r"nephr|urotheli|\bTURBT\b|\bADT\b|androgen|leuprolide|Lupron|Eligard|"
    r"degarelix|abiraterone|enzalutamide|apalutamide|darolutamide|brachy|"
    r"Lutetium|Pluvicto|cystectomy|penectomy|orchiectomy", re.IGNORECASE)
_ED_TX_RE = re.compile(
    r"\bEDEX\b|alprostadil|\bICI\b|intracavernosal|penile\s+inject|\bTrimix\b|"
    r"sildenafil|tadalafil|vardenafil|Viagra|Cialis|Levitra|vacuum\s+erection|"
    r"penile\s+(?:implant|prosthesis)", re.IGNORECASE)


def _canon_tx_modality(m: str) -> str:
    """Collapse treatment-modality synonyms to a canonical key so duplicates
    (e.g. 'radiation therapy' vs 'radiation', 'RRP' vs 'radical retropubic
    prostatectomy') merge."""
    s = (m or "").lower()
    if any(k in s for k in ("prostatectomy", "rrp", "ralp", "rarp", "\brp\b")):
        return "prostatectomy"
    if any(k in s for k in ("radiation", "ebrt", "imrt", "sbrt", "igrt", "xrt",
                            "brachy", "seed implant", "radiotherap")):
        return "radiation"
    if any(k in s for k in ("adt", "androgen", "leuprolide", "lupron", "eligard",
                            "goserelin", "zoladex", "degarelix", "firmagon", "orgovyx")):
        return "ADT"
    if any(k in s for k in ("abiraterone", "enzalutamide", "apalutamide",
                            "darolutamide", "arsi")):
        return "ARSI"
    if any(k in s for k in ("docetaxel", "cabazitaxel", "chemo")):
        return "chemotherapy"
    if any(k in s for k in ("lutetium", "pluvicto", "radioligand", "radium")):
        return "radioligand"
    if any(k in s for k in ("focal", "hifu", "tulsa", "cryo")):
        return "focal"
    return s.strip()


def clean_treatment_facts(facts: "PatientStatusFacts") -> "PatientStatusFacts":
    """Dedup and de-noise the treatment facts before they reach the CC/HPI/
    Assessment/Plan agents:

      - drop treatments whose context is a NON-UROLOGIC cancer (e.g. radiation
        for gastric MALT lymphoma) unless a urologic anchor is present;
      - drop erectile-dysfunction treatments (ICI / EDEX / alprostadil) from the
        cancer-treatment list;
      - collapse duplicate / re-worded events by canonical modality (so
        "radiation therapy" + "radiation" and the dozen "s/p RRP" phrasings
        become one each).
    """
    def _drop(blob: str) -> bool:
        if _ED_TX_RE.search(blob):
            return True
        if _NONURO_CANCER_RE.search(blob) and not _URO_TX_ANCHOR_RE.search(blob):
            return True
        return False

    # Clinical timeline: keep non-treatment events untouched; clean treatments.
    kept, seen = [], {}
    for e in facts.clinical_timeline:
        if not e.event_type.startswith("TREATMENT"):
            kept.append(e)
            continue
        blob = f"{e.modality} {e.detail} {getattr(e, 'source_quote', '')}"
        if _drop(blob):
            continue
        canon = _canon_tx_modality(e.modality) or (e.modality or "")
        e.modality = canon
        key = (canon, e.event_type)
        if key in seen:
            prev = seen[key]
            if (e.date_key or "9999") < (prev.date_key or "9999"):
                kept[kept.index(prev)] = e
                seen[key] = e
            continue
        seen[key] = e
        kept.append(e)
    facts.clinical_timeline = kept

    # confirmed_urologic_treatments: drop non-uro/ED, then keep ONE cleanest
    # representative per canonical modality (prefer no non-urologic-cancer term,
    # then the shortest phrasing — so 'Gastric MALT lymphoma' text doesn't
    # survive as the prostatectomy line).
    def _score(s: str):
        return (1 if _NONURO_CANCER_RE.search(s) else 0, len(s))
    by_canon: Dict[str, str] = {}
    for t in facts.confirmed_urologic_treatments:
        if _drop(t):
            continue
        canon = _canon_tx_modality(t)
        cur = by_canon.get(canon)
        if cur is None or _score(t) < _score(cur):
            by_canon[canon] = t
    facts.confirmed_urologic_treatments = list(by_canon.values())
    facts.treatment_naive = len(by_canon) == 0
    return facts


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
    r"diagnos(?:is\s+of|ed\s+with)\s+prostate\s+(?:cancer|adenocarcinoma)|"
    r"history\s+of\s+prostate\s+(?:cancer|adenocarcinoma)|"
    r"(?:treated|managed)\s+for\s+prostate\s+(?:cancer|adenocarcinoma)|"
    r"known\s+prostate\s+(?:cancer|adenocarcinoma)|"
    r"completed\s+definitive\s+(?:focal\s+therapy|radiation|treatment|brachytherapy)|"
    r"after\s+(?:definitive\s+)?(?:focal\s+therapy|focal\s+ablation|"
    r"radiation|radiation\s+therapy|EBRT|brachytherapy|HIFU|TULSA|"
    r"prostatectomy|radical\s+prostatectomy)"
    r")\b",
    re.IGNORECASE,
)

# Prostate-specific vocabulary that is anatomically impossible in a female
# patient. Bare "prostate cancer" is included here (unlike the male ABSENT
# guard, which requires an assertion form) because a female can have NO
# prostate context at all — any un-negated mention is an error.
_FEMALE_IMPOSSIBLE_RE = re.compile(
    r"\b(?:"
    r"prostate\s+(?:cancer|adenocarcinoma|carcinoma)|"
    r"prostatectomy|"
    r"PSA\s+(?:screening|surveillance|kinetics|velocity|doubling)|"
    r"(?:elevated|rising)\s+PSA|"
    r"androgen[\s\-]+deprivation|\bADT\b|"
    r"Gleason|Grade\s+Group"
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

        # Prostate cancer / PSA screening / prostatectomy / ADT are anatomically
        # impossible in a female patient — strip any un-negated positive mention
        # (a "no prostate cancer" negation is preserved by the guard).
        if not drop_reason and (facts.patient_sex or "").lower() == "female":
            fm = _FEMALE_IMPOSSIBLE_RE.search(sentence)
            if fm and not _preceded_by_negation(sentence, fm.start()):
                drop_reason = "prostate-specific assertion in a female patient"

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
    ]

    if facts.patient_sex:
        lines.append(f"PATIENT_SEX: {facts.patient_sex}")
        if facts.patient_sex == "female":
            lines.append(
                "  -> Prostate cancer, PSA screening, prostatectomy and ADT are "
                "ANATOMICALLY IMPOSSIBLE in a female patient. Never write any "
                "prostate-cancer narrative, and read PROSTATE_CANCER_STATUS below "
                "as not-applicable."
            )
        lines.append("")

    # Non-prostate GU diagnoses are frequently the PRIMARY reason for the visit
    # (renal mass, bladder tumor). List them FIRST so the CC and HPI anchor to
    # the correct organ instead of defaulting to a prostate/PSA narrative.
    if facts.other_gu_diagnoses:
        lines.append(
            "OTHER_UROLOGIC_DIAGNOSES (non-prostate — often the PRIMARY problem):"
        )
        for d in facts.other_gu_diagnoses:
            bits = [f"{d.organ}: {d.name}", f"[{d.category}]"]
            if d.grade:
                bits.append(f"grade {d.grade}")
            if d.status:
                bits.append(d.status)
            lines.append("  - " + " ".join(bits))
        lines.append(
            "  -> Center the CC and HPI on these when present. An 'indeterminate' "
            "mass is NEITHER cancer NOR benign — frame it as a mass/lesion of "
            "uncertain significance (NEVER call an unbiopsied mass 'benign'). The "
            "prostate status below is a SEPARATE, organ-specific finding: "
            "PROSTATE_CANCER_STATUS: ABSENT does NOT mean the patient is "
            "cancer-free."
        )
        lines.append("")

    lines.append(f"PROSTATE_CANCER_STATUS: {facts.cancer_status}")
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

    if facts.treatment_active_status:
        lines.append("")
        lines.append("CURRENT_TREATMENT_STATUS (per category):")
        # Stable display order for readability
        for cat in ("radiation", "prostatectomy", "focal", "adt", "chemo"):
            verdict = facts.treatment_active_status.get(cat)
            if not verdict:
                continue
            human = {
                "radiation": "Radiation",
                "prostatectomy": "Prostatectomy",
                "focal": "Focal therapy",
                "adt": "Androgen-deprivation therapy",
                "chemo": "Chemotherapy",
            }[cat]
            lines.append(f"  {human}: {verdict}")
        # ADT-specific guidance because the active/discontinued distinction
        # is what most commonly trips the LLM.
        if facts.treatment_active_status.get("adt") == "DISCONTINUED":
            lines.append(
                "    -> Frame ADT as PRIOR therapy that has been discontinued. "
                "Do NOT write 'remains on ADT', 'continues on ADT', or "
                "'currently on androgen deprivation therapy'. The correct "
                "framing is 'previously received ADT' or 'completed a course "
                "of ADT' or 'declined ADT restart in favor of monitoring' — "
                "whichever phrasing the source supports."
            )
        elif facts.treatment_active_status.get("adt") == "ACTIVE":
            lines.append(
                "    -> ADT appears to be ongoing. Confirm with the most "
                "recent injection date from the source before writing "
                "'continues on' / 'remains on'."
            )

    # Clinical phase + current active treatments + timeline + procedure
    # findings. These four sections are the structured-state foundation
    # the synthesis agents must anchor to.
    if facts.current_phase and facts.current_phase != "UNCERTAIN":
        lines.append("")
        lines.append(f"CURRENT_PHASE: {facts.current_phase}")
        from .clinical_timeline import phase_guidance
        for ln in phase_guidance(facts.current_phase).split(". "):
            ln = ln.strip()
            if ln:
                lines.append(f"  -> {ln.rstrip('.')}.")

    if facts.current_active_treatments:
        lines.append("")
        lines.append("CURRENT_ACTIVE_TREATMENTS (last-known-active per source):")
        for med in facts.current_active_treatments[:8]:
            lines.append(f"  - {med}")
        # Differentiate CHRONIC meds (continue) from FINITE oncologic courses
        # (do NOT auto-continue). The old blanket "MUST keep every med" forced
        # the Plan to write "continue Eligard/abiraterone" even when the course
        # was completed — the dominant context-blind-recommendation error once
        # both stages share these facts.
        lines.append(
            "  Note: keep CHRONIC medications (BPH alpha-blockers / 5-ARIs, "
            "supplements, etc.) on the regimen unless the source documents "
            "discontinuation. But a FINITE oncologic course — LHRH-agonist "
            "ADT (leuprolide/Eligard/goserelin/degarelix), an ARSI "
            "(abiraterone/enzalutamide/apalutamide/darolutamide), or "
            "chemotherapy — must NOT be auto-continued: consult "
            "CURRENT_TREATMENT_STATUS and CLINICAL_TIMELINE. If that course is "
            "completed/finite (e.g. 'completed a 2-year course', 'final/last "
            "dose', a fixed number of injections/cycles delivered, or "
            "CURRENT_TREATMENT_STATUS shows COMPLETED/DISCONTINUED), frame it "
            "as COMPLETED and do NOT order its continuation."
        )

    if facts.clinical_timeline:
        lines.append("")
        lines.append("CLINICAL_TIMELINE (chronologically-sorted dated events):")
        from .clinical_timeline import format_timeline_for_prompt
        for ln in format_timeline_for_prompt(facts.clinical_timeline, limit=25).split("\n"):
            lines.append(ln)
        lines.append(
            "  The HPI narrative MUST walk this timeline in order. Each treatment "
            "event the HPI mentions must trace to a TREATMENT_* entry above. Do "
            "NOT collapse multiple distinct dated events into one (e.g. an ADT "
            "course completed 04/2025 AND an ADT RESTARTED 03/2026 are TWO "
            "separate events and must both appear in the narrative)."
        )

    if facts.procedure_findings:
        lines.append("")
        lines.append("KEY_PROCEDURE_FINDINGS (often missed by synthesis — surface these):")
        from .clinical_timeline import format_procedures_for_prompt
        for ln in format_procedures_for_prompt(facts.procedure_findings, limit=12).split("\n"):
            lines.append(ln)
        lines.append(
            "  Cystoscopy, urodynamics, biopsy / pathology, TURBT, and DEXA "
            "findings drive clinical decisions. The Assessment and Plan MUST "
            "reference these by date when relevant — do not omit them."
        )

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
