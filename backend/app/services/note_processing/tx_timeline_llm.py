"""LLM-forward treatment timeline with quote-grounded verification (VAUCDA_TX_LLM).

Why: the regex timeline is the single authority for what treatments a patient
has had, and a regex miss is converted downstream into a PROHIBITION ("DO NOT
mention radiation / salvage"). GORDEN: ten explicit "s/p salvage XRT ...
completed 3/24/2025" sentences, zero radiation events (a +/-300-char prostate-
context gate and a negation window rejected every one), so the Plan recommended
the salvage radiation he had already received.

Three layers, all gated by VAUCDA_TX_LLM=1:

1. extract_treatment_events_llm — one structured-JSON extraction call over the
   chart. Every event must carry a VERBATIM quote; deterministic verification
   requires the quote to exist in the chart, the modality word to be in the
   quote, a status cue near it, and the date to be corroborated next to the
   quote. The model cannot invent a treatment (the quote must be real) and
   cannot miss prose a regex never anticipated. Regex events are merged in as a
   second opinion that can ADD but never veto.
2. scan_treatment_mentions / unresolved_treatment_mentions — absence is never a
   prohibition: when the chart contains strong completion language for a
   modality that no event resolved, the facts block carries the quote as
   UNRESOLVED instead of forbidding the modality.
3. completed_treatment_recommendation_violations — chart-grounded output check:
   a Plan/Assessment sentence that recommends or "clarifies" a treatment the
   chart documents as completed is a violation (repaired, else dropped).
"""
import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

FLAG = "VAUCDA_TX_LLM"


def enabled() -> bool:
    return os.environ.get(FLAG, "0") == "1"


# ---- modality vocabulary ---------------------------------------------------
_MODALITY_RE: Dict[str, "re.Pattern"] = {
    "radiation": re.compile(r"\b(?:radiation|radiotherapy|XRT|EBRT|IMRT|SBRT|IGRT|VMAT|proton|RT)\b", re.I),
    "brachytherapy": re.compile(r"brachytherapy|seed\s+implant|\bLDR\b|\bHDR\b", re.I),
    "prostatectomy": re.compile(r"prostatectomy|\bRALP\b|\bRRP\b|\bRARP\b|\bRP\b", re.I),
    "adt": re.compile(r"\bADT\b|androgen[\s-]deprivation|eligard|lupron|leuprolide|degarelix|firmagon|"
                      r"zoladex|goserelin|relugolix|orgovyx|trelstar|triptorelin|hormon(?:e|al)\s+therapy", re.I),
    "arsi": re.compile(r"abiraterone|zytiga|enzalutamide|xtandi|apalutamide|erleada|darolutamide|nubeqa", re.I),
    "chemotherapy": re.compile(r"docetaxel|cabazitaxel|taxotere|jevtana|chemotherap", re.I),
    "focal": re.compile(r"\bHIFU\b|cryo(?:therapy|ablation)|\bTULSA\b|focal\s+(?:therapy|ablation)", re.I),
    "radioligand": re.compile(r"lutetium|\bLu[\s-]?177\b|pluvicto|radium[\s-]?223|xofigo", re.I),
}
_DISPLAY = {"radiation": "radiation therapy", "brachytherapy": "brachytherapy",
            "prostatectomy": "prostatectomy", "adt": "ADT", "arsi": "AR-pathway inhibitor",
            "chemotherapy": "chemotherapy", "focal": "focal therapy", "radioligand": "radioligand therapy"}
# facts.treatment_active_status category names used by the facts block
_STATUS_CAT = {"radiation": "radiation", "brachytherapy": "radiation", "prostatectomy": "prostatectomy",
               "adt": "adt", "arsi": "adt", "chemotherapy": "chemo", "focal": "focal", "radioligand": "chemo"}

_COMPLETED_CUE = re.compile(r"complet|\bs/p\b|status[\s-]post|underwent|received|finish|conclud|\bdone\b|"
                            r"\bhad\b|treated\s+with|\bafter\b|\bpost[\s-]|\bprior\b|discontinu|stopp", re.I)
