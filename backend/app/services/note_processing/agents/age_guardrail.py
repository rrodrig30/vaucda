"""
Age & life-expectancy guardrail for the Assessment and Plan agents.

Deterministically classifies the patient as Standard / Limited /
Very-Limited life expectancy from age + PMH + frailty markers in the
Stage-1 note, and emits a block listing what is INDICATED, what is
DISCOURAGED, and what is CONTRAINDICATED for the typical cancer-
screening, mpMRI, and biopsy decisions that the LLM otherwise applies
uniformly to every patient regardless of age.

Rationale: the Plan agent has been recommending routine PSA screening,
mpMRI prostate, and prostate biopsy in elderly and/or frail men citing
"AUA guidelines" — when AUA's actual Early-Detection language says the
opposite (screening generally discontinued at 70-75 in average health;
biopsy generally not offered when life expectancy <10 years absent
symptomatic or management-changing PSA progression).

This module produces a directive block the synthesis prompts can quote
verbatim. The block names the AUA language and tells the LLM what to
suppress, rather than relying on RAG keyword retrieval that pulls in
the wrong AUA chunk.
"""

from __future__ import annotations

import re
from typing import Optional


# Comorbidity markers that, when present, substantially reduce life
# expectancy regardless of age. Each entry is (regex, label).
_LIFE_LIMITING_FLAGS = (
    # Only a NAMED non-prostate metastatic cancer counts. A bare
    # "metastatic" matched metastatic PROSTATE cancer phrased with
    # intervening words ("metastatic castration-resistant prostate cancer")
    # or a prostate met SITE ("metastatic ... neoplasm to liver"),
    # falsely flagging a second malignancy and seeding hallucinated
    # "very limited life expectancy due to metastatic non-prostate cancer".
    (re.compile(
        r"\bmetastatic\s+(?:lung|pancrea\w+|colorectal|colon|gastric|"
        r"hepatocellular|esophageal|renal\s+cell|urothelial|bladder|"
        r"breast|melanoma|lymphoma|leukemia|small[-\s]cell|"
        r"non[-\s]small[-\s]cell|cholangio\w+|ovarian|"
        r"head\s+and\s+neck)\b",
        re.IGNORECASE,
    ), "metastatic non-prostate malignancy"),
    (re.compile(
        r"\b(?:stage\s+iv|advanced)\s+(?:lung|pancreatic|liver|"
        r"gastric|hepatocellular|colorectal|esophageal)\s+(?:cancer|"
        r"carcinoma|malignancy)\b",
        re.IGNORECASE,
    ), "advanced non-prostate cancer"),
    (re.compile(r"\bhospice\b", re.IGNORECASE), "hospice care"),
    (re.compile(r"\bpalliative\s+care\b", re.IGNORECASE), "palliative care"),
    (re.compile(
        r"\b(?:NYHA\s+(?:III|IV)|class\s+(?:III|IV)\s+heart\s+failure|"
        r"advanced\s+(?:congestive\s+)?heart\s+failure|severe\s+CHF)\b",
        re.IGNORECASE,
    ), "advanced heart failure"),
    (re.compile(r"\bejection\s+fraction\s+(?:of\s+)?(?:<|less\s+than\s+)?\s*"
                r"(\d{1,2})\s*%?\b", re.IGNORECASE), "low EF (≤30%)"),
    (re.compile(
        r"\b(?:dialysis|ESRD|end[-\s]stage\s+renal|eGFR\s+(?:<|less\s+than)\s*15)\b",
        re.IGNORECASE,
    ), "end-stage renal disease / dialysis"),
    (re.compile(
        r"\b(?:severe\s+COPD|home\s+(?:O2|oxygen)|"
        r"on\s+continuous\s+oxygen|GOLD\s+(?:III|IV))\b",
        re.IGNORECASE,
    ), "severe COPD / home oxygen"),
    (re.compile(
        r"\b(?:advanced\s+dementia|severe\s+dementia|"
        r"end[-\s]stage\s+dementia)\b",
        re.IGNORECASE,
    ), "advanced dementia"),
    (re.compile(
        r"\b(?:Child[-\s]Pugh\s+C|cirrhosis\s+with\s+(?:ascites|"
        r"encephalopathy|varices)|decompensated\s+liver\s+disease|"
        r"hepatic\s+failure)\b",
        re.IGNORECASE,
    ), "decompensated liver disease"),
    (re.compile(
        r"\b(?:CFS\s*[≥>=]?\s*[6-9]|clinical\s+frailty\s+score\s+"
        r"(?:of\s+)?[6-9]|frailty\s+(?:score\s+)?(?:6|7|8|9))\b",
        re.IGNORECASE,
    ), "moderate-to-severe frailty (CFS ≥6)"),
    (re.compile(
        r"\b(?:bed[-\s]bound|bedbound|bedridden|"
        r"wheelchair[-\s]bound|wheelchairbound|"
        r"nursing\s+home|long[-\s]term\s+care\s+facility|"
        r"skilled\s+nursing\s+facility)\b",
        re.IGNORECASE,
    ), "limited functional status"),
    (re.compile(r"\bECOG\s+(?:performance\s+status\s+)?(?:of\s+)?[3-4]\b",
                re.IGNORECASE), "poor performance status (ECOG 3-4)"),
)


