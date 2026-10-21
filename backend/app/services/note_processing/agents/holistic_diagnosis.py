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
  "cancer" and never "benign". EXCEPTION: a mass is "cancer" even WITHOUT a
  tissue biopsy when the chart documents a radiographically diagnostic feature —
  it invades a vein / the IVC / has tumor thrombus, OR it is named as an
  established diagnosis ("known RCC", "history of renal cell carcinoma"), OR it
  is being treated with definitive cancer therapy for that mass (SBRT,
  nephrectomy, ablation, cryoablation). Benign masses do not invade veins and
  are not given definitive oncologic treatment.
- READ THE RADIOLOGY CHARACTERIZATION. An adrenal nodule the report describes as
  a myelolipoma, a lipid-rich/lipid-poor adenoma, showing washout, <10 HU,
  "benign", or stable over time is BENIGN and does NOT require follow-up if
  biochemically inactive — classify it "benign"; do NOT call it "of uncertain
  significance". The same for a simple renal cyst (Bosniak I/II) and a stable
  old non-specific nodule.
- Do NOT list a purely benign incidental finding (benign adrenal adenoma /
  myelolipoma, simple cyst, old stable nodule) as a problem at all unless it is
  the documented reason for THIS visit. Omit it entirely rather than inventing a
  surveillance problem for it.
- Incidental benign findings must NEVER be the primary problem when a cancer is
  present. The PRIMARY problem is the active disease — the cancer or the
  documented reason for the tumor-clinic follow-up. List it first.
- Capture the actual organ. "Squamous cell carcinoma of penis" is organ
  "penile"; "urothelial carcinoma" is "bladder"; a renal mass is "renal".
- SYMPTOMS ARE NOT DIAGNOSES. Hematuria, LUTS, nocturia, frequency, urgency,
  incontinence, dysuria, pain, retention, and erectile dysfunction are symptoms.
  Do NOT list a symptom as a problem unless it is the documented reason for
  THIS visit AND its workup is still incomplete. A presenting symptom whose
  workup was negative or that led to a cancer diagnosis (e.g. the hematuria
  that prompted the PSA/biopsy) is part of that cancer's history — omit it.
  Never label a symptom 'indeterminate etiology' or 'under surveillance'.
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


_SYMPTOM_ONLY_RE = re.compile(
    r"hematuria|\bLUTS\b|lower\s+urinary\s+tract\s+symptom|nocturia|frequency|urgency|incontinence|"
    r"dysuria|\bpain\b|retention|erectile|\bED\b|voiding|dribbl|hesitancy|weak\s+stream", re.I)
_LESION_WORD_RE = re.compile(
    r"lesion|mass|tumou?r|carcinoma|cancer|neoplasm|stricture|stone|calcul|cyst|hydronephrosis|"
    r"diverticul|fistula|varicocele|hydrocele", re.I)


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


_ORGAN_MALIGNANCY_RE = {
    "bladder": re.compile(r"urothelial\s+(?:cell\s+)?carcinoma|transitional\s+cell\s+carcinoma|\bTCC\b|"
                          r"carcinoma\s+in\s+situ|\bCIS\b|\bNMIBC\b|\bMIBC\b|"
                          r"(?:high|low)[\s-]grade\s+(?:papillary\s+)?urothelial|bladder\s+(?:cancer|carcinoma|malignancy)", re.I),
    "renal": re.compile(r"renal\s+cell\s+carcinoma|\bRCC\b|clear[\s-]cell|papillary\s+renal|chromophobe|"
                        r"kidney\s+cancer|renal\s+(?:cancer|malignancy)", re.I),
    "upper_tract": re.compile(r"upper[\s-]tract\s+urothelial|\bUTUC\b|ureteral\s+(?:cancer|carcinoma)", re.I),
    "testicular": re.compile(r"seminoma|germ[\s-]cell\s+tumou?r|\bNSGCT\b|embryonal|teratoma|testicular\s+cancer", re.I),
    "penile": re.compile(r"squamous\s+cell\s+carcinoma|penile\s+(?:cancer|carcinoma)", re.I),
    "adrenal": re.compile(r"adrenocortical\s+carcinoma|pheochromocytoma|adrenal\s+(?:cancer|carcinoma)", re.I),
    "urethral": re.compile(r"urethral\s+(?:cancer|carcinoma)", re.I),
}
_HEDGE_RE = re.compile(
    r"concern(?:ing|ed)?\s+for|suspicious|suspect\w*|\br/o\b|rule\s+out|question\s+of|possibl\w+|"
    r"probabl\w+|likely|unverified|pre-?op(?:erative)?\s+diag|post-?op(?:erative)?\s+diag|screen\w*|"
    r"risk\s+(?:of|for)|\bversus\b|\bvs\.?\b|cannot\s+(?:be\s+)?exclude|not\s+excluded|no\s+evidence\s+of|"
    r"negative\s+for|without\s+evidence|atypical|\bif\b|would|could|workup\s+for|evaluat\w+\s+for|"
    r"family\s+history|\bfh\b|\bFHx\b", re.I)


