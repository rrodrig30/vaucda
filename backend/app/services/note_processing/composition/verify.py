"""Verifier: deterministic DISCREPANCY detection + quote-grounded LLM adjudication.

Answer to "if the deterministic portion finds something the LLM missed, how do
we know it was right?": it does not get to be right on its own. Each check
emits a discrepancy (the draft sentence, what the check found, and where the
check looked). ONE adjudication call shows the adjudicator the chart, the data
tables and every discrepancy; for each it must answer keep / fix / remove and
cite the chart passage that settles it. A fix or removal is applied only when
that quote exists verbatim (whitespace- and case-insensitively) in the chart or
the tables. Anything else is left as written and listed under VERIFICATION
NOTES for the provider. Hard cap on applied edits per section.

The two arithmetic authorities (the ADT scheduler verdict and the data tables)
are not adjudicated — they are enforced by the existing deterministic
post-processors, which is where the user wants them.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .context import ChartContext, date_tuples
from .ap_compose import parse_json_object

logger = logging.getLogger(__name__)
LLMCallable = Callable[[str], str]

_MAX_EDITS = 6


@dataclass
class Discrepancy:
    kind: str
    unit: str                       # the exact sentence or bullet in the draft
    finding: str                    # what the check found
    looked_in: str = ""             # where the check looked


@dataclass
class VerifyResult:
    text: str
    applied: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    discrepancies: List[Discrepancy] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
def _units(text: str, is_plan: bool) -> List[str]:
    if is_plan:
        return [l for l in text.split("\n") if l.lstrip().startswith("-")]
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip()) if s.strip()]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# ---------------------------------------------------------------------------
# Deterministic checks (each returns Discrepancy objects, never edits)
# ---------------------------------------------------------------------------
_PSA_NUM_RE = re.compile(
    r"(?i)\bPSA\b(?:\s+(?:of|was|is|at|to|level|value|rose\s+to|fell\s+to|declined\s+to|dropped\s+to|remains?|remained))?"
    r"\s*(?:\(|:)?\s*(\d+\.\d+|\d+)(?!\s*(?:/|,?\s*20\d\d|\s*%|\s*(?:months?|weeks?|years?|cores?|fractions?|points?)))\s*(?:ng/mL)?"
    r"|(\d+\.\d+)\s*ng/mL")
_YEAR_LIKE_RE = re.compile(r"^(?:19|20)\d{2}$")
_TX_CLAIM_RE = re.compile(
    r"(?i)\b(completed|underwent|s/p|status post|received|finished)\s+(?:definitive\s+|salvage\s+|adjuvant\s+|a\s+course\s+of\s+)?"
    r"(?:external\s+beam\s+)?(radiation(?:\s+therapy)?|radiotherapy|IMRT|EBRT|XRT|SBRT|brachytherapy|"
    r"(?:radical\s+)?prostatectomy|RALP|RARP|RRP|androgen\s+deprivation(?:\s+therapy)?|ADT|leuprolide|Eligard|Lupron)")
_PHOENIX_RE = re.compile(r"(?i)\bphoenix\b|nadir\s*\+\s*2")
_NAIVE_RE = re.compile(r"(?i)treatment[\s-]naive|no\s+prior\s+(?:prostate[\s-]cancer\s+)?treatment")
_RISK_RE = re.compile(r"(?i)\b(very[\s-]low|low|favou?rable[\s-]intermediate|unfavou?rable[\s-]intermediate|"
                      r"intermediate[\s-](?:un)?favou?rable|intermediate|high|very[\s-]high)[\s-]risk\b")


def _visit_tuple(ctx: ChartContext):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", ctx.visit_date or "")
    return (int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


def check_dates(units: List[str], ctx: ChartContext) -> List[Discrepancy]:
    out = []
    vt = _visit_tuple(ctx)
    for u in units:
        for (y, m, d) in date_tuples(u):
            if d is None and m is None:
                continue                      # bare years are too loose to police
            # A PLANNED date after the visit (next depot, next labs, RTC) is
            # schedule arithmetic the clinician asked for, not a chart fact.
            if vt and (y, m, d or 1) > vt:
                continue
            if (y, m, d) not in ctx.chart_dates and (y, m, None) not in ctx.chart_dates:
                shown = f"{m:02d}/{d:02d}/{y}" if d else f"{m:02d}/{y}"
                out.append(Discrepancy("DATE_NOT_IN_CHART", u, f"the date {shown} does not appear in the chart or the data tables",
                                       "chart + Stage 1 tables"))
                break
    return out


def check_psa_values(units: List[str], ctx: ChartContext) -> List[Discrepancy]:
    if not ctx.psa_values:
        return []
    out = []
    vals = ctx.psa_values
    for u in units:
        for m in _PSA_NUM_RE.finditer(u):
            v = m.group(1) or m.group(2)
            if not v or _YEAR_LIKE_RE.match(v):
                continue
            # a number that is part of a date ("rose to 2.83 ng/mL on 01/03/2025" is fine;
            # "May 2023" is not a PSA) — skip when preceded by a month name
            pre = u[max(0, m.start() - 12):m.start()].lower()
            if re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*$", pre):
                continue
            try:
                f = float(v)
            except ValueError:
                continue
            if f > 10000 or any(abs(f - x) < 0.0051 for x in vals):
                continue
            # thresholds like nadir+2 are derived values: allow any x+2.0
            if any(abs(f - (x + 2.0)) < 0.0051 for x in vals):
                continue
            out.append(Discrepancy("PSA_NOT_IN_CURVE", u, f"PSA value {v} is not on the PSA CURVE", "PSA CURVE"))
            break
    return out


def check_treatment_claims(units: List[str], ctx: ChartContext, facts: Any) -> List[Discrepancy]:
    out = []
    tas = (getattr(facts, "treatment_active_status", {}) or {}) if facts is not None else {}
    naive = bool(getattr(facts, "treatment_naive", False)) if facts is not None else False
    confirmed = list(getattr(facts, "confirmed_urologic_treatments", []) or []) if facts is not None else []
    for u in units:
        for m in _TX_CLAIM_RE.finditer(u):
            verb, mod = m.group(1).lower(), m.group(2).lower()
            if re.search(r"radiat|imrt|ebrt|xrt|sbrt|radiother", mod) and tas.get("radiation") == "INCOMPLETE" \
                    and verb in ("completed", "finished", "s/p", "status post"):
                out.append(Discrepancy("RADIATION_INCOMPLETE", u,
                                       "the facts ledger marks the radiation course INCOMPLETE (stopped early), but the draft says it was completed",
                                       "TREATMENT CONSTRAINTS"))
                break
            if re.search(r"androgen|adt|leuprolide|eligard|lupron", mod) and tas.get("adt") == "ACTIVE" \
                    and verb in ("completed", "finished"):
                out.append(Discrepancy("ADT_ONGOING", u,
                                       "the ADT scheduler says the course is ONGOING, but the draft says it was completed",
                                       "ADT SCHEDULER VERDICT"))
                break
        if naive and not confirmed and _TX_CLAIM_RE.search(u):
            out.append(Discrepancy("TREATED_BUT_NAIVE", u,
                                   "the facts ledger finds no confirmed prostate-cancer treatment, but the draft asserts one",
                                   "confirmed treatments"))
        if _NAIVE_RE.search(u) and confirmed:
            out.append(Discrepancy("NAIVE_BUT_TREATED", u,
                                   "the facts ledger lists confirmed treatments, but the draft calls the patient treatment-naive",
                                   "confirmed treatments"))
    return out


def check_phoenix(units: List[str], ctx: ChartContext, facts: Any) -> List[Discrepancy]:
    if facts is None:
        return []
    tas = getattr(facts, "treatment_active_status", {}) or {}
    rp = tas.get("prostatectomy") == "COMPLETED"
    inc = tas.get("radiation") == "INCOMPLETE"
    phoenix_ok = bool(getattr(facts, "phoenix_applicable", False))
    if phoenix_ok and not rp and not inc:
        return []
    out = []
    for u in units:
        if _PHOENIX_RE.search(u):
            why = ("after radical prostatectomy recurrence is PSA-based, not Phoenix" if rp else
                   "the radiation course was not completed, so Phoenix (nadir + 2) does not apply" if inc else
                   "no definitive radiation course is documented")
            out.append(Discrepancy("PHOENIX_INAPPLICABLE", u, why, "facts ledger"))
    return out


def check_risk_category(units: List[str], ctx: ChartContext, facts: Any) -> List[Discrepancy]:
    risk = (getattr(facts, "nccn_risk", "") or "").strip().lower() if facts is not None else ""
    if not risk:
        return []
    out = []
    for u in units:
        for m in _RISK_RE.finditer(u):
            said = m.group(1).lower().replace("-", " ")
            said = re.sub(r"\s+", " ", said)
            if said.startswith(risk) or risk.startswith(said) and said != "intermediate" or said == risk:
                continue
            out.append(Discrepancy("RISK_CATEGORY", u,
                                   f"the chart states the NCCN risk category as '{risk}', the draft says '{said}'",
                                   "chart (NCCN risk statement)"))
            break
    return out


def run_checks(text: str, ctx: ChartContext, facts: Any, is_plan: bool) -> List[Discrepancy]:
    units = _units(text, is_plan)
    found: List[Discrepancy] = []
    found += check_dates(units, ctx)
    found += check_psa_values(units, ctx)
    found += check_treatment_claims(units, ctx, facts)
    found += check_phoenix(units, ctx, facts)
    found += check_risk_category(units, ctx, facts)
    # one discrepancy per unit (the first wins) keeps the adjudication focused
    seen, out = set(), []
    for d in found:
        if d.unit in seen:
            continue
        seen.add(d.unit)
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Adjudication
# ---------------------------------------------------------------------------
def _adjudication_prompt(discrepancies: List[Discrepancy], ctx: ChartContext, section: str) -> str:
    items = "\n".join(
        f'{i + 1}. [{d.kind}] DRAFT: "{d.unit}"\n   CHECK FOUND: {d.finding} (looked in: {d.looked_in})'
        for i, d in enumerate(discrepancies))
    return f"""\
