"""Assessment + Plan composer: ONE whole-chart LLM pass returning JSON.

The model is the attending urologist. It reads the chart, leans on the most
recent clinician HPI/Assessment/Plan as the backbone, treats the deterministic
tables and the ADT scheduler verdict as data, and grounds guideline-based
recommendations on the GraphRAG passages it is given (citing them). The output
is structured so the deterministic assembler controls headers, numbering and
the time template, and the verifier can check sentence by sentence.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .context import ChartContext

logger = logging.getLogger(__name__)
LLMCallable = Callable[[str], str]

_MAX_PROBLEMS = 7
_MAX_BULLETS = 7


def _schema() -> str:
    return """\
Return ONLY a JSON object of this exact shape (no markdown, no commentary):
{
  "assessment": "<5-9 sentence clinical narrative, one paragraph>",
  "problems": [
    {
      "title": "<problem name as a clinician writes it, e.g. 'Prostate adenocarcinoma, Grade Group 3, intermediate unfavorable risk, on ADT'>",
      "bullets": ["<plan item>", "..."],
      "guideline_basis": ["<[query label] or AUA/NCCN statement the bullets rest on, or empty>"]
    }
  ],
  "open_questions": ["<anything the chart leaves unresolved that the clinician should confirm at the visit>"]
}"""


def _instructions(ctx: ChartContext) -> str:
    return f"""\
You are the attending urologist writing YOUR OWN Assessment and Plan for today's clinic
visit ({ctx.visit_date}) after reading this patient's entire chart. Write the way a
senior urologic oncologist thinks: what the disease is, what has been done and WHY, what
the current therapy is and how the patient is responding, what was decided by other
services, what is new today, and what you will do next and why.

HOW TO READ THE CHART
- The most recent UROLOGY notes (section "MOST RECENT CLINICIAN NOTES") are the backbone:
  they are the clinician's own synthesis. Carry their reasoning forward and update it with
  interval events; do not re-derive the history from fragments.
- The sections under "AUTHORITATIVE DATA" (PSA curve, PSADT, ADT schedule, pathology, labs,
  imaging, medications, functional status) are verified tables. Every date, PSA value,
  lab value, Gleason score and stage you write MUST come from them or from the chart
  verbatim. Never invent, round, or infer a value or a date.
- "VERIFIED FACTS" is a deterministic ledger with ABSOLUTE RULES. Obey its rules. If it
  conflicts with the chart narrative on a point of fact, prefer the chart passage you can
  quote, and list the conflict under "open_questions".
- The ADT SCHEDULER VERDICT is arithmetic on documented injection dates and is
  authoritative for depot timing: reflect its action in Problem #1 exactly.
- The LIFE EXPECTANCY / FUNCTIONAL STATUS block is deterministic: use its figures as given
  (never recompute a Schonberg index or life expectancy; never invent a Charlson score).

ASSESSMENT (one paragraph, 5-9 sentences)
1. Who and why today (age, diagnosis with grade/stage/NCCN risk EXACTLY as the chart states it).
2. The treatment path AND the reasons it was chosen: every treatment constraint the chart
   documents (a course stopped early and why, surgical candidacy, declined options,
   intolerances) belongs here — they explain the current therapy.
3. Current therapy and response with dated PSA / testosterone values.
4. Interval events and decisions by other services (oncology, radiation oncology, biopsies
   attempted or failed, new imaging, new symptoms, new diagnoses) that bear on urologic care.
5. Today's symptoms (what is reported and denied).
6. The life-expectancy / functional-status framing and what it implies for intensity of care.
7. Secondary or incidental findings in ONE closing clause, never earlier.

PLAN (problems in order of clinical importance; {_MAX_PROBLEMS} max, {_MAX_BULLETS} bullets max each)
- Problem #1 is the active cancer or the documented reason for this visit. Its bullets carry
  the therapy decision, the ADT scheduler action if any, the surveillance schedule with the
  next dated check, and the treatment rationale in one bullet.
- Weight by importance: an incidental or surveillance-only finding (an indeterminate renal
  lesion, a pulmonary nodule) gets at most two bullets and comes after the active problems.
- Include non-urologic problems ONLY when they change urologic management (anticoagulation
  before a procedure, diabetes affecting wound or ADT risk, bowel disease limiting radiation)
  and say how; list them last.
- Guideline-based recommendations must rest on the GUIDELINE PASSAGES provided; name the
  passage's [query label] or the guideline body (AUA / NCCN / EAU) in guideline_basis. A
  recommendation with no retrieved basis is allowed but must be your clinical judgment,
  stated as such ("clinical judgment").
