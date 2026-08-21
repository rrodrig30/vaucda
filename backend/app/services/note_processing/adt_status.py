"""Deterministic Androgen-Deprivation-Therapy (ADT) status + injection scheduler.

Standalone and LLM-FREE. For a prostate-cancer patient on an LHRH agonist / GnRH
antagonist depot, this module answers the two clinical questions a provider needs
at the visit:

  1. Is the ADT course COMPLETED, CONTINUOUS (indefinite), or INTERMITTENT
     (on-cycle vs currently holding)?
  2. Is a depot injection DUE at THIS visit — and if so, which agent, dose, route,
     and interval?

Everything is extracted deterministically from the chart (pharmacy orders,
administration records, injection-date language) so a dose can never be
hallucinated. The output renders as its own note section; the determination is
always accompanied by the EVIDENCE it rests on for provider confirmation.

Grounded in the real VistA/CPRS formats seen in the corpus, e.g.
  "LEUPROLIDE(ELIGARD) 6-MONTH INJ,SUSP,LA 45MG IM Q6MONTHS   PENDING"
  "received his last Eligard injection 07/2024 ... currently off therapy"
  "Administered Eligard 45MG SQ ... today"
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --- drug knowledge base ----------------------------------------------------
# token -> (canonical display, class). INJECTABLE classes drive the injection
# scheduler; ORAL classes (ARPI / antiandrogen / oral GnRH) are reported
# separately and never generate an "injection due".
_INJECTABLE = {"lhrh_agonist", "gnrh_antagonist", "lhrh_implant"}
_AGENTS: Dict[str, Tuple[str, str, str]] = {
    # token: (display, class, agent_family)
    "eligard":      ("Leuprolide (Eligard)", "lhrh_agonist", "leuprolide"),
    "lupron":       ("Leuprolide (Lupron)", "lhrh_agonist", "leuprolide"),
    "leuprolide":   ("Leuprolide", "lhrh_agonist", "leuprolide"),
    "zoladex":      ("Goserelin (Zoladex)", "lhrh_agonist", "goserelin"),
    "goserelin":    ("Goserelin", "lhrh_agonist", "goserelin"),
    "trelstar":     ("Triptorelin (Trelstar)", "lhrh_agonist", "triptorelin"),
    "triptorelin":  ("Triptorelin", "lhrh_agonist", "triptorelin"),
    "firmagon":     ("Degarelix (Firmagon)", "gnrh_antagonist", "degarelix"),
    "degarelix":    ("Degarelix (Firmagon)", "gnrh_antagonist", "degarelix"),
    "vantas":       ("Histrelin (Vantas)", "lhrh_implant", "histrelin"),
    "histrelin":    ("Histrelin (Vantas)", "lhrh_implant", "histrelin"),
    # oral GnRH antagonist — NOT an injection
    "orgovyx":      ("Relugolix (Orgovyx)", "gnrh_oral", "relugolix"),
    "relugolix":    ("Relugolix (Orgovyx)", "gnrh_oral", "relugolix"),
    # oral ARPIs / antiandrogens — reported separately, never an injection
    "abiraterone":  ("Abiraterone", "arpi_oral", "abiraterone"),
    "zytiga":       ("Abiraterone (Zytiga)", "arpi_oral", "abiraterone"),
    "enzalutamide": ("Enzalutamide (Xtandi)", "arpi_oral", "enzalutamide"),
    "xtandi":       ("Enzalutamide (Xtandi)", "arpi_oral", "enzalutamide"),
    "apalutamide":  ("Apalutamide (Erleada)", "arpi_oral", "apalutamide"),
    "erleada":      ("Apalutamide (Erleada)", "arpi_oral", "apalutamide"),
    "darolutamide": ("Darolutamide (Nubeqa)", "arpi_oral", "darolutamide"),
    "nubeqa":       ("Darolutamide (Nubeqa)", "arpi_oral", "darolutamide"),
    "bicalutamide": ("Bicalutamide (Casodex)", "antiandrogen_oral", "bicalutamide"),
    "casodex":      ("Bicalutamide (Casodex)", "antiandrogen_oral", "bicalutamide"),
}
# fallback (agent_family, dose_mg) -> interval months, used only when the order
# text doesn't state the interval. Dose alone is ambiguous ACROSS agents
# (leuprolide 22.5 = q3mo but triptorelin 22.5 = q6mo), so it is keyed by family.
_DOSE_INTERVAL: Dict[Tuple[str, float], int] = {
    ("leuprolide", 7.5): 1, ("leuprolide", 22.5): 3, ("leuprolide", 30.0): 4, ("leuprolide", 45.0): 6,
    ("goserelin", 3.6): 1, ("goserelin", 10.8): 3,
    ("triptorelin", 3.75): 1, ("triptorelin", 11.25): 3, ("triptorelin", 22.5): 6,
    ("degarelix", 240.0): 1, ("degarelix", 80.0): 1,   # 240 loading -> 80 monthly
    ("histrelin", 50.0): 12,                            # annual implant
}
_INJECTABLE_TOKENS = tuple(t for t, v in _AGENTS.items() if v[1] in _INJECTABLE)
_ORAL_TOKENS = tuple(t for t, v in _AGENTS.items() if v[1] not in _INJECTABLE)

_METASTATIC_RE = re.compile(
    r"\bmetasta\w*|\bmets\b|\bmHSPC\b|\bmCRPC\b|\bM1\b|osseous\s+(?:disease|metasta)|"
    r"bone\s+metasta|widespread\s+disease|visceral\s+metasta", re.I)
# Negation cue in the ~35 chars BEFORE a metastatic token — "no evidence of
# metastatic disease", "negative for metastasis", "no convincing … metastatic".
_META_NEG = re.compile(
    r"(?:\bno\b|without|negative\s+for|free\s+of|ruled?\s+out|denies|resolved|"
    r"no\s+evidence\s+of|no\s+convincing|not\b|\bnon-)[^.\n]{0,40}$", re.I)
# EQUIVOCAL / hedged metastatic mention — a radiology "may represent early nodal
# metastasis" is NOT confirmed metastatic disease and must not drive continuous
# ADT. Skipped like a negation.
_META_EQUIVOCAL = re.compile(
    r"(?:may\s+(?:represent|be)|might\s+(?:represent|be)|possibl\w+|"
    r"suspicious\s+for|concerning\s+for|worrisome\s+for|question\w+|"
    r"cannot\s+(?:be\s+)?exclud\w+|suggestive\s+of|could\s+(?:represent|be)|"
    r"equivocal|indeterminate|early\s+nodal|favor\w*|versus|vs\.?)"
    r"[^.\n]{0,40}$", re.I)


def _is_metastatic(text: str) -> bool:
    """True only when a metastatic mention appears NON-negated AND NON-equivocal —
    so 'metastatic castration-resistant …' (mCRPC) counts, but 'no evidence of
    metastatic disease' and 'may represent early nodal metastasis' do not."""
    for m in _METASTATIC_RE.finditer(text):
        ctx = text[max(0, m.start() - 40):m.start()]
        if not _META_NEG.search(ctx) and not _META_EQUIVOCAL.search(ctx):
            return True
    return False


