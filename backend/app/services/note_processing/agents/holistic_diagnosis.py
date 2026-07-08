"""Holistic GU diagnosis pass (Option B).

The regex-based ``gu_diagnoses`` detector is organ-limited (renal / bladder /
prostate / a few others) and mislabels: for a penile-SCC patient it MISSES the
cancer ("Squamous cell carcinoma of penis" doesn't match its "of THE penis"
regex) and then manufactures a spurious "benign bladder pathology" from a bare
"no evidence of malignancy" line. That single wrong structured diagnosis then
becomes the HPI's primary anchor, and — because the pipeline treats structured
facts as authoritative — the LLM discards the true diagnosis it saw in the
prior HPI.

This pass fixes the *authority* split. It reads the whole chart holistically
(the way ChatGPT does) and returns the patient's GU problem list — organ,
diagnosis, stage/grade, status, key treatments — each grounded in a verbatim
source quote from the chart. It supplies the DIAGNOSIS ANCHOR only; every
checkable specific (PSA values, dates, med list) is still verified downstream
by the deterministic fact validators. So we gain ChatGPT-style diagnosis
identification for any organ without re-opening the numeric-hallucination door.

Safe-degrade: on any error, or when no LLM task config is available, or when
``VAUCDA_HOLISTIC_DX=0``, this is a no-op and the regex layer stands.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, List, Optional

from ..gu_diagnoses import GUDiagnosis

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], str]

_ORGANS = {
    "renal", "bladder", "upper_tract", "ureter", "prostate", "penile",
    "testicular", "urethral", "adrenal", "retroperitoneal", "other",
}
_MALIGNANCY = {"cancer", "indeterminate", "benign"}


def _build_prompt(context: str) -> str:
    return f"""\
You are a urologist reviewing a patient's chart to build the genitourinary (GU)
problem list for a clinic note. Read the WHOLE chart below and identify the
patient's GU diagnoses.

Output ONLY a single JSON object, no prose, no markdown:

{{
  "primary_gu_problem": "<one-line name of the dominant/active GU diagnosis>",
  "problems": [
    {{
      "organ": "<renal|bladder|upper_tract|prostate|penile|testicular|urethral|adrenal|retroperitoneal|other>",
      "diagnosis": "<diagnosis name, e.g. squamous cell carcinoma of the penis>",
      "histology": "<histology if stated, else empty>",
      "stage": "<TNM / Grade Group / stage if stated, else empty>",
      "grade": "<grade if stated, else empty>",
      "status": "<current status: s/p <treatments>, on surveillance, active, etc.>",
      "malignancy": "<cancer|indeterminate|benign>",
      "key_treatments": ["<treatment (date)>", "..."],
      "source_quote": "<a VERBATIM phrase copied from the chart that proves this diagnosis>"
    }}
  ]
}}

RULES:
- List the PRIMARY GU problem first (the dominant active diagnosis — usually the
  cancer or the documented reason for GU follow-up), then secondary problems.
- Every problem MUST include a source_quote copied VERBATIM from the chart. If
  you cannot find a supporting quote, do NOT include that problem.
- Do NOT infer prostate cancer from an elevated PSA alone. An elevated/stable
  PSA without a positive biopsy is NOT prostate cancer.
- An unbiopsied or radiographically-uncertain lesion is "indeterminate", never
  "cancer" and never "benign".
- Incidental benign findings (simple cyst, "no evidence of malignancy" on an
  unrelated study, benign prostatic hypertrophy) are secondary at most and must
  NEVER be listed as the primary problem when a cancer is present.
- Capture the actual organ. "Squamous cell carcinoma of penis" is organ
  "penile"; "urothelial carcinoma" is "bladder"; a renal mass is "renal".
- Include definitive cancer surgery in key_treatments (e.g. glansectomy,
  penectomy, inguinal lymph node dissection, nephrectomy, cystectomy, TURBT,
  prostatectomy, radiation, chemotherapy) with dates when documented.

CHART:
{context}