- Never write a negative recommendation ("no X indicated", "do not administer") for an
  option no urologist would consider; omit it instead.
- Never re-offer, re-refer for, or question a treatment the chart documents as completed,
  declined or ruled out by a constraint.
- A radiation course the chart says was stopped early is not "completed" and not
  "definitive": no Phoenix criteria, no "post-radiation surveillance" framing. After a
  radical prostatectomy the recurrence definition is PSA-based, not Phoenix.
- Do not restate laboratory tables; cite only the values that drive a decision.
- Do not create a separate "elevated PSA" problem when prostate cancer is established.
- Use dates as MM/DD/YYYY; write values exactly as the tables show them.

{_schema()}"""


def build_prompt(ctx: ChartContext) -> str:
    parts = [_instructions(ctx), ""]
    if ctx.patient_banner:
        parts += ["=== PATIENT ===", ctx.patient_banner, ""]
    if ctx.prior_clinician_notes:
        parts += ["=== MOST RECENT CLINICIAN NOTES (newest first; the backbone) ===",
                  ctx.prior_clinician_notes, ""]
    tables = ctx.tables_text()
    if tables:
        parts += ["=== AUTHORITATIVE DATA (deterministic tables from the chart) ===", tables, ""]
    if ctx.adt_directive:
        parts += ["=== ADT SCHEDULER VERDICT (arithmetic on documented injections — authoritative) ===",
                  ctx.adt_directive, ""]
    elif ctx.adt_constraint:
        parts += ["=== ADT (historical) ===", ctx.adt_constraint, ""]
    if ctx.life_expectancy_block:
        parts += ["=== LIFE EXPECTANCY / FUNCTIONAL STATUS (deterministic) ===", ctx.life_expectancy_block, ""]
    if ctx.facts_block:
        parts += ["=== VERIFIED FACTS (deterministic ledger; obey its ABSOLUTE RULES) ===", ctx.facts_block, ""]
    if ctx.guidelines:
        parts += ["=== GUIDELINE PASSAGES (GraphRAG retrieval; cite by [query label]) ===", ctx.guidelines[:12_000], ""]
    parts += ["=== FULL CHART (normalized) ===", ctx.chart, "", "Write the JSON now:"]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Parsing / rendering
# ---------------------------------------------------------------------------
def parse_json_object(raw: str) -> Optional[dict]:
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I)
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except json.JSONDecodeError:
                    break
    try:
        return json.loads(s[start:])
    except Exception:  # noqa: BLE001
        return None


def _clean(s: Any) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return re.sub(r"\*\*|__", "", s)


def render_plan(problems: List[dict]) -> str:
    lines: List[str] = []
    n = 0
    for p in (problems or [])[:_MAX_PROBLEMS]:
        if not isinstance(p, dict):
            continue
        title = _clean(p.get("title"))
        bullets = [_clean(b) for b in (p.get("bullets") or []) if _clean(b)]
        if not title or not bullets:
            continue
        n += 1
        lines.append("")
        lines.append(f"PROBLEM #{n}: {title}")
        for b in bullets[:_MAX_BULLETS]:
            b = re.sub(r"^[-*•]\s*", "", b)
            lines.append(f"- {b}")
    return "\n".join(lines).strip("\n")


def compose_assessment_plan(ctx: ChartContext, llm_call: LLMCallable, max_retry: int = 1
                            ) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """Return (assessment, plan_text, audit) or None when the model gave nothing
    usable after retries (the caller falls back to the legacy agents)."""
    prompt = build_prompt(ctx)
    audit: Dict[str, Any] = {"attempts": 0, "prompt_chars": len(prompt)}
    obj = None
    for attempt in range(max_retry + 1):
        audit["attempts"] = attempt + 1
        raw = (llm_call(prompt) or "").strip()
        audit["raw_chars"] = len(raw)
        obj = parse_json_object(raw)
        if obj and _clean(obj.get("assessment")) and obj.get("problems"):
            break
        logger.warning("A&P composer: unusable output on attempt %d (%d chars)", attempt + 1, len(raw))
        obj = None
    if not obj:
        return None
    assessment = _clean(obj.get("assessment"))
    plan = render_plan(obj.get("problems") or [])
    if len(assessment) < 200 or not plan:
        return None
    audit["open_questions"] = [_clean(q) for q in (obj.get("open_questions") or [])][:6]
    audit["guideline_basis"] = {
        _clean(p.get("title"))[:60]: [_clean(g) for g in (p.get("guideline_basis") or [])]
        for p in obj.get("problems") or [] if isinstance(p, dict)}
    return assessment, plan, audit