# Metastatic disease is asserted ONLY when DOCUMENTED. Radiology reports comment
# on metastasis in nearly every study — usually to NEGATE it ("no evidence of
# metastatic disease", "bone scan (-) for metastatic disease") — and pathology
# uses "M1" as a specimen/cassette label ("cassette labeled M1", ICD "M1A.9XX0"),
# so detection is CLAUSE-scoped with aggressive negation/hedge rejection.
_STRONG_META_RE = re.compile(r"\bmHSPC\b|\bmCRPC\b", re.I)
_M1_RE = re.compile(r"\b[cp]?M1[abc]?\b", re.I)
# 'M1' counts as a STAGE only in a staging/disease clause…
_M1_STAGE_CTX = re.compile(
    r"stage|\bdisease\b|crpc|hspc|castrat|metasta|\bmets?\b|prostate\s+cancer|"
    r"high[\s-]?volume|low[\s-]?volume|oligomet", re.I)
# …and NEVER in a pathology specimen-label / ICD-code clause.
_PATH_LABEL_CTX = re.compile(
    r"cassette|specimen|submitted|labell?ed|\bblock\b|inked|microscop|gross|"
    r"M1[abc]?\.\d|M1[abc]?\s*[-–]\s*(?:prostate|left|right|apex|base|mid)", re.I)
_IMAGING_CTX_RE = re.compile(
    r"bone\s+scan|\bCT\b|CAT\s+scan|\bPSMA\b|\bPET\b|\bMRI\b|\bNaF\b|technetium|"
    r"\bscan\b|imaging|uptake|\bavid\b|sclerotic|lytic|osseous|scintigraph|"
    r"radiotracer|\blesion", re.I)
# Any negation / hedge / future-or-order framing ANYWHERE in the clause blocks the
# assertion — radiology negatives are the dominant failure mode.
_META_SENT_BLOCK = re.compile(
    r"\bno\b|\bnot\b|without|negative|no\s+evidence|no\s+convincing|exclud|"
    r"neither|unremarkable|applicable|rule\s+out|\br/o\b|\bvs\.?\b|versus|"
    r"differential|suspicious\s+for|concern|worrisome\s+for|possib|"
    r"\bmay\b|might|equivocal|indeterminate|to\s+suggest|evaluation|evaluat\w+\s+for|"
    r"work[\s-]?up|\(-\)|not\s+identified|\bif\b|should\s+(?:he|show)|"
    r"progress\w*\s+to|risk\s+of|screen|to\s+assess|potential|question|\blikely\b|"
    r"lack\s+of|chance\s+of|c(?:an|ould)\s+occur|"
    # family history, not the patient
    r"family\s+history|\bFHx\b|brothers?\s+had|father\s+had|sibling|"
    r"(?:brother|father|son|relative|paternal|maternal)",
    re.I)
# Distant-metastasis sites (bone / visceral / distant) vs REGIONAL nodal disease.
_DISTANT_SITE = re.compile(
    r"osseous|osteoblastic|sclerotic|lytic|\bbone\b|bony|skeletal|vertebr|\brib\b|"
    r"visceral|hepatic|\bliver\b|pulmonary|\blung\b|adrenal|\bbrain\b|"
    r"widespread|diffuse|\bdistant\b|innumerable", re.I)
_NODAL_ONLY = re.compile(
    r"nodal|lymph\s*node|\bLN\b|\bLAD\b|lymphadenopath|inguinal|iliac|obturator|"
    r"retroperitoneal|pelvic\s+node|\bregional\b", re.I)
# Affirmative diagnosis / positive-finding phrasing for a metastatic mention.
_META_POSITIVE = re.compile(
    r"metasta\w*\s+(?:prostate|castrat|castration|disease|cancer|lesion|deposit)|"
    r"(?:osteoblastic|osseous|sclerotic|lytic|widespread|visceral|nodal|distant|"
    r"bone|biopsy[\s-]?proven|known|treating|treatment\s+of)\s+\w{0,12}\s*metasta|"
    r"metasta\w*\s+to\s+(?:bone|the\s+bone|liver|lung|node)|"
    r"consistent\s+with\s+metasta|followup\s+of\s+metasta|for\s+metastatic\s+prostate",
    re.I)


def _clause(text: str, s: int, e: int) -> str:
    """A whitespace-NORMALIZED window around [s:e]. Clinical text is line-wrapped,
    so a sentence split on '\\n' would sever a negation ('no evidence of\\n
    metastatic disease') from the token; a flattened window keeps them together.
    The window is deliberately generous on the left (where negation/hedge sits) so
    detection errs toward NOT asserting metastasis."""
    return re.sub(r"\s+", " ", text[max(0, s - 140):min(len(text), e + 50)])


def _metastatic_documented(text: str) -> bool:
    """True only when metastatic prostate cancer is DOCUMENTED — an explicit
    metastatic stage/state (mCRPC / mHSPC / M1 stage) or an AFFIRMATIVE metastatic
    finding (imaging-corroborated or a metastatic-diagnosis phrase), with the whole
    clause free of negation/hedge/order framing. Being on ADT, a bare/negated
    'metastatic' in a radiology impression, or an 'M1' cassette label do NOT
    qualify — so a short neoadjuvant/adjuvant course is never mislabeled."""
    for m in _STRONG_META_RE.finditer(text):
        if not _META_SENT_BLOCK.search(_clause(text, m.start(), m.end())):
            return True
    for m in _M1_RE.finditer(text):
        cl = _clause(text, m.start(), m.end())
        if (_M1_STAGE_CTX.search(cl) and not _PATH_LABEL_CTX.search(cl)
                and not _META_SENT_BLOCK.search(cl)):
            return True
    for m in _METASTATIC_RE.finditer(text):
        cl = _clause(text, m.start(), m.end())
        if _META_SENT_BLOCK.search(cl):
            continue
        if not _META_POSITIVE.search(cl):
            continue
        # Regional NODAL spread (N-stage: pelvic/iliac/obturator lymphadenopathy,
        # "metastatic nodal spread") is NOT distant (M1) metastatic disease and
        # must not drive continuous ADT — a bone scan can't even see nodes.
        # Require a distant site (bone / visceral / distant) when the finding is
        # framed as nodal.
        if _NODAL_ONLY.search(cl) and not _DISTANT_SITE.search(cl):
            continue
        return True
    return False