# Subset of the flags above that are TERMINAL (life expectancy typically well
# under 5 years) — these force VERY_LIMITED regardless of the actuarial number,
# because a health-quartile multiplier under-weights an end-stage condition.
_TERMINAL_FLAG_LABELS = frozenset({
    "metastatic non-prostate malignancy",
    "advanced non-prostate cancer",
    "hospice care",
    "palliative care",
    "advanced dementia",
})

# Positive evidence of excellent health — only then do we apply the "healthiest
# quartile" (x1.5) uplift to the SSA life expectancy. Absence of severe flags
# alone is NOT enough (over-estimating life expectancy drives over-treatment).
_EXCELLENT_HEALTH = re.compile(
    r"no\s+(?:significant\s+|major\s+|other\s+)?(?:comorbidit|chronic\s+"
    r"(?:medical\s+)?(?:problems|conditions|illness))|excellent\s+health|"
    r"very\s+active|physically\s+active|robust|no\s+(?:significant\s+)?PMH\b|"
    r"no\s+past\s+medical\s+history|otherwise\s+healthy|healthy\s+"
    r"(?:man|male|adult|woman|female)|ECOG\s+(?:performance\s+status\s+)?0\b",
    re.IGNORECASE,
)


# Sentinel "do NOT use to discourage workup" markers. If any of these
# appear in the stage-1 note, the patient has prostate cancer already
# and is not in the screening population — guardrail rules about PSA
# SCREENING and biopsy-for-detection do not apply. Treatment-related
# workup (e.g., PSMA PET for known PC) is still allowed.
_KNOWN_PC_MARKERS = (
    re.compile(r"\bprostate\s+adenocarcinoma\b", re.IGNORECASE),
    re.compile(r"\b(?:Gleason|Grade\s+Group)\b", re.IGNORECASE),
    re.compile(r"\bprostate\s+cancer\b(?!\s+screening)", re.IGNORECASE),
    re.compile(r"\bs/p\s+(?:RP|prostatectomy|EBRT|brachytherapy)\b",
               re.IGNORECASE),
    re.compile(r"\bbiochemical\s+recurrence\b", re.IGNORECASE),
    re.compile(r"\bcastrat[ei]\s+resistant\b", re.IGNORECASE),
)


def _parse_age(stage1_note: str) -> Optional[int]:
    """Pull the patient's age out of the Stage-1 note header."""
    if not stage1_note:
        return None
    # Standard renderer emits "Age: NN" in the patient banner line.
    m = re.search(r"\bAge\s*[:=]\s*(\d{1,3})\b", stage1_note, re.IGNORECASE)
    if m:
        try:
            v = int(m.group(1))
            if 18 <= v <= 110:
                return v
        except ValueError:
            pass
    # Fallback: "NN-year-old" phrasing in the HPI.
    m = re.search(r"\b(\d{1,3})[-\s]year[-\s]old\b", stage1_note,
                  re.IGNORECASE)
    if m:
        try:
            v = int(m.group(1))
            if 18 <= v <= 110:
                return v
        except ValueError:
            pass
    return None


def _detect_life_limiting(stage1_note: str) -> list:
    """Return the list of labels for life-limiting comorbidities found in
    the Stage-1 note."""
    if not stage1_note:
        return []
    found = []
    for pat, label in _LIFE_LIMITING_FLAGS:
        m = pat.search(stage1_note)
        if not m:
            continue
        # Special handling for ejection fraction — only flag if ≤30%.
        if label == "low EF (≤30%)":
            try:
                ef = int(m.group(1))
            except (IndexError, ValueError):
                continue
            if ef > 30:
                continue
        if label not in found:
            found.append(label)
    return found


