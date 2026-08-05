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
    r"no\s+evidence\s+of|no\s+convincing|not\b|\bnon-)[^.\n]{0,30}$", re.I)


def _is_metastatic(text: str) -> bool:
    """True only when a metastatic mention appears NON-negated somewhere — so
    'metastatic castration-resistant …' (mCRPC) counts, but a chart whose only
    metastatic word is 'no evidence of metastatic disease' does not."""
    for m in _METASTATIC_RE.finditer(text):
        if not _META_NEG.search(text[max(0, m.start() - 35):m.start()]):
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
            st.status = "CONTINUOUS" if _is_metastatic(raw_text) else "ACTIVE"
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
    metastatic = _is_metastatic(raw_text)
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
            st.status = "INTERMITTENT_HOLDING"
            st.evidence.append("off therapy this visit")
    # 5) Explicitly intermittent, currently receiving.
    elif intermittent:
        st.status = "INTERMITTENT_ON" if active_order else "INTERMITTENT_HOLDING"
        st.evidence.append("intermittent ADT")
    # 6) Metastatic / indefinite -> continuous.
    elif metastatic and active_order:
        st.status = "CONTINUOUS"
        st.evidence.append("metastatic disease on active ADT")
    elif bool(_CONTINUE_INDEF_RE.search(raw_text)):
        st.status = "CONTINUOUS"
        st.evidence.append("indefinite/continuous ADT documented")
    elif active_order:
        st.status = "CONTINUOUS" if metastatic else "ACTIVE"
    else:
        st.status = "UNCERTAIN"

    if pending and off_now:
        st.evidence.append("NOTE: a pending ADT order exists despite off-therapy "
                           "documentation — confirm intent")

    # ---- injection-due determination (priority-ordered) ----
    vdt = _parse_visit_ymd(visit_date) or _latest_note_date(raw_text)
    if st.status == "INITIATING":
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
        if vdt is None or _cmp(vdt, nd) >= -14:   # due within a 2-week grace window
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


def render_adt_section(st: ADTStatus) -> str:
    if not st or not st.present:
        return ""
    lines = []
    lines.append(f"  Status:         {_STATUS_DISPLAY.get(st.status, st.status)}")
    reg = _regimen(st)
    if reg.strip():
        lines.append(f"  Agent:          {reg}")
    if st.start_display:
        lines.append(f"  Started:        {st.start_display}")
    if st.last_injection_display and st.last_injection_display != st.start_display:
        lines.append(f"  Last injection: {st.last_injection_display}")
    if st.oral_agents and st.agent not in st.oral_agents:
        lines.append(f"  Oral therapy:   {', '.join(st.oral_agents)}")
    lines.append(f"  This visit:     {st.determination}")
    if st.evidence:
        lines.append(f"  Basis:          {'; '.join(dict.fromkeys(st.evidence))}")
    return "\n".join(lines)