_INTERMITTENT_RE = re.compile(r"intermittent\s+(?:adt|androgen|hormon|therapy)", re.I)
_HOLDING_RE = re.compile(
    r"currently\s+off\s+(?:therapy|adt)|off\s+therapy|hormone\s+holiday|adt\s+holiday|"
    r"holding\s+(?:adt|therapy|injection)|(?:on\s+a\s+)?treatment\s+holiday|"
    r"declined\s+(?:restart|repeat|next)|in\s+favor\s+of\s+monitoring|"
    r"favor\s+of\s+(?:active\s+)?(?:surveillance|monitoring)", re.I)
_CONTINUE_INDEF_RE = re.compile(
    r"lifelong|indefinit|continue\s+(?:adt|indefinitely)|continuous\s+(?:adt|androgen)", re.I)
_FINITE_COMPLETED_RE = re.compile(
    r"completed\s+(?:his\s+|her\s+|the\s+|a\s+|an\s+)?"
    r"(?:\d+[-\s]?(?:month|mo|year|yr)s?|planned|prescribed|adjuvant|neoadjuvant)"
    r"[^.\n]{0,40}?(?:course|adt|androgen|therapy|leuprolide|lupron|eligard)|"
    r"(?:final|last)\s+(?:dose|injection)\s+(?:of\s+)?(?:adt|eligard|lupron|leuprolide)|"
    r"(?:finished|completed)\s+(?:adt|androgen\s+deprivation)", re.I)

_AGENT_WORD = (r"eligard|lupron|leuprolide|zoladex|goserelin|degarelix|firmagon|"
               r"trelstar|triptorelin|vantas|histrelin|adt")
_INJECTION_TODAY_RE = re.compile(
    r"(?:received|administer(?:ed)?|gave|given)[^.\n]{0,30}?"
    r"(?:" + _AGENT_WORD + r")[^.\n]{0,25}?\btoday\b|"
    r"(?:" + _AGENT_WORD + r")\s+injection[-\s]*today|"
    r"(?:next|the)\s+(?:" + _AGENT_WORD + r")\s+injection\s+today", re.I)
# Explicitly NOT given today: bypass / defer / decline the injection this visit.
_DEFER_TODAY_RE = re.compile(
    r"(?:bypass|defer|decline[sd]?|hold|skip|not\s+(?:give|administer))"
    r"[^.\n]{0,30}?(?:" + _AGENT_WORD + r")\s+injection[^.\n]{0,15}?\btoday\b|"
    r"(?:defer|hold|will\s+not\s+(?:give|administer))[^.\n]{0,20}?"
    r"(?:" + _AGENT_WORD + r")\s+injection", re.I)
# Permanently stopped (toxicity / intolerance), not a planned finite course.
_DISCONTINUED_TOX_RE = re.compile(
    r"discontinu\w+[^.\n]{0,40}?(?:due\s+to|because|for|secondary\s+to)|"
    r"stopped[^.\n]{0,30}?(?:due\s+to|because|side\s+effect|intoler)|"
    r"(?:tolerated|received)[^.\n]{0,20}?\d+\s*years?[^.\n]{0,25}?discontinu", re.I)
# A SHORT / single-dose course (neoadjuvant/concurrent with radiation) — the
# course is effectively done after one or a few doses.
_SHORT_COURSE_RE = re.compile(
    r"(?:single|one|1)\s+(?:dose|injection|shot)\s+of\s+(?:adt|androgen|eligard|"
    r"lupron|leuprolide)|(?:adt|eligard|lupron|leuprolide)\s+x\s*1\b|"
    r"short\s+course\s+(?:of\s+)?adt[^.\n]{0,40}?complet|"
    r"complet\w*[^.\n]{0,25}?short\s+course\s+(?:of\s+)?adt", re.I)
# Testosterone recovering — for an ADT patient this means the drug effect is
# wearing off (the course has ended / is over).
_T_RECOVERY_RE = re.compile(
    r"testosterone[^.\n]{0,25}?(?:rising|recover\w*|returning|normaliz\w*|"
    r"back\s+to\s+normal)|(?:recover\w*|rising|returning)[^.\n]{0,20}?testosterone",
    re.I)

# A PLANNED FINITE course (defined duration or dose count) — adjuvant/neoadjuvant
# ADT with radiation, e.g. "18 months of ADT", "planned 24-month course",
# "2 years of Lupron with radiation".
_FINITE_PLANNED_RE = re.compile(
    r"(?:planned|prescribed|course\s+of|total\s+of|complete\s+a|for\s+a?|receive\s+a?)\s*"
    r"(\d{1,2})\s*[-\s]?(?:month|mo|year|yr)s?[^.\n]{0,30}?"
    r"(?:adt|androgen|eligard|lupron|leuprolide|radiation|hormon)|"
    r"(?:adt|androgen\s+deprivation|eligard|lupron|leuprolide)[^.\n]{0,25}?"
    r"(?:for|x)\s*(\d{1,2})\s*(?:month|year)s?", re.I)
# "injection 3 of 6" / "3rd of 6 injections" — X of Y course. WORD form only:
# the bare "2/6" slash form collides with dates ("injection 2/28/24" -> "2 of 28"),
# so it is deliberately excluded.
_DOSE_COUNT_RE = re.compile(
    r"(?:injection|dose|shot|cycle)\s*(?:#\s*)?(\d{1,2})\s+(?:of|out\s+of)\s+(\d{1,2})\b|"
    r"(\d{1,2})(?:st|nd|rd|th)\s+of\s+(\d{1,2})\s+(?:injection|dose|shot)s?", re.I)