def _has_known_prostate_cancer(stage1_note: str) -> bool:
    """Suppress the screening-specific rules when the patient already has
    prostate cancer — workup language is different."""
    if not stage1_note:
        return False
    return any(p.search(stage1_note) for p in _KNOWN_PC_MARKERS)


def classify_life_expectancy(stage1_note: str) -> dict:
    """Bucket the patient as STANDARD / LIMITED / VERY_LIMITED based on
    age + comorbidities. Returns a dict the prompt block uses.

    Buckets (heuristic, intentionally conservative — flags more patients
    for shared-decision-making than the formal Charlson/CFS thresholds
    would, because over-recommending elderly cancer workup is the
    clinical-harm direction):

      VERY_LIMITED: ≥85, OR any one life-limiting comorbidity at ≥75,
                    OR ≥2 life-limiting comorbidities at any age.
                    ⇒ <5-year life expectancy assumption.
      LIMITED:      75-84 without life-limiting comorbidities,
                    OR 70-74 with ≥1 life-limiting comorbidity.
                    ⇒ 5-10 year life expectancy; SDM required for
                       cancer-detection workup.
      STANDARD:     <70 (any), or 70-74 without comorbidities.
                    ⇒ standard AUA early-detection options apply.
    """
    age = _parse_age(stage1_note)
    flags = _detect_life_limiting(stage1_note)
    n_flags = len(flags)

    # Primary driver: NCCN/AUA SSA actuarial life expectancy adjusted by
    # comorbidity health quartile (replaces the coarse Charlson 10-yr survival).
    from .life_expectancy import (estimate_life_expectancy, parse_sex,
                                   format_life_expectancy, compute_lee_index,
                                   compute_schonberg_index)
    sex = parse_sex(stage1_note)
    excellent = bool(_EXCELLENT_HEALTH.search(stage1_note or "")) and n_flags == 0
    le = estimate_life_expectancy(age, sex, n_flags, excellent_health=excellent)
    # Lee 4-yr-mortality index — computed only when functional status is documented.
    lee = compute_lee_index(stage1_note, age, sex)
    # Schonberg 9-yr-mortality index — PREFERRED (closest to 10-yr survival) when
    # its self-report inputs are documented; else the SSA estimate governs.
    schon = compute_schonberg_index(stage1_note, age, sex)

    if age is None or le is None:
        bucket = "UNKNOWN"
    else:
        if schon is not None:
            # Schonberg's own strata: 0-7 low, 8-13 medium, 14+ high mortality.
            if schon["score"] <= 7:
                bucket = "STANDARD"
            elif schon["score"] <= 13:
                bucket = "LIMITED"
            else:
                bucket = "VERY_LIMITED"
        elif le["years"] >= 10:
            # Bucket from the SSA estimated years: >=10 STANDARD, 5-10 LIMITED, <5.
            # (Replaces the old blunt age-only cutoffs — a robust 80-year-old is
            # no longer auto-LIMITED; the actuarial estimate decides.)
            bucket = "STANDARD"
        elif le["years"] >= 5:
            bucket = "LIMITED"
        else:
            bucket = "VERY_LIMITED"
        # Severe-end safety overrides the actuarial quartile can under-weight:
        #  - a TERMINAL condition (hospice/palliative/metastatic non-prostate
        #    cancer/advanced dementia) -> VERY_LIMITED at any age;
        #  - >=2 severe flags (catastrophic burden) -> VERY_LIMITED;
        #  - a severe flag in an elderly (>=75) patient -> VERY_LIMITED.
        _terminal = any(f in _TERMINAL_FLAG_LABELS for f in flags)
        if _terminal or n_flags >= 2 or (n_flags >= 1 and age >= 75):
            bucket = "VERY_LIMITED"
        # Lee index is DOWNGRADE-ONLY: a high 4-yr mortality (score >=10 -> >=42%)
        # reliably means limited life expectancy, so pull the bucket down at least
        # one level. A low Lee score never upgrades (4-yr mortality can't confirm
        # 10-yr survival) — the SSA estimate governs the upside.
        if lee and lee["score"] >= 14:            # ~64% 4-yr mortality
            bucket = "VERY_LIMITED"
        elif lee and lee["score"] >= 10 and bucket == "STANDARD":  # ~42%
            bucket = "LIMITED"

    # Honest summary: when a severe/terminal override forced VERY_LIMITED but the
    # actuarial number is >=5 yr, the table under-weights the end-stage condition
    # — so don't present that inflated figure; state the limiting driver instead.
    le_summary = format_life_expectancy(le)
    disp_years = le["years"] if le else None
    if le and bucket == "VERY_LIMITED" and le["years"] >= 5:
        drivers = ", ".join(flags) if flags else f"age {age}"
        le_summary = (f"Life expectancy markedly limited (<5 years) given {drivers}; "
                      f"the actuarial table under-weights end-stage disease.")
        disp_years = None

    lee_summary = ""
    if lee:
        drivers = ", ".join(k for k in lee["contributors"] if k not in ("male",))
        lee_summary = (f"Lee index {lee['score']} pts (~{lee['mortality_4yr_band']} "
                       f"4-year mortality"
                       + (f"; {drivers}" if drivers else "") + ").")

    schon_summary = ""
    if schon:
        drivers = ", ".join(k for k in schon["contributors"] if k not in ("male",))
        schon_summary = (
            f"Schonberg index {schon['score']} pts: ~{schon['survival_9yr_pct']}% "
            f"9-year survival (~{schon['mortality_9yr_pct']}% 9-year mortality"
            + (f"; {drivers}" if drivers else "") + ").")

    # Primary survival figure the synthesis prompt should cite: Schonberg when
    # available (validated 9-yr, closest to 10-yr survival), else the SSA estimate.
    primary_summary = schon_summary or le_summary

    return {
        "bucket": bucket,
        "age": age,
        "sex": sex,
        "life_limiting_flags": flags,
        "life_expectancy": le,                       # SSA-based estimate dict (or None)
        "life_expectancy_years": disp_years,
        "life_expectancy_summary": le_summary,
        "lee_index": lee,                            # Lee 4-yr index dict (or None)
        "lee_index_summary": lee_summary,
        "schonberg_index": schon,                    # Schonberg 9-yr index (or None)
        "schonberg_index_summary": schon_summary,
        "primary_survival_summary": primary_summary,
        "known_prostate_cancer": _has_known_prostate_cancer(stage1_note),
    }