# Tissue evidence: the malignancy named in a pathology DIAGNOSIS, an explicit
# biopsy-/pathology-proven statement, or an extirpative operation for that
# cancer (a specimen was necessarily examined).
_TISSUE_CUE_RE = re.compile(
    r"biopsy[\s-]+(?:proven|confirmed|showed|showing|revealed|demonstrat\w+)|"
    r"patholog\w*\s+(?:proven|confirmed|showed|showing|revealed|demonstrat\w+|consistent)|"
    r"histolog\w*\s+(?:confirmed|proven|showed|showing|revealed|consistent)|"
    r"final\s+patholog|surgical\s+patholog|\bdiagnosis\s*:|\bs/p\s+(?:(?:left|right|bilateral|radical|partial|"
    r"laparoscopic|robotic|open|simple|total|cytoreductive)\s+){0,3}"
    r"(?:nephrectomy|nephroureterectomy|cystectomy|cystoprostatectomy|orchiectomy|penectomy|glansectomy)|"
    r"(?:nephrectomy|nephroureterectomy|cystectomy|orchiectomy|penectomy|glansectomy)\s+(?:for|revealed|showed|with)",
    re.I)


def malignancy_corroborated(organ: str, chart_text: str) -> bool:
    """True only with TISSUE evidence of a malignancy of `organ`: the term in a
    pathology report's diagnosis (deterministic extraction), or in a non-hedged
    clause that also carries a biopsy-/pathology-proven cue or an extirpative
    operation for that cancer. Imaging ('concerning for RCC'), a tumor-board
    presumption ('significant for RCC'), a surgery booking ('Bladder Cancer
    (Unverified)'), cytology atypia, or an ablation without biopsy never
    corroborate a cancer label (CARO: RFA of an unbiopsied 1.2 cm renal mass)."""
    rx = _ORGAN_MALIGNANCY_RE.get((organ or "").lower())
    if not rx or not chart_text:
        return False
    try:
        from ..extractors import extract_pathology
        path = extract_pathology(chart_text) or ""
    except Exception:  # noqa: BLE001
        path = ""
    for m in rx.finditer(path):
        s0 = max(path.rfind("\n", 0, m.start()), path.rfind(". ", 0, m.start())) + 1
        s1 = path.find("\n", m.end())
        clause = path[s0:(s1 if s1 != -1 else len(path))]
        if not re.search(r"negative\s+for|no\s+evidence|benign|atypical|suspicious|concern|r/o|rule\s+out", clause, re.I):
            return True
    for m in rx.finditer(chart_text):
        s0 = max(chart_text.rfind("\n", 0, m.start()), chart_text.rfind(". ", 0, m.start())) + 1
        s1 = chart_text.find("\n", m.end())
        clause = re.sub(r"\s+", " ", chart_text[max(s0, m.start() - 160):(s1 if s1 != -1 else len(chart_text))][:320])
        if _HEDGE_RE.search(clause):
            continue
        if _TISSUE_CUE_RE.search(clause):
            return True
        # Inside a pathology report's DIAGNOSIS block (header within the preceding
        # lines): the term is a histologic diagnosis even if the extractor did
        # not render this report.
        lookback = chart_text[max(0, m.start() - 450):m.start()]
        if re.search(r"(?i)\bDIAGNOSIS\s*:|Microscopic\s+Exam|FINAL\s+(?:PATHOLOGIC\s+)?DIAGNOSIS", lookback) \
                and not re.search(r"(?i)pre-?op|post-?op|clinical\s+diag|provisional", lookback[-120:]):
            return True
    return False