# A NEW / restarted course — a prior course may be COMPLETED, but recurrence /
# rising PSA drives a fresh course, which must not be masked by the old
# completion. Bidirectional: "restart ADT for rising PSA" OR "rising PSA ...
# restart ADT".
_NEW_COURSE_RE = re.compile(
    r"(?:restart|re-?start|resume|re-?initiat\w*|re-?challenge|new\s+course|"
    r"second\s+course|another\s+course|start(?:ing)?\s+(?:a\s+)?(?:new\s+|second\s+)?"
    r"(?:course\s+of\s+)?(?:adt|androgen|eligard|lupron|leuprolide))"
    r"[^.\n]{0,45}?(?:adt|androgen|eligard|lupron|leuprolide|recurrence|"
    r"rising\s+psa|biochemical)|"
    r"(?:recurrence|rising\s+psa|biochemical\s+recurrence|psa\s+(?:rise|rising|"
    r"increas\w+))[^.\n]{0,45}?(?:restart|resume|re-?initiat\w*|start\w*|"
    r"re-?challenge)[^.\n]{0,20}?(?:adt|eligard|lupron|leuprolide|androgen)",
    re.I)

# Agent named only to say the patient is NOT getting it — must not render as
# on-therapy ("not a candidate for Eligard", "Eligard contraindicated").
_NOT_CANDIDATE_RE = re.compile(
    r"not\s+a\s+candidate\s+for\s+[^.\n]{0,15}?(?:eligard|lupron|leuprolide|adt|"
    r"androgen)|(?:eligard|lupron|leuprolide|adt|androgen\s+deprivation)"
    r"[^.\n]{0,20}?(?:contraindicated|not\s+(?:a\s+candidate|recommended|indicated))",
    re.I)
# ADT being INITIATED — a first injection scheduled/planned but not yet given.
_PLANNED_START_RE = re.compile(
    r"(?:scheduled\s+to\s+(?:receive|start|begin)|plan(?:s|ned)?\s+to\s+(?:start|"
    r"begin|initiate)|will\s+(?:start|begin|receive)|to\s+(?:start|begin|initiate|"
    r"receive|obtain)|rtc[^.\n]{0,15}?for)[^.\n]{0,25}?"
    r"(?:eligard|lupron|leuprolide|adt|androgen)|"
    r"(?:eligard|lupron|leuprolide)\s+(?:shot|injection)\s*#?\s*1\b|"
    r"(?:appointment|appt|\balm\b)[^.\n]{0,40}?(?:for\s+)?(?:eligard|lupron|leuprolide)",
    re.I)
# A scheduled first-injection date ("shot #1 on 4/27/22", "start … on <date>").
_SCHED_DATE_RE = re.compile(
    r"(?:eligard|lupron|leuprolide)\s+(?:shot|injection)\s*#?\s*1\b[^.\n]{0,12}?"
    r"(?:on\s+)?(\d{1,2})[/\-](?:(\d{1,2})[/\-])?(\d{2,4})|"
    r"(?:scheduled|start\w*|begin\w*|receive|obtain)[^.\n]{0,25}?"
    r"(?:eligard|lupron|leuprolide|adt)[^.\n]{0,15}?(?:on\s+)"
    r"(\d{1,2})[/\-](?:(\d{1,2})[/\-])?(\d{2,4})", re.I)

_DATE = r"(\d{1,2})[/\-](?:(\d{1,2})[/\-])?(\d{2,4})"
# Reject a date that is really a lab / appointment / PSA / entry date, not an
# injection date, when it sits between the anchor and the number.
_DATE_NEG = re.compile(r"lab|psa|drawn|complet|appoint|follow|entry|dictat|"
                       r"scan|imaging|biopsy|visit", re.I)


def _norm_year(y: int) -> int:
    return y + 2000 if y < 50 else (y + 1900 if y < 100 else y)


def _parse_date(mm: str, dd: Optional[str], yy: str) -> Optional[Tuple[int, int, int, str]]:
    """-> (year, month, day, display) or None. Month/year-only -> day=15, display MM/YYYY."""
    try:
        m = int(mm); y = _norm_year(int(yy))
    except (TypeError, ValueError):
        return None
    if not (1 <= m <= 12 and 1900 <= y <= 2100):
        return None
    if dd:
        d = int(dd)
        if not (1 <= d <= 31):
            return None
        return (y, m, d, f"{m:02d}/{d:02d}/{y}")
    return (y, m, 15, f"{m:02d}/{y}")