Output the JSON now.
"""


def _parse_json(raw: str) -> Optional[dict]:
    """Lenient parse: strip fences, take the first balanced object."""
    if not raw:
        return None
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw.strip(),
                  flags=re.IGNORECASE | re.MULTILINE).strip()
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    return None
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _is_grounded(problem: dict, note_norm: str) -> bool:
    """A problem is grounded if its source quote (or its distinctive tokens) or
    the organ/histology term actually appears in the chart. Prevents the LLM
    from inventing a diagnosis with a fabricated quote."""
    quote = _norm(problem.get("source_quote", ""))
    if quote and len(quote) >= 8 and quote in note_norm:
        return True
    # Fall back to distinctive content tokens from the quote / diagnosis.
    hay = note_norm
    for field in ("source_quote", "diagnosis", "histology"):
        val = _norm(problem.get(field, ""))
        if not val:
            continue
        toks = [t for t in re.split(r"[^a-z0-9]+", val)
                if len(t) >= 5 and t not in _STOPWORDS]
        # require at least two distinctive tokens present (or one long/organ term)
        hits = sum(1 for t in toks if t in hay)
        if hits >= 2 or any(t in hay for t in toks if len(t) >= 8):
            return True
    return False


_STOPWORDS = {
    "carcinoma", "cancer", "tumour", "tumor", "disease", "history",
    "status", "post", "patient", "malignant", "benign", "lesion",
}


def _to_category(malignancy: str) -> str:
    m = (malignancy or "").strip().lower()
    if m in ("cancer", "malignant", "malignancy"):
        return "cancer"
    if m in ("benign",):
        return "benign"
    return "indeterminate"


def extract_gu_problem_list(context: str, llm_call: LLMCallable) -> List[GUDiagnosis]:
    """Run the holistic pass and return grounded GUDiagnosis objects (primary
    first). Returns [] on any parse/grounding failure so the caller degrades to
    the regex layer."""
    try:
        raw = llm_call(_build_prompt(context))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Holistic diagnosis LLM call failed: {e}")
        return []
    obj = _parse_json(raw)
    if not obj or not isinstance(obj.get("problems"), list):
        return []
    note_norm = _norm(context)
    out: List[GUDiagnosis] = []
    for p in obj["problems"]:
        if not isinstance(p, dict):
            continue
        organ = _norm(p.get("organ", "")).replace(" ", "_")
        name = (p.get("diagnosis") or "").strip()
        if not organ or not name:
            continue
        if not _is_grounded(p, note_norm):
            logger.info(f"Holistic dx dropped (ungrounded): {name!r}")
            continue
        # Grade/stage: prefer explicit stage, then grade.
        grade = (p.get("stage") or p.get("grade") or "").strip()
        status = (p.get("status") or "").strip()
        out.append(GUDiagnosis(
            organ=organ if organ in _ORGANS else "other",
            category=_to_category(p.get("malignancy", "")),
            name=name,
            grade=grade,
            status=status,
            evidence=(p.get("source_quote") or "")[:300],
        ))
    return out


def enrich_facts_with_holistic_diagnoses(
    facts: Any,
    context: str,
    llm_task_config: Any = None,
) -> Any:
    """Replace/augment ``facts.other_gu_diagnoses`` with the holistic problem
    list so the HPI anchors on the TRUE primary diagnosis regardless of organ.

    - The holistic list becomes the authoritative anchor (primary first).
    - Regex-detected diagnoses are kept only when they add a cancer/indeterminate
      the holistic pass missed — a regex BENIGN finding never survives when a
      holistic cancer is present (kills the spurious "benign bladder pathology").
    - Definitive-cancer surgery from the holistic pass is added to
      ``confirmed_urologic_treatments`` (as "s/p ...") so the HPI can name it.

    Safe-degrade: returns ``facts`` unchanged on any failure / when disabled.
    """
    if os.environ.get("VAUCDA_HOLISTIC_DX", "1") != "1":
        return facts
    if llm_task_config is None or not context:
        return facts
    try:
        from ..llm_helper import synthesize_with_llm

        def _call(prompt: str) -> str:
            return synthesize_with_llm(
                prompt=prompt, temperature=0.0,
                task_config=llm_task_config, max_tokens=1600,
            )

        holistic = extract_gu_problem_list(context, _call)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Holistic diagnosis enrichment failed: {e}")
        return facts
    if not holistic:
        return facts

    # ``other_gu_diagnoses`` is the NON-prostate GU anchor — prostate cancer has
    # its own dedicated path (cancer_status + prostate ground truth). Drop any
    # prostate-organ holistic finding so we never (a) duplicate the prostate
    # cancer as a "secondary" entry for a prostate patient, nor (b) let an
    # incidental "raised PSA" clutter a non-prostate primary's HPI.
    non_prostate = [d for d in holistic if d.organ != "prostate"]
    if not non_prostate:
        # Holistic found no non-prostate GU primary → leave the regex layer as
        # is (e.g. a prostate patient's incidental adrenal nodule stands).
        return facts

    # Merge: the holistic list is authoritative. Keep a regex diagnosis only if
    # it adds a non-prostate organ the holistic list lacks — and never a benign
    # incidental when the holistic list already has a cancer (kills the spurious
    # "benign bladder pathology").
    holistic_organs = {d.organ for d in non_prostate}
    holistic_has_cancer = any(d.category in ("cancer", "indeterminate")
                              for d in non_prostate)
    merged: List[GUDiagnosis] = list(non_prostate)
    for d in (getattr(facts, "other_gu_diagnoses", None) or []):
        if d.organ in holistic_organs or d.organ == "prostate":
            continue
        if d.category == "benign" and holistic_has_cancer:
            continue
        merged.append(d)
    facts.other_gu_diagnoses = merged
    # Note: definitive-cancer surgery (glansectomy, ILND, etc.) is carried in
    # each diagnosis's ``status`` field, which the ground-truth block renders,
    # and is also present in the prior-HPI template — so the HPI can name it
    # without polluting the enum-constrained treatment_history array.

    try:
        logger.info(
            "Holistic dx anchor: "
            + "; ".join(f"{d.organ}:{d.name}[{d.category}]" for d in holistic))
    except Exception:  # noqa: BLE001
        pass
    return facts