def enrich_facts_with_holistic_diagnoses(
    facts: Any,
    context: str,
    llm_task_config: Any = None,
    chart_text: str = "",
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
    # A holistic 'cancer' must be corroborated by non-hedged chart text; a
    # problem-list 'Neoplasm of uncertain behavior' + a TURBT booking labelled
    # 'Bladder Cancer (Unverified)' became 'T2 urothelial carcinoma' in the
    # Assessment (CARO) while the biopsy read benign. Downgrade to indeterminate.
    if chart_text:
        for d in non_prostate:
            if d.category == "cancer" and not malignancy_corroborated(d.organ, chart_text):
                logger.info(f"Holistic dx downgraded cancer->indeterminate (uncorroborated): {d.organ}:{d.name!r}")
                d.category = "indeterminate"
                if not re.search(r"uncertain|indeterminate|lesion|mass", d.name or "", re.I):
                    d.name = f"{d.name} (histology not established)"
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

    # Deterministic-cancer override. The regex confirmation gate fires "cancer"
    # only on STRONG radiographic signals (venous/IVC invasion + tumor thrombus,
    # "Known/Hx of RCC") that a mass is malignant even without a tissue biopsy.
    # The holistic LLM's blanket "unbiopsied -> indeterminate" rule wrongly
    # downgrades those. When the deterministic gate confirmed CANCER for an organ
    # the holistic called indeterminate, trust the strict gate and upgrade it in
    # place (keep the holistic's richer status/stage; adopt its confirmed name if
    # the holistic left a generic "mass"/"lesion"). Fixes RIVERA: 8.5 cm RCC
    # invading the right renal vein, on SBRT, downgraded to "renal mass of
    # uncertain significance".
    _regex_cancer = {
        d.organ: d
        for d in (getattr(facts, "other_gu_diagnoses", None) or [])
        if d.category == "cancer"
    }
    _GENERIC_NAME = re.compile(r"\b(mass|lesion|nodule)\b", re.I)
    for d in non_prostate:
        if d.organ in _regex_cancer:
            rd = _regex_cancer[d.organ]
            if d.category == "indeterminate":
                d.category = "cancer"
            # Adopt the deterministic gate's specific histology name ("renal cell
            # carcinoma") when the holistic pass left a generic "right renal mass"
            # — the CC/HPI should name the confirmed cancer, not a bland "mass".
            if (rd.name and not _GENERIC_NAME.search(rd.name)
                    and (not d.name or _GENERIC_NAME.search(d.name))):
                d.name = rd.name

    # Deterministic symptom guard (ALEJANDRO: 'gross hematuria of indeterminate
    # etiology' became problem #1 above a metastatic prostate cancer). A
    # symptom-only entry (no lesion / mass / tumour / carcinoma / stricture /
    # stone / cyst word) is dropped when the patient has an established cancer
    # (prostate cancer_status PRESENT/TREATED or a holistic cancer) — it is that
    # cancer's history, not a separate problem to anchor the note on.
    _has_cancer = (getattr(facts, "cancer_status", "") in ("PRESENT", "TREATED")
                   or any(d.category == "cancer" for d in non_prostate))
    if _has_cancer:
        kept = []
        for d in non_prostate:
            if d.category != "cancer" and _SYMPTOM_ONLY_RE.search(d.name or "") \
                    and not _LESION_WORD_RE.search(f"{d.name} {d.status}"):
                logger.info(f"Holistic dx dropped (symptom, cancer present): {d.name!r}")
                continue
            kept.append(d)
        non_prostate = kept
        if not non_prostate:
            # Keep deterministic cancers AND indeterminate lesions (a Bosniak 2F
            # mass awaiting follow-up MRI must not vanish because the holistic
            # LLM omitted it on one run — MARTINEZ). With prostate cancer
            # primary they render as SECONDARY findings only.
            facts.other_gu_diagnoses = [
                d for d in (getattr(facts, "other_gu_diagnoses", None) or [])
                if d.category in ("cancer", "indeterminate")]
            return facts
        holistic_organs = {d.organ for d in non_prostate}

    merged: List[GUDiagnosis] = list(non_prostate)
    for d in (getattr(facts, "other_gu_diagnoses", None) or []):
        if d.organ in holistic_organs or d.organ == "prostate":
            continue
        # LLM-forward: the holistic pass read the WHOLE chart (incl. radiology).
        # Only re-inject a regex CANCER it may have missed (a safety net) — a
        # regex indeterminate/benign the holistic deliberately omitted (a benign
        # adrenal myelolipoma, an old non-specific nodule, a simple cyst) stays
        # omitted, so it can't resurface as "of uncertain significance" and
        # hijack the CC over the patient's actual cancer.
        if d.category == "cancer":
            merged.append(d)
        elif d.category == "indeterminate" and getattr(facts, "cancer_status", "") in ("PRESENT", "TREATED"):
            # Prostate cancer is the primary problem, so a deterministic
            # indeterminate lesion is a SECONDARY finding that still needs its
            # follow-up — re-inject it (it cannot hijack the CC here).
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