def _add_months(ymd: Tuple[int, int, int], n: int) -> Tuple[int, int, int]:
    y, m, d = ymd
    total = (y * 12 + (m - 1)) + n
    return (total // 12, total % 12 + 1, d)


@dataclass
class ADTStatus:
    present: bool = False
    agent: str = ""
    agent_family: str = ""
    dose: str = ""
    route: str = ""
    interval_months: Optional[int] = None
    interval_display: str = ""
    start_display: str = ""
    last_injection_display: str = ""
    last_injection_ymd: Optional[Tuple[int, int, int]] = None
    status: str = "UNCERTAIN"     # COMPLETED|CONTINUOUS|INTERMITTENT_ON|INTERMITTENT_HOLDING|ACTIVE|UNCERTAIN
    order_status: str = ""        # PENDING|ACTIVE|DISCONTINUED|...
    injection: str = "UNKNOWN"    # DUE|NOT_DUE|GIVEN_TODAY|ORDERED_PENDING|UNKNOWN|NOT_APPLICABLE
    next_due_display: str = ""
    determination: str = ""       # the human-facing "this visit" line
    oral_agents: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    # Course documentation (output1.txt format): Active vs Inactive, and per-course
    # Started/Completed dates. A 2nd course adds Restarted/Completed-again. A field
    # is left blank when that course has not completed (still ongoing).
    is_active: bool = False
    completed_display: str = ""
    restarted_display: str = ""
    completed_again_display: str = ""


_STATUS_DISPLAY = {
    "INITIATING": "Initiating — starting ADT (first injection scheduled/planned)",
    "COMPLETED": "Completed (finite course finished)",
    "FINITE_IN_PROGRESS": "Finite course — in progress (not yet completed)",
    "CONTINUOUS": "Continuous / indefinite",
    "INTERMITTENT_ON": "Intermittent — currently on-cycle",
    "INTERMITTENT_HOLDING": "Intermittent — currently holding (off-cycle)",
    "DISCONTINUED": "Discontinued / off therapy",
    "ACTIVE": "On ADT (continuous vs. intermittent not explicitly documented)",
    "UNCERTAIN": "Uncertain — see evidence",
}


def _pick_injectable(text: str) -> Optional[Tuple[str, str, str]]:
    """First injectable ADT agent present -> (display, class, family)."""
    low = text.lower()
    for tok in _INJECTABLE_TOKENS:
        if re.search(r"\b" + re.escape(tok) + r"\b", low):
            return _AGENTS[tok]
    return None


def _scan_order_lines(text: str, family: str):
    """Parse pharmacy ORDER lines for the agent family. Only a line that actually
    specifies a DEPOT DOSE (…MG) AND a schedule/route/status counts as an order —
    a bare med-list mention or a prose 'last injection' line is ignored, so a
    stale 'ACTIVE' cannot masquerade as a live depot order. Returns
    (dose, route, interval_months, order_status, has_order)."""
    dose = route = order_status = ""
    interval = None
    has_order = False
    fam_tokens = [t for t, v in _AGENTS.items() if v[2] == family]
    tok_re = re.compile(r"\b(?:" + "|".join(map(re.escape, fam_tokens)) + r")\b", re.I)
    for line in text.splitlines():
        if not tok_re.search(line):
            continue
        m_dose = re.search(r"(\d+(?:\.\d+)?)\s*MG\b", line, re.I)
        if not m_dose:
            continue  # not a dose/order line
        m_route = re.search(r"\b(IM|SC|SQ|SUBQ)\b", line, re.I)
        # Depot SCHEDULE only ("Q6MONTHS" / "6-MONTH INJ") — never a bare
        # "18 months of ADT" course DURATION, which is not the dosing interval.
        m_int = (re.search(r"Q\s?(\d+)\s?MONTH", line, re.I)
                 or re.search(r"(\d+)[-\s]?MONTH\s+INJ", line, re.I))
        m_stat = re.search(r"\b(PENDING|ACTIVE|DISCONTINUED|EXPIRED|HOLD|DELETED)\b", line, re.I)
        if not (m_int or m_route or m_stat):
            continue  # a real order line carries a schedule/route/status too
        has_order = True
        if not dose:
            dose = f"{float(m_dose.group(1)):g} mg"
        if m_route and not route:
            route = m_route.group(1).upper().replace("SQ", "SC").replace("SUBQ", "SC")
        if m_int and interval is None:
            interval = int(m_int.group(1))
        if m_stat:
            s = m_stat.group(1).upper()
            if s == "PENDING" or not order_status:   # a fresh PENDING order dominates
                order_status = s
    return dose, route, interval, order_status, has_order


def _collect_injection_dates(text: str) -> List[Tuple[int, int, int, str]]:
    """Dates TIGHTLY tied to an injection/ADT-start phrase (agent/'injection'
    directly adjacent to the date), most-recent last. Rejects lab / PSA /
    appointment dates that merely sit near the word 'injection'."""
    out = []
    patterns = (
        # "<agent> injection [was/in/on] <date>", "last injection <date>"
        re.compile(r"(?:" + _AGENT_WORD + r")\s+injection\s+"
                   r"(?:was\s+|in\s+|on\s+|dated\s+)?" + _DATE, re.I),
        re.compile(r"(?:last|first|next)\s+injection\s+"
                   r"(?:was\s+|in\s+|on\s+)?" + _DATE, re.I),
        # "started/initiated ADT/<agent> ... <date>"
        re.compile(r"(?:start(?:ed)?|initiat\w+|began)\s+(?:on\s+)?"
                   r"(?:adt|" + _AGENT_WORD + r")[^.\n]{0,18}?" + _DATE, re.I),
        # "<date>: started on ADT/<agent>"
        re.compile(_DATE + r"[:\s\-]{1,3}(?:start\w*|initiat\w+)[^.\n]{0,18}?"
                   r"(?:adt|" + _AGENT_WORD + r")", re.I),
    )
    for rx in patterns:
        for m in rx.finditer(text):
            if _DATE_NEG.search(m.group(0)):
                continue
            g = m.groups()
            d = _parse_date(g[-3], g[-2], g[-1])
            if d:
                out.append(d)
    return out


_MON3 = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _latest_note_date(text: str) -> Optional[Tuple[int, int, int]]:
    """Most-recent 'DATE OF NOTE: MON DD, YYYY' — the visit date when a normalized
    'VISIT DATE:' header is absent (raw VistA dumps)."""
    best = None
    for m in re.finditer(r"DATE\s+OF\s+NOTE:\s*([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})",
                         text, re.I):
        mo = _MON3.get(m.group(1)[:3].lower())
        if not mo:
            continue
        ymd = (int(m.group(3)), mo, int(m.group(2)))
        if best is None or ymd > best:
            best = ymd
    return best


def _split_courses(dates, interval_months):
    """Group injection dates into distinct ADT COURSES. A gap much larger than the
    dosing interval (> ~2 intervals, min 13 months) marks a completed course
    followed by a restart. Returns [(start_tuple, last_tuple), ...] where each
    tuple is (y, m, d, display)."""
    if not dates:
        return []
    seen = {}
    for d in dates:
        seen.setdefault((d[0], d[1], d[2]), d)
    pts = sorted(seen.values(), key=lambda d: (d[0], d[1], d[2]))
    gap = max((interval_months or 6) * 30 * 2, 400)
    courses, cur = [], [pts[0]]
    for i in range(1, len(pts)):
        if _cmp(pts[i][:3], pts[i - 1][:3]) > gap:
            courses.append((cur[0], cur[-1]))
            cur = [pts[i]]
        else:
            cur.append(pts[i])
    courses.append((cur[0], cur[-1]))
    return courses


def build_adt_status(raw_text: str, visit_date: str = "",
                     psa_data: str = "", facts=None) -> ADTStatus:
    """Deterministic ADT status + injection-due for a prostate-cancer patient."""
    st = ADTStatus()
    if not raw_text:
        return st
    inj = _pick_injectable(raw_text)
    oral = [_AGENTS[t][0] for t in _ORAL_TOKENS
            if re.search(r"\b" + re.escape(t) + r"\b", raw_text, re.I)]
    st.oral_agents = list(dict.fromkeys(oral))
    if not inj:
        # oral-only ADT (e.g. relugolix / abiraterone) — record but no injection
        if st.oral_agents:
            st.present = True
            st.agent = st.oral_agents[0]
            st.injection = "NOT_APPLICABLE"
            st.status = "CONTINUOUS" if _metastatic_documented(raw_text) else "ACTIVE"
            st.determination = "No depot injection — oral agent(s) only."
            st.evidence.append(f"oral ADT documented: {', '.join(st.oral_agents)}")
        return st

    st.present = True
    st.agent, _cls, st.agent_family = inj
    (st.dose, st.route, st.interval_months,
     st.order_status, _has_order) = _scan_order_lines(raw_text, st.agent_family)

    # interval fallback from dose KB
    if st.interval_months is None and st.dose:
        try:
            dv = float(re.sub(r"[^\d.]", "", st.dose))
            st.interval_months = _DOSE_INTERVAL.get((st.agent_family, dv))
        except ValueError:
            pass
    if st.interval_months:
        st.interval_display = f"q{st.interval_months} month{'s' if st.interval_months != 1 else ''}"

    dates = _collect_injection_dates(raw_text)
    if dates:
        dates.sort(key=lambda d: (d[0], d[1], d[2]))
        st.start_display = dates[0][3]
        last = dates[-1]
        st.last_injection_display = last[3]
        st.last_injection_ymd = (last[0], last[1], last[2])

    # ---- signals ----
    # Metastatic drives CONTINUOUS and propagates into HPI/Assessment/Plan, so it
    # must be DOCUMENTED (imaging or explicit M1/mHSPC/mCRPC), not a bare mention.
    metastatic = _metastatic_documented(raw_text)
    intermittent = bool(_INTERMITTENT_RE.search(raw_text))
    holding = bool(_HOLDING_RE.search(raw_text))
    deferred_today = bool(_DEFER_TODAY_RE.search(raw_text))
    given_today = bool(_INJECTION_TODAY_RE.search(raw_text)) and not deferred_today
    finite_done = bool(_FINITE_COMPLETED_RE.search(raw_text))
    disc_tox = bool(_DISCONTINUED_TOX_RE.search(raw_text))
    new_course = bool(_NEW_COURSE_RE.search(raw_text))
    finite_planned = _FINITE_PLANNED_RE.search(raw_text)
    m_dc = _DOSE_COUNT_RE.search(raw_text)
    dc_done = dc_progress = False
    dc_txt = ""
    if m_dc:
        nums = [int(x) for x in m_dc.groups() if x]
        if len(nums) >= 2:
            x, y = nums[0], nums[1]
            dc_done, dc_progress = x >= y, x < y
            dc_txt = f"injection {x} of {y}"
    off_now = holding or deferred_today
    pending = st.order_status == "PENDING"
    # a bare med-list 'ACTIVE' does NOT count as receiving when the note says off
    active_order = pending or given_today or (st.order_status == "ACTIVE" and not off_now)
    planned_n = None
    if finite_planned:
        planned_n = next((g for g in finite_planned.groups() if g), None)
    planned_start = bool(_PLANNED_START_RE.search(raw_text))
    not_candidate = bool(_NOT_CANDIDATE_RE.search(raw_text))
    ever_used = bool(st.last_injection_ymd) or given_today or _has_order
    n_inj = len({(d[0], d[1], d[2]) for d in dates})
    single_inj = n_inj <= 1
    # Injection recency vs the visit — a patient truly on CONTINUOUS ADT has had
    # many injections AND a recent one (~one dosing interval ago). Depot interval
    # defaults to 6 months when the order didn't specify it.
    vdt = _parse_visit_ymd(visit_date) or _latest_note_date(raw_text)
    gap_days = (-_cmp(st.last_injection_ymd, vdt)
                if (st.last_injection_ymd and vdt) else None)
    _interval_days = (st.interval_months or 6) * 30
    last_recent = gap_days is not None and gap_days <= _interval_days + 90
    # Confident CONTINUOUS: >4 documented injections and the last one is recent.
    long_term_continuous = n_inj > 4 and last_recent
    # A COMPLETED short course requires COMPLETION corroboration — an explicit
    # "completed short course", or a single/one dose alongside testosterone
    # recovery OR completed radiation (neoadjuvant/concurrent done) — plus a
    # single injection and NON-metastatic disease. Bare "single dose of ADT"
    # alone is ambiguous (could be just-started for metastatic disease), so it
    # does NOT qualify — this is why MARTINEZ (metastatic) and LAWRENCE (one
    # injection, no completion signal) must not flag.
    _short_completion = (
        bool(re.search(r"complet\w*[^.\n]{0,25}short\s+course|"
                       r"short\s+course[^.\n]{0,30}complet", raw_text, re.I))
        or (bool(_SHORT_COURSE_RE.search(raw_text)) and (
            bool(_T_RECOVERY_RE.search(raw_text))
            or bool(re.search(r"complet\w+[^.\n]{0,25}(?:xrt|radiation|\brt\b|brachy)",
                              raw_text, re.I)))))
    short_course_done = _short_completion and single_inj and not metastatic
    short_conflict = False

    # Suppress the section entirely when the injectable agent is named ONLY as a
    # non-candidate / contraindication and there is no order, injection, or
    # planned start (e.g. "not a candidate for Eligard").
    if not_candidate and not ever_used and not planned_start:
        st.present = False
        return st

    # ---- status classification (order matters) ----
    # 0) ADT being INITIATED — a first injection scheduled/planned, none yet given.
    #    Only a REAL depot order or a today-administration blocks this; a captured
    #    date in a "shot #1 scheduled on <date>" phrase is the SCHEDULED first
    #    dose, not proof of prior therapy.
    if planned_start and not (given_today or _has_order) and not off_now:
        st.status = "INITIATING"
        st.evidence.append("ADT being initiated — first injection scheduled/planned")
    # 1) A NEW / restarted course for recurrence overrides a stale completion.
    elif new_course and not off_now:
        st.evidence.append("new/restarted ADT course (recurrence / rising PSA)")
        if finite_planned or dc_progress:
            st.status = "FINITE_IN_PROGRESS"
        elif metastatic:
            st.status = "CONTINUOUS"
        else:
            st.status = "ACTIVE"
    # 1b) A completed SHORT / single-dose course (neoadjuvant/concurrent with RT).
    #     Reads as COMPLETED — but if a depot order is still PENDING it is a
    #     CONFLICT (stale order vs an intended new course): flag, don't guess.
    elif short_course_done and not off_now and not given_today:
        st.status = "COMPLETED"
        if pending:
            short_conflict = True
            st.evidence.append("completed short/single-dose ADT course, but a PENDING "
                               "order exists — confirm stale order vs. intended new course")
        else:
            st.evidence.append("completed short/single-dose ADT course "
                               "(testosterone recovering)")
    # 2) Finite course finished (and not restarting).
    elif (finite_done or dc_done) and not active_order:
        st.status = "COMPLETED"
        st.evidence.append("finite ADT course completed" + (f" ({dc_txt})" if dc_done else ""))
    # 3) Finite course still underway (adjuvant/neoadjuvant, not yet finished).
    elif (finite_planned or dc_progress) and not off_now and not metastatic:
        st.status = "FINITE_IN_PROGRESS"
        detail = dc_txt or (f"planned {planned_n}-unit course" if planned_n else "planned finite course")
        st.evidence.append(f"finite ADT course in progress ({detail})")
    # 4) Off therapy this visit — intermittent-holding vs discontinued.
    elif off_now:
        if intermittent:
            st.status = "INTERMITTENT_HOLDING"
            st.evidence.append("intermittent ADT, off-cycle / holding")
        elif disc_tox:
            st.status = "DISCONTINUED"
            st.evidence.append("ADT discontinued (intolerance / off therapy)")
        else:
            # Off therapy but NOT documented as intermittent. Intermittent ADT is
            # uncommon and is clearly marked when present, so do NOT infer an
            # intermittent 'holiday' here (which would wrongly imply a resume-when-
            # PSA-rises plan). Treat as off/stopped pending confirmation.
            st.status = "DISCONTINUED"
            st.evidence.append("off therapy this visit; not documented as intermittent "
                               "— confirm whether ADT was stopped")
    # 5) Explicitly intermittent, currently receiving.
    elif intermittent:
        st.status = "INTERMITTENT_ON" if active_order else "INTERMITTENT_HOLDING"
        st.evidence.append("intermittent ADT")
    # 6) CONTINUOUS only on solid evidence: documented metastatic disease on ADT,
    #    an explicit indefinite/continuous statement, OR a long-term pattern
    #    (>4 injections with a recent last dose). Otherwise ADT is ACTIVE but its
    #    continuous-vs-finite nature is NOT established — do not assume continuous.
    elif metastatic and active_order:
        st.status = "CONTINUOUS"
        st.evidence.append("documented metastatic disease (imaging/stage) on active ADT")
    elif bool(_CONTINUE_INDEF_RE.search(raw_text)):
        st.status = "CONTINUOUS"
        st.evidence.append("indefinite/continuous ADT documented")
    elif long_term_continuous:
        st.status = "CONTINUOUS"
        st.evidence.append(f"long-term ADT — {n_inj} injections, last dose "
                           f"~{round(gap_days / 30)} months ago")
    elif active_order:
        st.status = "ACTIVE"
        st.evidence.append("on ADT — continuous vs. finite course not established; "
                           "confirm intended duration")
    else:
        st.status = "UNCERTAIN"

    if pending and off_now:
        st.evidence.append("NOTE: a pending ADT order exists despite off-therapy "
                           "documentation — confirm intent")

    # ---- injection-due determination (priority-ordered) ----
    if short_conflict:
        st.injection = "CONFLICT"
        st.determination = ("Likely COMPLETED short ADT course (single dose / "
                            "testosterone recovering) — but a PENDING depot order "
                            "exists; CONFIRM whether the order is stale or a new "
                            "course is intended before administering.")
    elif st.status == "INITIATING":
        st.injection = "SCHEDULED"
        _sm = _SCHED_DATE_RE.search(raw_text)
        _sd = None
        if _sm:
            gs = [g for g in _sm.groups() if g]
            if len(gs) == 3:
                _sd = _parse_date(gs[0], gs[1], gs[2])
            elif len(gs) == 2:
                _sd = _parse_date(gs[0], None, gs[1])
        when = f" on {_sd[3]}" if _sd else ""
        reg = _regimen(st)
        st.determination = ("ADT being initiated — first injection scheduled" + when
                            + (f"; {reg}" if reg.strip() else "; confirm agent/dose/interval."))
    elif deferred_today:
        st.injection = "NOT_DUE"
        st.determination = f"Injection DEFERRED this visit (per chart) — {_regimen(st)}."
    elif given_today:
        st.injection = "GIVEN_TODAY"
        st.determination = f"INJECTION GIVEN TODAY — {_regimen(st)}."
    elif st.status == "COMPLETED":
        st.injection = "NOT_DUE"
        st.determination = "No injection due — finite ADT course completed."
    elif st.status == "DISCONTINUED":
        st.injection = "NOT_DUE"
        st.determination = ("No injection due — ADT discontinued (off therapy)."
                            + _psa_tail(psa_data))
    elif st.status == "INTERMITTENT_HOLDING":
        st.injection = "NOT_DUE"
        st.determination = ("No injection due — off-cycle (intermittent ADT); "
                            "resume per PSA threshold." + _psa_tail(psa_data))
    elif st.order_status == "PENDING":
        st.injection = "ORDERED_PENDING"
        st.determination = (f"INJECTION ORDERED — {_regimen(st)} "
                            f"(pharmacy order PENDING this visit).")
    elif st.last_injection_ymd and st.interval_months:
        nd = _add_months(st.last_injection_ymd, st.interval_months)
        st.next_due_display = f"{nd[1]:02d}/{nd[2]:02d}/{nd[0]}"
        if gap_days is not None and gap_days > _interval_days + 120:
            # Last dose is far past the dosing interval — ADT looks lapsed/stopped,
            # not simply "due". Do NOT suggest a dose on this basis; flag it.
            st.injection = "UNKNOWN"
            st.determination = (
                f"Last injection {st.last_injection_display} was ~{round(gap_days / 30)} "
                f"months ago (interval {st.interval_display}) — ADT appears "
                f"lapsed/discontinued; confirm status before any dose."
                + _psa_tail(psa_data))
        elif vdt is None or _cmp(vdt, nd) >= -14:   # due within a 2-week grace window
            st.injection = "DUE"
            st.determination = (f"INJECTION DUE — {_regimen(st)} "
                                f"(last {st.last_injection_display}, due {st.next_due_display}).")
        else:
            st.injection = "NOT_DUE"
            st.determination = (f"No injection due — next due {st.next_due_display} "
                                f"(last {st.last_injection_display}, {st.interval_display}).")
    else:
        st.injection = "UNKNOWN"
        miss = "interval" if not st.interval_months else "last-injection date"
        st.determination = (f"Injection timing indeterminate — {miss} not documented; "
                            f"confirm regimen ({_regimen(st)}).")

    # ---- Active/Inactive + per-course Started/Completed (output1.txt format) ----
    # ACTIVE = currently on ADT (a dose was just given/ordered/scheduled, or an
    # ongoing continuous/finite/on-cycle course whose last dose isn't lapsed).
    # A completed / discontinued / off-cycle / lapsed course is INACTIVE.
    _lapsed = "lapsed" in (st.determination or "").lower()
    _active_status = st.status in ("CONTINUOUS", "FINITE_IN_PROGRESS",
                                   "INTERMITTENT_ON", "INITIATING", "ACTIVE")
    _active_inj = st.injection in ("DUE", "ORDERED_PENDING", "GIVEN_TODAY", "SCHEDULED")
    _ongoing_inj = st.injection in ("DUE", "NOT_DUE", "ORDERED_PENDING",
                                    "GIVEN_TODAY", "SCHEDULED", "NOT_APPLICABLE")
    st.is_active = bool(not _lapsed and (_active_inj or (_active_status and _ongoing_inj)))

    courses = _split_courses(dates, st.interval_months)
    if courses:
        st.start_display = courses[0][0][3]
        if len(courses) == 1:
            # Completed only when the (single) course is finished; blank if ongoing.
            st.completed_display = "" if st.is_active else courses[0][1][3]
        else:
            # >=2 courses: course 1 is finished (a restart followed).
            st.completed_display = courses[0][1][3]
            st.restarted_display = courses[-1][0][3]
            st.completed_again_display = "" if st.is_active else courses[-1][1][3]
    return st


def _regimen(st: ADTStatus) -> str:
    bits = [st.agent]
    if st.dose:
        bits.append(st.dose)
    if st.route:
        bits.append(st.route)
    head = " ".join(bits[:2]) + (f" {st.route}" if st.route else "")
    return head + (f" {st.interval_display}" if st.interval_display else "")


def _psa_tail(psa_data: str) -> str:
    m = re.search(r"(\d+\.\d+)", psa_data or "")
    return f" (most recent PSA {m.group(1)})" if m else ""


def _parse_visit_ymd(visit_date: str) -> Optional[Tuple[int, int, int]]:
    m = re.match(r"\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})", visit_date or "")
    if not m:
        return None
    d = _parse_date(m.group(1), m.group(2), m.group(3))
    return (d[0], d[1], d[2]) if d else None


def _cmp(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    """Approx day difference a-b (months*30) — sign is what matters for the window."""
    return (a[0] - b[0]) * 360 + (a[1] - b[1]) * 30 + (a[2] - b[2])


def adt_plan_directive_from_note(stage1_note: str) -> Optional[str]:
    """Read the already-rendered (and correct) ADT section from the Stage 1 note
    and map its determination to an actionable PLAN directive. Parses the section
    rather than re-extracting, because re-running the extractor on the rendered
    note misfires (the Assessment/Plan prose says 'completed ADT/radiation')."""
    m = re.search(r"ANDROGEN DEPRIVATION THERAPY \(ADT\):\s*(.*?)"
                  r"(?=\n\s*\n|\n=|\n[A-Z][A-Z /()]{3,}:)", stage1_note or "", re.S)
    if not m:
        return None
    block = m.group(1)

    def _field(label: str) -> str:
        fm = re.search(rf"{label}:\s*(.+)", block)
        return fm.group(1).strip() if fm else ""

    det = _field("This visit")
    if not det:
        return None
    agent = (_field("Agent").split(",")[0].strip() or "ADT")
    d = det.lower()
    # NOT-due / status-specific cases FIRST — many share the "No injection due"
    # prefix, so the affirmative "injection due" check must come last and exclude
    # "no injection due".
    if "deferred" in d:
        return ("ADT depot injection deferred this visit per patient preference; "
                "continue PSA surveillance and reassess at follow-up.")
    if "given today" in d:
        return (f"{agent} administered today; schedule the next depot injection per "
                f"the dosing interval and continue PSA/testosterone monitoring.")
    if "confirm whether the order is stale" in d:
        return (f"Clarify ADT intent before dosing — a completed short course but a "
                f"pending {agent} depot order exists; confirm a stale order vs. an "
                f"intended new course.")
    if "discontinued" in d:
        return ("ADT remains discontinued; continue PSA surveillance and manage per "
                "shared decision-making.")
    if "off-cycle" in d or "intermittent" in d:
        return (f"Continue the intermittent ADT holiday ({agent}); monitor PSA and "
                f"testosterone, resume ADT per the PSA threshold.")
    if "course completed" in d:
        return "ADT course completed; monitor PSA and testosterone recovery."
    if "being initiated" in d or "first injection scheduled" in d or "initiat" in d:
        return (f"Initiate ADT ({agent}); counsel on side effects and obtain baseline "
                f"bone-health monitoring (DEXA, calcium/vitamin D).")
    if "next due" in d:
        nd = re.search(r"next due (\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{4})", det)
        return f"{agent} up to date; next depot injection due {nd.group(1) if nd else 'per interval'}."
    if "indeterminate" in d or "confirm regimen" in d or "confirm agent" in d:
        return (f"Confirm the ADT regimen ({agent}: agent/dose/interval) and the next "
                f"injection timing.")
    if "injection ordered" in d or ("injection due" in d and "no injection due" not in d):
        return (f"Administer {agent} depot today (pharmacy order pending); confirm "
                f"dose/route/interval.")
    return f"ADT — {det}"


def render_adt_section(st: ADTStatus) -> str:
    if not st or not st.present:
        return ""
    lines = []
    lines.append(f"  Status:         {'Active' if st.is_active else 'Inactive'}")
    reg = _regimen(st)
    if reg.strip():
        lines.append(f"  Agent:          {reg}")
    if st.start_display:
        lines.append(f"  Started:        {st.start_display}")
        # Completed is blank while the course is ongoing (not yet completed).
        lines.append(f"  Completed:      {st.completed_display}")
    # A second ADT course (recurrence): Restarted / Completed again.
    if st.restarted_display:
        lines.append(f"  Restarted:      {st.restarted_display}")
        lines.append(f"  Completed again: {st.completed_again_display}")
    if st.oral_agents and st.agent not in st.oral_agents:
        # A first-generation antiandrogen (bicalutamide / flutamide / nilutamide)
        # given alongside an LHRH AGONIST is transient flare protection at ADT
        # start, NOT ongoing therapy — label it so it isn't read as a maintenance
        # drug. (GnRH antagonists don't flare, so no antiandrogen accompanies them;
        # ARPIs are ongoing and shown as-is.)
        _agonist = st.agent_family in ("leuprolide", "goserelin", "triptorelin", "histrelin")
        labeled = []
        for oa in st.oral_agents:
            if _agonist and re.match(r"\s*(?:bicalutamide|flutamide|nilutamide)", oa, re.I):
                labeled.append(f"{oa} (initiation of ADT only)")
            else:
                labeled.append(oa)
        lines.append(f"  Oral therapy:   {', '.join(labeled)}")
    lines.append(f"  This visit:     {st.determination}")
    if st.evidence:
        lines.append(f"  Basis:          {'; '.join(dict.fromkeys(st.evidence))}")
    return "\n".join(lines)