You are verifying a clinic-note {section} against the patient's chart. A deterministic check
flagged each item below. The check is NOT authoritative — it may be wrong. Decide each item
from the chart and the data tables ONLY.

For every item answer with:
  "verdict": "keep"   — the draft is supported by the chart as written
            "fix"    — the draft is wrong; supply "replacement" (the corrected sentence/bullet,
                        same scope as the draft unit, nothing else changed)
            "remove" — the draft asserts something the chart does not support at all
  "quote":  the EXACT chart or table passage (verbatim, 8-40 words) that settles the item. A
            fix/remove without a verbatim quote will be ignored.
  "reason": one short clause.

Return ONLY a JSON array: [{{"id": 1, "verdict": "...", "quote": "...", "replacement": "...", "reason": "..."}}, ...]

ITEMS
{items}

=== DATA TABLES ===
{ctx.tables_text(cap=10_000)}

=== ADT SCHEDULER VERDICT ===
{ctx.adt_directive or ctx.adt_constraint or "(none)"}

=== CHART ===
{ctx.chart[:70_000]}
"""


def _quote_in_chart(quote: str, ctx: ChartContext) -> bool:
    q = _norm(quote)
    if len(q) < 12:
        return False
    hay = _norm(ctx.chart) + " " + _norm(ctx.tables_text(cap=200_000)) + " " + _norm(ctx.adt_directive)
    return q in hay


def verify_section(text: str, ctx: ChartContext, facts: Any, llm_call: Optional[LLMCallable],
                   is_plan: bool, section: str) -> VerifyResult:
    res = VerifyResult(text=text)
    if not text:
        return res
    res.discrepancies = run_checks(text, ctx, facts, is_plan)
    if not res.discrepancies:
        return res
    if llm_call is None:
        res.notes = [f"{d.kind}: {d.finding} — \"{d.unit[:120]}\"" for d in res.discrepancies]
        return res
    try:
        raw = (llm_call(_adjudication_prompt(res.discrepancies, ctx, section)) or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
        start = raw.find("[")
        verdicts = json.loads(raw[start:raw.rfind("]") + 1]) if start >= 0 else []
    except Exception as e:  # noqa: BLE001
        logger.warning("adjudication failed (%s); flagging only", e)
        verdicts = []
    by_id = {int(v.get("id", 0)): v for v in verdicts if isinstance(v, dict)}
    out = text
    edits = 0
    for i, d in enumerate(res.discrepancies):
        v = by_id.get(i + 1)
        if not v:
            res.notes.append(f"{d.kind}: {d.finding} — \"{d.unit[:120]}\" (not adjudicated)")
            continue
        verdict = str(v.get("verdict", "")).lower().strip()
        quote = str(v.get("quote", "")).strip()
        if verdict == "keep":
            continue
        if verdict in ("fix", "remove") and _quote_in_chart(quote, ctx) and edits < _MAX_EDITS and d.unit in out:
            if verdict == "remove":
                out = out.replace(d.unit, "", 1)
                res.applied.append(f"removed: \"{d.unit[:100]}\" (chart: \"{quote[:80]}\")")
            else:
                rep = re.sub(r"\s+", " ", str(v.get("replacement", "")).strip())
                if not rep:
                    res.notes.append(f"{d.kind}: fix without replacement — \"{d.unit[:120]}\"")
                    continue
                if is_plan and not rep.lstrip().startswith("-"):
                    rep = "- " + rep.lstrip("-• ").strip()
                out = out.replace(d.unit, rep, 1)
                res.applied.append(f"fixed: \"{d.unit[:80]}\" -> \"{rep[:80]}\" (chart: \"{quote[:80]}\")")
            edits += 1
        else:
            reason = str(v.get("reason", "")).strip()
            res.notes.append(f"{d.kind}: {d.finding} — \"{d.unit[:120]}\""
                             + (f" (adjudicator: {verdict}, quote not found in chart)" if verdict in ("fix", "remove")
                                else f" (adjudicator: {verdict or 'no verdict'}{': ' + reason if reason else ''})"))
    if not is_plan:
        out = re.sub(r"\s{2,}", " ", out).strip()
    else:
        out = re.sub(r"\n{3,}", "\n\n", out).strip("\n")
    res.text = out
    return res


def render_verification_notes(results: List[VerifyResult], open_questions: Optional[List[str]] = None) -> str:
    notes = [n for r in results for n in r.notes]
    oq = [q for q in (open_questions or []) if q]
    if not notes and not oq:
        return ""
    lines = ["VERIFICATION NOTES (for the provider; not part of the note):"]
    for n in notes[:8]:
        lines.append(f"- {n}")
    for q in oq[:4]:
        lines.append(f"- Open question: {q}")
    return "\n".join(lines)