_STARTED_CUE = re.compile(r"start|initiat|began|\bon\b|receiv|currently|continu|ongoing|undergoing", re.I)
_DECLINED_CUE = re.compile(r"declin|refus|elected\s+not|opted\s+(?:against|not|for\s+surveillance)|not\s+interested", re.I)
_COURSE_DONE_CUE = re.compile(
    r"complet\w*\s+(?:his|her|the|a|an)?\s*(?:\d+[-\s]?(?:month|mo|year|yr)s?|course|planned|prescribed|"
    r"adjuvant|neoadjuvant|\d+\s+(?:cycles|doses|injections))|(?:final|last)\s+(?:dose|injection|cycle)|"
    r"finished|discontinu|stopp|\boff\s+(?:adt|therapy|treatment)|\bx\s*\d+\s*(?:months|years|cycles)|"
    r"\d+\s*(?:of|/)\s*\d+\s+(?:doses|injections|cycles)|course\s+(?:was\s+)?(?:completed|finished)|"
    r"no\s+(?:further|longer)\s+(?:adt|on)", re.I)
_PLANNED_CUE = re.compile(r"plan|schedul|recommend|candidate|consider|discuss|refer|will\b|pending|upcoming|interested", re.I)

# Strong, self-contained completion phrases for the deterministic scan (layer 2/3).
_STRONG_COMPLETION_RE = re.compile(
    r"(?:\bs/p\b|status[\s-]post|completed|underwent|finished|concluded|received|treated\s+with|"
    r"history\s+of)\s+(?:(?:salvage|adjuvant|definitive|primary|external[\s-]beam|high[\s-]dose|"
    r"a\s+course\s+of|course\s+of|\d+\s+(?:sessions|fractions)\s+of)\s+){0,3}"
    r"(?P<mod>radiation(?:\s+therapy)?|radiotherapy|XRT|EBRT|IMRT|SBRT|IGRT|brachytherapy|"
    r"prostatectomy|RALP|RRP|RARP|HIFU|cryo(?:therapy|ablation)|docetaxel|chemotherapy)\b"
    r"(?:[^.\n]{0,40}?(?:completed|concluded|finished|ended)\s+(?:in\s+|on\s+)?(?P<d1>\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}))?|"
    r"(?P<mod2>XRT|radiation(?:\s+therapy)?|radiotherapy|EBRT|IMRT|SBRT|brachytherapy)\s+"
    r"(?:which\s+(?:he|she|they)\s+)?(?:completed|concluded|finished|ended)\s+(?:in\s+|on\s+)?"
    r"(?P<d2>\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}/\d{4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4})",
    re.I)
_MENTION_NEG = re.compile(r"\b(?:not|no|never|declin|refus|without|instead\s+of|rather\s+than|candidate|"
                          r"consider|recommend|discuss|plan|schedul|would|could|if\b)\b", re.I)


def _canon(text: str) -> Optional[str]:
    for mod, rx in _MODALITY_RE.items():
        if rx.search(text or ""):
            return mod
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


# ---- layer 2: deterministic strong-completion scan ----------------------------
def scan_treatment_mentions(raw_text: str) -> Dict[str, List[str]]:
    """modality -> verbatim clauses asserting the treatment was DONE
    ("s/p salvage XRT", "XRT which he completed 3/24/2025"). Negated / hypothetical
    clauses ('declined XRT', 'candidate for salvage radiation') are excluded."""
    out: Dict[str, List[str]] = {}
    for m in _STRONG_COMPLETION_RE.finditer(raw_text or ""):
        mod = _canon(m.group("mod") or m.group("mod2") or "")
        if not mod:
            continue
        s0 = max(raw_text.rfind("\n", 0, m.start()), raw_text.rfind(". ", 0, m.start())) + 1
        clause = raw_text[s0:m.start()]
        if _MENTION_NEG.search(clause[-60:]):
            continue
        quote = re.sub(r"\s+", " ", raw_text[max(0, m.start() - 25):m.end() + 25]).strip()
        lst = out.setdefault(mod, [])
        if all(_norm(quote)[:40] != _norm(q)[:40] for q in lst):
            lst.append(quote)
    return out