_ECOG_RE = re.compile(r"ECOG\s*(?:PS|performance\s+status)?\s*[:=]?\s*([0-4])\b", re.I)
_ANY_CANCER_RE = re.compile(
    r"\bcancer\b|carcinoma|malignan|adenocarcinoma|lymphoma|leukemia|sarcoma|"
    r"\bGleason\b|Grade\s+Group", re.IGNORECASE)
_IADL_INDEPENDENT = re.compile(
    r"independent\s+(?:in|with)\s+(?:all\s+)?(?:IADL|instrumental)", re.IGNORECASE)
_AMBULATES_OK = re.compile(
    r"no\s+difficulty\s+walking|ambulat\w*\s+(?:independently|without\s+"
    r"(?:difficulty|assist)|well)|walks?\s+without\s+(?:difficulty|assist)", re.IGNORECASE)


def build_functional_status_section(stage1_note: str) -> str:
    """Structured intake that (a) captures the Schonberg self-report inputs
    (perceived health, IADL status, ambulation) and (b) prompts ECOG performance
    status for cancer patients — so both the life-expectancy estimate and ECOG
    are documented. Extracted values are shown when present; otherwise a labeled
    fill-in template prompts the provider. Rendered only when relevant (cancer,
    age >=65, or functional status already documented)."""
    if not stage1_note:
        return ""
    from .life_expectancy import (_SCHON_PERCEIVED, _SCHON_IADL,
                                  _SCHON_DIFF_QUARTER_MILE, _LEE_FUNC_DOCUMENTED,
                                  _difficulty_present)
    info = classify_life_expectancy(stage1_note)
    age = info.get("age")
    is_cancer = bool(_ANY_CANCER_RE.search(stage1_note)) or info.get("known_prostate_cancer")
    relevant = is_cancer or (age is not None and age >= 65) \
        or bool(_LEE_FUNC_DOCUMENTED.search(stage1_note))
    if not relevant:
        return ""

    rows = []

    def _row(label, value):
        rows.append(f"  {(label + ':').ljust(28)}{value}")

    if is_cancer:
        m = _ECOG_RE.search(stage1_note)
        _row("ECOG performance status",
             m.group(1) if m else
             "___  (0 fully active · 1 restricted strenuous · 2 ambulatory, "
             "up >50% · 3 limited, in bed >50% · 4 bedbound)")

    pm = _SCHON_PERCEIVED.search(stage1_note)
    if pm:
        _row("Self-rated health", (next((g for g in pm.groups() if g), "") or "").strip().title())
    else:
        _row("Self-rated health", "___  (Excellent / Very good / Good / Fair / Poor)")

    if _SCHON_IADL.search(stage1_note):
        _row("IADL status", "Dependent in ≥1 IADL")
    elif _IADL_INDEPENDENT.search(stage1_note):
        _row("IADL status", "Independent")
    else:
        _row("IADL status", "___  (Independent / Dependent in ≥1 IADL)")

    if _difficulty_present(stage1_note, _SCHON_DIFF_QUARTER_MILE):
        _row("Ambulation (¼ mile)", "Difficulty walking ¼ mile / several blocks")
    elif _AMBULATES_OK.search(stage1_note):
        _row("Ambulation (¼ mile)", "No difficulty")
    else:
        _row("Ambulation (¼ mile)", "___  (No difficulty / Difficulty walking ¼ mile)")

    body = "\n".join(rows)
    est = info.get("primary_survival_summary")
    if est:
        body += f"\n\n  Estimated survival: {est}"
    return body