def unresolved_treatment_mentions(raw_text: str, timeline) -> List[str]:
    """Modalities the chart says were done but no timeline event resolved."""
    resolved = set()
    for e in timeline or []:
        if getattr(e, "event_type", "") in ("TREATMENT_COMPLETED", "TREATMENT_STARTED", "TREATMENT_RESTARTED"):
            c = _canon(f"{getattr(e, 'modality', '')} {getattr(e, 'detail', '')}")
            if c:
                resolved.add(c)
    out = []
    for mod, quotes in scan_treatment_mentions(raw_text).items():
        if mod not in resolved:
            out.append(f"{_DISPLAY[mod]}: chart states \"{quotes[0][:160]}\"")
    return out


# ---- layer 1: LLM extraction + verification -------------------------------------
_EXTRACT_SYSTEM = (
    "You are a urologic oncology chart abstractor. Read the ENTIRE chart and list every "
    "prostate-cancer-directed treatment event. Output ONLY a JSON array. Each element: "
    '{"modality": one of radiation|brachytherapy|prostatectomy|adt|arsi|chemotherapy|focal|radioligand, '
    '"agent": "<drug/procedure name as written or empty>", '
    '"status": one of completed|started|restarted|declined|planned|discontinued, '
    '"date": "YYYY-MM-DD" or "YYYY-MM" or "YYYY" or "", '
    '"quote": "<a VERBATIM sentence or clause copied exactly from the chart that states this event>", '
    '"detail": "<one short phrase: e.g. salvage to prostate bed, 7 fractions, without ADT>"}. '
    "Rules: the quote MUST be copied character-for-character from the chart (it is checked). "
    "A booked/recommended/discussed treatment is status planned, never completed. A treatment "
    "the patient declined is declined. If the same event is documented many times, report it once "
    "with the clearest quote. Do not include biopsies, imaging, or non-prostate treatments. "
    "If there are none, output []."
)


def _parse_json_array(raw: str) -> List[dict]:
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", (raw or "").strip(), flags=re.M)
    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    return obj if isinstance(obj, list) else []
                except json.JSONDecodeError:
                    return []
    return []


_MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_MON_NAME = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _date_corroborated(date: str, window: str) -> bool:
    """The claimed date's year (and month, if given) appears in the text window."""
    m = re.match(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$", date or "")
    if not m:
        return False
    y, mo = m.group(1), m.group(2)
    yy = y[2:]
    w = window.lower()
    if y not in w and not re.search(rf"\b\d{{1,2}}/(?:\d{{1,2}}/)?{yy}\b", w):
        return False
    if mo:
        mi = int(mo)
        if not (re.search(rf"\b{mi}/\d{{1,2}}/(?:{y}|{yy})\b|\b{mi:02d}/\d{{1,2}}/(?:{y}|{yy})\b|\b{mi}/(?:{y}|{yy})\b|\b{mi:02d}/(?:{y}|{yy})\b", w)
                or re.search(rf"\b{_MON_NAME[mi].lower()}[a-z]*\.?\s+(?:\d{{1,2}},?\s+)?{y}\b", w)):
            return False
    return True


def _date_display(date: str) -> str:
    m = re.match(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$", date or "")
    if not m:
        return "(undated)"
    y, mo, d = m.group(1), m.group(2), m.group(3)
    if mo and d:
        return f"{_MON_NAME[int(mo)]} {int(d):02d}, {y}"
    if mo:
        return f"{_MON_NAME[int(mo)]} {y}"
    return y


def verify_events(raw_text: str, items: List[dict]) -> Tuple[list, List[str]]:
    """Return (TimelineEvent list, rejection reasons). Every accepted event is
    quote-grounded; its date is kept only when corroborated beside the quote."""
    from .clinical_timeline import TimelineEvent
    text_n = _norm(raw_text)
    events, rejected = [], []
    seen = set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        mod = (it.get("modality") or "").strip().lower()
        status = (it.get("status") or "").strip().lower()
        quote = (it.get("quote") or "").strip()
        date = (it.get("date") or "").strip()
        if mod not in _MODALITY_RE:
            rejected.append(f"unknown modality {mod!r}")
            continue
        qn = _norm(quote)
        if len(qn) < 12 or qn not in text_n:
            rejected.append(f"{mod}/{status}: quote not found verbatim: {quote[:80]!r}")
            continue
        if not (_MODALITY_RE[mod].search(quote) or (it.get("agent") and _MODALITY_RE[mod].search(it.get("agent", "")) and _norm(it["agent"]) in qn)):
            rejected.append(f"{mod}/{status}: modality word not in quote")
            continue
        pos = text_n.find(qn)
        window = text_n[max(0, pos - 150): pos + len(qn) + 150]
        cue = {"completed": _COMPLETED_CUE, "discontinued": _COMPLETED_CUE, "started": _STARTED_CUE,
               "restarted": _STARTED_CUE, "declined": _DECLINED_CUE, "planned": _PLANNED_CUE}.get(status)
        if cue is None:
            rejected.append(f"{mod}: unknown status {status!r}")
            continue
        if not cue.search(quote) and not cue.search(window):
            rejected.append(f"{mod}/{status}: no status cue near quote")
            continue
        if status == "planned":
            continue  # recorded nowhere as history; the planned list is built separately
        # A COURSE-based therapy (ADT / ARSI / chemo) is "completed" only on
        # course-completion language; a single administration ("received first
        # Eligard injection", "Administered Eligard 45MG") is a START, never a
        # completed course.
        if status in ("completed", "discontinued") and mod in ("adt", "arsi", "chemotherapy"):
            if not _COURSE_DONE_CUE.search(quote) and not _COURSE_DONE_CUE.search(window):
                if _STARTED_CUE.search(quote) or re.search(r"administer|inject|received|given", quote, re.I):
                    status = "started"
                else:
                    rejected.append(f"{mod}/completed: single administration, not a completed course")
                    continue
        if date and not _date_corroborated(date, window):
            date = ""
        etype = {"completed": "TREATMENT_COMPLETED", "discontinued": "TREATMENT_COMPLETED",
                 "started": "TREATMENT_STARTED", "restarted": "TREATMENT_RESTARTED",
                 "declined": "TREATMENT_DECLINED"}[status]
        key = (etype, mod, date[:7])
        if key in seen:
            continue
        seen.add(key)
        agent = (it.get("agent") or "").strip()
        modality = agent if (agent and mod in ("adt", "arsi", "chemotherapy")) else _DISPLAY[mod]
        detail = (it.get("detail") or "").strip()
        events.append(TimelineEvent(
            date_key=date, date_display=_date_display(date), event_type=etype,
            modality=modality, detail=(detail or modality)[:140], source_quote=quote[:220],
            source_tier=2, assertion_class="durable" if etype in ("TREATMENT_COMPLETED", "TREATMENT_DECLINED") else "volatile"))
    return events, rejected


def extract_treatment_events_llm(raw_text: str, llm_call) -> Tuple[list, List[str], List[dict]]:
    """(verified events, rejections, planned items) from one extraction call."""
    chart = (raw_text or "")[:350000]
    prompt = _EXTRACT_SYSTEM + "\n\nCHART:\n" + chart + "\n\nJSON array:"
    raw = llm_call(prompt) or ""
    items = _parse_json_array(raw)
    events, rejected = verify_events(raw_text, items)
    planned = [it for it in items if isinstance(it, dict) and (it.get("status") or "").lower() == "planned"
               and _norm(it.get("quote", "")) in _norm(raw_text)]
    return events, rejected, planned


def _merge_timelines(llm_events: list, regex_timeline: list) -> list:
    """LLM events are primary; a regex TREATMENT event is added only when no LLM
    event of the same type+modality exists in the same month (regex can add,
    never veto). Non-treatment regex events (imaging, pathology, ...) pass through."""
    out = list(llm_events)
    have = {(e.event_type, _canon(f"{e.modality} {e.detail}"), (e.date_key or "")[:7]) for e in llm_events}
    have_mod = {(e.event_type, _canon(f"{e.modality} {e.detail}")) for e in llm_events}
    for e in regex_timeline or []:
        if not e.event_type.startswith("TREATMENT"):
            out.append(e)
            continue
        c = _canon(f"{e.modality} {e.detail}")
        if (e.event_type, c, (e.date_key or "")[:7]) in have:
            continue
        if (e.event_type, c) in have_mod and not e.date_key:
            continue
        out.append(e)
    out.sort(key=lambda e: (e.date_key or ""))
    return out


def enrich_facts_with_llm_timeline(facts, raw_text: str, llm_task_config=None):
    """Layer 1 + 2 entry point. Safe no-op when the flag is off or no LLM config."""
    if not enabled() or facts is None or not raw_text:
        return facts
    llm_events, planned = [], []
    if llm_task_config is not None:
        try:
            from .llm_helper import synthesize_with_llm

            def _call(prompt: str) -> str:
                return synthesize_with_llm(prompt, temperature=0.0, task_config=llm_task_config,
                                           max_tokens=3000)
            llm_events, rejected, planned = extract_treatment_events_llm(raw_text, _call)
            print(f"      TX timeline (LLM, verified): {len(llm_events)} event(s)"
                  + (f"; rejected {len(rejected)}" if rejected else ""))
            for r in rejected[:6]:
                print(f"        - rejected: {r}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"LLM treatment timeline skipped: {e}")
    merged = _merge_timelines(llm_events, facts.clinical_timeline or [])
    facts.clinical_timeline = merged

    # Recompute the derived facts from the merged timeline.
    tx_events = [e for e in merged if e.event_type in ("TREATMENT_COMPLETED", "TREATMENT_STARTED", "TREATMENT_RESTARTED")]
    confirmed = list(facts.confirmed_urologic_treatments or [])
    for e in tx_events:
        c = _canon(f"{e.modality} {e.detail}")
        if not c:
            continue
        if any(_MODALITY_RE[c].search(t) for t in confirmed):
            continue
        verb = "s/p" if e.event_type == "TREATMENT_COMPLETED" else "on"
        confirmed.append(f"{verb} {e.modality}" + (f" ({e.date_display})" if e.date_key else ""))
    facts.confirmed_urologic_treatments = confirmed
    facts.treatment_naive = len(confirmed) == 0
    if facts.cancer_evidence and confirmed and facts.cancer_status in ("PRESENT", "UNCERTAIN"):
        facts.cancer_status = "TREATED"
    status = dict(facts.treatment_active_status or {})
    for e in sorted(tx_events, key=lambda e: e.date_key or ""):
        c = _canon(f"{e.modality} {e.detail}")
        if not c:
            continue
        status[_STATUS_CAT[c]] = "COMPLETED" if e.event_type == "TREATMENT_COMPLETED" else "ACTIVE"
    facts.treatment_active_status = status
    if any(_canon(f"{e.modality} {e.detail}") in ("radiation", "brachytherapy") for e in tx_events):
        facts.phoenix_applicable = True
    try:
        from .clinical_timeline import classify_current_phase
        facts.current_phase = classify_current_phase(merged, cancer_known=bool(facts.cancer_evidence))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"phase reclassification skipped: {e}")
    facts.unresolved_treatment_mentions = unresolved_treatment_mentions(raw_text, merged)
    facts.planned_treatments = [
        f"{(p.get('agent') or _DISPLAY.get((p.get('modality') or '').lower(), p.get('modality')))}"
        f"{' (' + p['date'] + ')' if p.get('date') else ''}: \"{(p.get('quote') or '')[:120]}\""
        for p in planned]
    return facts


# ---- layer 3: output check ---------------------------------------------------------
_RECOMMEND_CUE = re.compile(
    r"\b(?:recommend\w*|consider\w*|offer\w*|discuss\w*|refer\w*\s+(?:to|for)|candidate\s+for|"
    r"proceed\s+with|initiat\w*|pursue|clarify\s+whether|confirm\s+whether|has\s+been\s+initiated|"
    r"remains?\s+under\s+consideration|is\s+scheduled|plan(?:ned|s)?\s+(?:for|to)|would\s+benefit|"
    r"option\s+of|eligib\w*|evaluat\w*\s+for|interest\w*\s+in)\b", re.I)
_HISTORY_CUE = re.compile(r"\bs/p\b|status[\s-]post|completed|underwent|\bprior\b|previous|\bpost[\s-]|"
                          r"following|\bafter\b|received|finished|concluded|history\s+of", re.I)
_SALVAGE_WORD = {"radiation": r"salvage|radiation|radiotherapy|XRT|EBRT|IMRT|SBRT",
                 "brachytherapy": r"brachytherapy", "prostatectomy": r"prostatectomy|RALP|RRP",
                 "focal": r"HIFU|cryo|focal", "chemotherapy": r"docetaxel|chemotherap"}


def completed_treatment_recommendation_violations(text: str, raw_text: str) -> List[str]:
    """Sentences/bullets in `text` that recommend, consider, or 'clarify' a
    treatment the chart documents as COMPLETED (strong completion phrase)."""
    if not text or not raw_text:
        return []
    done = scan_treatment_mentions(raw_text)
    viol = []
    for mod, quotes in done.items():
        word = _SALVAGE_WORD.get(mod)
        if not word:
            continue
        wrx = re.compile(word, re.I)
        for sent in re.split(r"(?<=[.!?])\s+|\n", text):
            if not wrx.search(sent) or not _RECOMMEND_CUE.search(sent):
                continue
            # the modality is named as HISTORY in this sentence -> fine
            m = wrx.search(sent)
            if _HISTORY_CUE.search(sent[max(0, m.start() - 60):m.end() + 40]):
                continue
            viol.append(f"the text recommends / considers / asks to clarify {_DISPLAY[mod]}, but the chart "
                        f"documents it as COMPLETED: \"{quotes[0][:140]}\" — state it as completed history "
                        f"with its date and do not recommend, re-offer, or question it")
            break
    return viol


def drop_completed_treatment_recommendations(text: str, raw_text: str) -> str:
    """Backstop: remove the offending sentences/bullets outright."""
    if not completed_treatment_recommendation_violations(text, raw_text):
        return text
    done = scan_treatment_mentions(raw_text)
    out_lines = []
    for line in text.split("\n"):
        keep_sents = []
        for sent in re.split(r"(?<=[.!?])\s+", line):
            bad = False
            for mod in done:
                word = _SALVAGE_WORD.get(mod)
                if not word:
                    continue
                m = re.search(word, sent, re.I)
                if m and _RECOMMEND_CUE.search(sent) and not _HISTORY_CUE.search(sent[max(0, m.start() - 60):m.end() + 40]):
                    bad = True
                    break
            if not bad:
                keep_sents.append(sent)
        kept = " ".join(keep_sents).strip()
        if kept and not re.fullmatch(r"[-*•]\s*", kept):
            out_lines.append(kept)
    return "\n".join(out_lines)


# ---- cross-section PSA-absence claims ------------------------------------------
_PSA_ABSENCE_RE = re.compile(
    r"\bno\s+(?:subsequent|further|additional|later|recent|interval)\s+PSA\b|"
    r"\bPSA\s+(?:has|have|was|were)\s+not\s+been\s+(?:reassessed|rechecked|repeated|measured|obtained|drawn)|"
    r"\bno\s+PSA\s+(?:values?|results?|levels?)\s+(?:are\s+|is\s+|were\s+)?(?:documented|available|on\s+file|recorded)|"
    r"\bPSA\s+status\s+has\s+not\s+been\s+reassessed|\bhas\s+not\s+been\s+reassessed\s+since\b", re.I)


def drop_unsupported_psa_absence_claims(hpi: str, psa_data: str) -> str:
    """Drop HPI sentences claiming no (subsequent) PSA exists when the note's
    own PSA curve carries values (GORDEN: 'no subsequent PSA values are
    documented' twelve lines above a 12-value PSA curve)."""
    if not hpi or not psa_data or not re.search(r"\d+\.\d+", psa_data):
        return hpi
    kept = [s for s in re.split(r"(?<=[.!?])\s+", hpi.strip()) if not _PSA_ABSENCE_RE.search(s)]
    out = " ".join(kept).strip()
    return out if out else hpi