def build_age_guardrail_block(stage1_note: str) -> str:
    """Build the deterministic guardrail block to inject into the
    Assessment and Plan agent prompts.

    Format: explicit "what is INDICATED / DISCOURAGED / CONTRAINDICATED"
    table per life-expectancy bucket, with the actual AUA Early-Detection
    Guideline language as the citation."""
    info = classify_life_expectancy(stage1_note)
    bucket = info["bucket"]
    age = info["age"]
    flags = info["life_limiting_flags"]
    has_pc = info["known_prostate_cancer"]

    if bucket == "UNKNOWN":
        # Don't emit a block when we can't determine age — silent rather
        # than wrong.
        return ""

    header = [
        "=== AGE / LIFE-EXPECTANCY GUARDRAIL "
        "(deterministic; overrides any RAG guideline retrieval) ===",
        f"Patient age: {age}",
        f"Life-expectancy bucket: {bucket}",
    ]
    # NCCN/AUA SSA-actuarial + comorbidity-quartile estimate (the survival
    # predictor — NOT the Charlson index). The LLM may cite this figure.
    if info.get("schonberg_index_summary"):
        # Preferred survival predictor (validated 9-year, closest to 10-year).
        header.append(info["schonberg_index_summary"]
                      + " Cite this validated survival estimate (Schonberg index),"
                        " NOT a Charlson 10-year-survival %.")
        if info.get("life_expectancy_summary"):
            header.append("Corroborating actuarial estimate: "
                          + info["life_expectancy_summary"])
    elif info.get("life_expectancy_summary"):
        header.append(info["life_expectancy_summary"]
                      + " Use this life-expectancy figure (per NCCN/AUA "
                        "actuarial method), not a Charlson 10-year-survival %.")
    if info.get("lee_index_summary"):
        header.append(info["lee_index_summary"]
                      + " (Lee index — corroborating validated estimate.)")
    if flags:
        header.append("Life-limiting comorbidity flags detected: "
                      + ", ".join(flags))
    if has_pc:
        header.append(
            "Patient already has prostate cancer — screening rules "
            "below do NOT apply to staging / surveillance / treatment-"
            "response workup of that established cancer. They DO apply "
            "to NEW unrelated workup (e.g., another solid-organ "
            "screening question)."
        )

    # Patients with KNOWN prostate cancer are NOT in the screening
    # population. PSA here is a disease-monitoring marker, not a screening
    # test — telling the LLM to "stop PSA surveillance" for an mCRPC patient
    # (HOLES) is clinically wrong and drove context-blind Plan recs. These
    # variants apply the life-expectancy lens to INTENSITY of intervention
    # without discontinuing appropriate disease monitoring.
    rules_by_bucket_known_pc = {
        "VERY_LIMITED": [
            "RULES FOR THIS PATIENT (known prostate cancer; life "
            "expectancy estimated <5 yr):",
            "- PSA here is a DISEASE-MONITORING marker for the established "
            "  cancer, NOT a screening test. Do NOT recommend stopping PSA "
            "  monitoring and do NOT cite screening-cessation guidelines.",
            "- DO continue appropriate disease monitoring (PSA, symptom "
            "  assessment) at a cadence matched to the treatment plan.",
            "- Calibrate INTENSITY of intervention to life expectancy: "
            "  favor symptom control, quality of life, and goals-of-care "
            "  discussion over aggressive diagnostics/treatment unlikely "
            "  to benefit within the remaining life expectancy.",
            "- Do NOT order NEW detection workup unrelated to the known "
            "  cancer (e.g., screening for a different organ).",
            "- Do NOT invent a life-expectancy figure or a non-prostate "
            "  terminal diagnosis that is not documented in the source.",
        ],
        "LIMITED": [
            "RULES FOR THIS PATIENT (known prostate cancer; life "
            "expectancy ~5-10 yr):",
            "- PSA is disease monitoring for the established cancer, not "
            "  screening — continue it; do NOT apply screening-cessation "
            "  language.",
            "- Weigh the intensity of further treatment/diagnostics against "
            "  life expectancy and competing comorbidity, but keep "
            "  appropriate monitoring of the known cancer in place.",
            "- Name an explicit rationale for the surveillance interval "
            "  (functional status, treatment phase, patient preference).",
        ],
    }

    rules_by_bucket = {
        "VERY_LIMITED": [
            "AUA Early Detection of Prostate Cancer (2023) language:",
            "  > 'Routine PSA screening is not recommended for men "
            "≥75 years OR for men with life expectancy <10 years.'",
            "  > 'Prostate biopsy should not be performed in men whose "
            "life expectancy is <5 years, regardless of PSA, unless "
            "needed to manage symptoms.'",
            "",
            "RULES FOR THIS PATIENT (life expectancy estimated <5 yr):",
            "- DO NOT recommend routine PSA surveillance or screening.",
            "- DO NOT recommend prostate biopsy unless it would change "
            "  symptom management (e.g., to enable palliative ADT for "
            "  symptomatic disease).",
            "- DO NOT recommend mpMRI prostate as a workup step — it is "
            "  a precursor to biopsy, and biopsy is not indicated.",
            "- DO NOT cite AUA early-detection language as supporting "
            "  active workup in this patient.",
            "- Frame the Assessment and Plan around symptom management, "
            "  quality of life, and shared decision-making to STOP "
            "  screening if it is currently being done.",
            "- A note to discontinue routine cancer-detection workup "
            "  IS appropriate ('per AUA, given life expectancy <5 yr, "
            "  PSA surveillance is no longer indicated; will discuss "
            "  with patient').",
        ],
        "LIMITED": [
            "AUA Early Detection of Prostate Cancer (2023) language:",
            "  > 'Shared decision making about PSA screening is "
            "recommended for men aged 55-69. PSA screening is generally "
            "discouraged in men aged ≥70 unless the patient is in above-"
            "average health with >10-year life expectancy.'",
            "  > 'Biopsy decisions should incorporate life expectancy "
            "and competing causes of mortality.'",
            "",
            "RULES FOR THIS PATIENT (life expectancy ~5-10 yr):",
            "- Routine PSA screening requires explicit shared-decision-"
            "  making — do NOT default to 'continue annual PSA' without "
            "  conditioning on life expectancy and patient preference.",
            "- mpMRI / biopsy should be recommended ONLY IF a confirmed "
            "  cancer would change management given life expectancy. "
            "  Otherwise the recommendation is a 'discuss risks/benefits "
            "  of further workup' line, not a definitive order.",
            "- If recommending continued surveillance, name the explicit "
            "  rationale (functional status, patient preference, no "
            "  competing terminal illness). 'Per AUA' alone is not "
            "  sufficient.",
            "- It is acceptable to recommend STOPPING PSA surveillance "
            "  if the patient lacks the life expectancy to benefit from "
            "  intervention.",
        ],
        "STANDARD": [
            "Standard AUA early-detection options apply. Recommendations "
            "for PSA surveillance, mpMRI, and biopsy should still be "
            "tailored to individual risk and patient preference, but the "
            "life-expectancy guardrail is not active for this patient.",
        ],
    }

    # Known-PC patients get the disease-monitoring variant (no screening-
    # cessation) for the life-expectancy-sensitive buckets; STANDARD is the
    # same either way.
    if has_pc and bucket in rules_by_bucket_known_pc:
        body = rules_by_bucket_known_pc[bucket]
    else:
        body = rules_by_bucket.get(bucket, rules_by_bucket["STANDARD"])

    return "\n".join(header + [""] + body) + "\n=== END AGE / LIFE-EXPECTANCY GUARDRAIL ===\n"
