"""NCCN/AUA-endorsed life-expectancy estimator.

Replaces the Charlson Comorbidity Index as the survival predictor that drives
prostate-cancer screening / treatment-intensity decisions. Method (per the NCCN
Prostate Cancer guideline and AUA):

  1. Take the age/sex expected remaining years from the Social Security
     Administration (SSA) period life table.
  2. Adjust for comorbidity by health quartile:
       - healthiest quartile  x1.5
       - middle two quartiles  x1.0
       - least-healthy quartile x0.5

This yields an individualized life-expectancy estimate rather than the coarse
integer 10-year-survival % of the Charlson index.

The SSA values below are expected remaining years (e_x) at exact age from the
SSA period life table; intermediate ages are linearly interpolated. Exact
figures shift by a few tenths between table years — clinically immaterial at the
>10 / 5-10 / <5-year decision thresholds this feeds.
"""
from __future__ import annotations

import re
from typing import Optional, Dict, Any

# SSA period life table — expected remaining years (e_x) by exact age.
_SSA_MALE = {40: 38.1, 45: 33.7, 50: 29.4, 55: 25.3, 60: 21.5, 65: 17.9,
             70: 14.6, 75: 11.5, 80: 8.6, 85: 6.1, 90: 4.1, 95: 2.9, 100: 2.1}
_SSA_FEMALE = {40: 42.0, 45: 37.4, 50: 32.9, 55: 28.6, 60: 24.5, 65: 20.5,
               70: 16.7, 75: 13.0, 80: 9.7, 85: 6.9, 90: 4.7, 95: 3.2, 100: 2.3}

# NCCN health-quartile multipliers.
_QUARTILE_MULT = {"healthiest": 1.5, "average": 1.0, "least-healthy": 0.5}


def _interp(table: Dict[int, float], age: int) -> float:
    ages = sorted(table)
    if age <= ages[0]:
        return table[ages[0]]
    if age >= ages[-1]:
        return table[ages[-1]]
    for i in range(1, len(ages)):
        if age <= ages[i]:
            a0, a1 = ages[i - 1], ages[i]
            return table[a0] + (table[a1] - table[a0]) * (age - a0) / (a1 - a0)
    return table[ages[-1]]


def base_life_expectancy(age: int, sex: str = "male") -> float:
    """Unadjusted SSA expected remaining years at this age/sex."""
    table = _SSA_FEMALE if (sex or "").lower().startswith("f") else _SSA_MALE
    return round(_interp(table, age), 1)


def health_quartile(n_severe: int, excellent_health: bool = False) -> str:
    """Map to an NCCN health quartile from the SEVERE/end-stage comorbidity flags
    the age guardrail detects (metastatic cancer, hospice, ESRD, advanced CHF,
    severe COPD, advanced dementia, moderate-severe frailty, etc.).

    These flags mark the sick end of the spectrum, not a graded index, so:
      - any severe flag  -> least-healthy quartile (x0.5)
      - explicit excellent-health / no-comorbidity signal -> healthiest (x1.5)
      - otherwise         -> average / table value (x1.0)   <- conservative default
    We do NOT assume "healthiest" merely from the absence of severe flags —
    over-estimating life expectancy is the over-treatment (clinical-harm)
    direction, so the default is the unadjusted table value."""
    if n_severe >= 1:
        return "least-healthy"
    if excellent_health:
        return "healthiest"
    return "average"


def estimate_life_expectancy(age: Optional[int], sex: str = "male",
                             n_comorbidities: int = 0,
                             excellent_health: bool = False) -> Optional[Dict[str, Any]]:
    """SSA-based, comorbidity-adjusted life expectancy (years). None if age
    unknown."""
    if age is None:
        return None
    base = base_life_expectancy(age, sex)
    q = health_quartile(n_comorbidities, excellent_health)
    mult = _QUARTILE_MULT[q]
    return {
        "years": round(base * mult, 1),
        "base_years": base,
        "quartile": q,
        "multiplier": mult,
        "age": age,
        "sex": sex,
    }


def parse_sex(note: str) -> str:
    """Best-effort sex from the note; defaults to male (this is a urology app and
    the life-expectancy lens is applied chiefly to prostate decisions). Only
    calls female on an explicit marker with no prostate/male context."""
    if not note:
        return "male"
    if re.search(r"prostate|\bmale\b|\bhe\b|\bhis\b", note, re.IGNORECASE):
        return "male"
    if re.search(r"\bSex\s*[:=]\s*F\b|\bfemale\b|\bwoman\b|\bshe\b", note, re.IGNORECASE):
        return "female"
    return "male"


# ---------------------------------------------------------------------------
# Lee index (Lee SJ et al., JAMA 2006;295:801-808) — validated 4-year mortality
# for community-dwelling older adults. Exact published point weights below.
# Used here as a DOWNGRADE-ONLY refinement: it requires self-reported functional
# (ADL) status, so it only activates when the chart documents functional status;
# a high score (high short-term mortality) reliably implies limited life
# expectancy and lowers the bucket, but a low score never OVER-rides the SSA
# estimate upward (4-year mortality says nothing definitive about 10-year
# survival). The Schonberg 9-year index is not implemented: its point table is
# not published in a citable/extractable form (ePrognosis is a closed calculator)
# and it additionally needs self-rated health that charts don't capture.
# ---------------------------------------------------------------------------
_LEE_AGE_BANDS = ((85, 7), (80, 5), (75, 4), (70, 3), (65, 2), (60, 1))
_LEE_DIABETES = re.compile(r"\bdiabet|\bT2DM\b|\bDM2\b|type\s*2\s*diabetes", re.I)
_LEE_CANCER = re.compile(r"\bcancer\b|carcinoma|malignan|adenocarcinoma|lymphoma|leukemia", re.I)
_LEE_LUNG = re.compile(r"\bCOPD\b|emphysema|chronic\s+bronchitis|pulmonary\s+fibrosis|"
                       r"interstitial\s+lung|\blung\s+disease\b|\basthma\b", re.I)
_LEE_CHF = re.compile(r"\bCHF\b|heart\s+failure|\bHFrEF\b|\bHFpEF\b|cardiomyopathy", re.I)
_LEE_SMOKER = re.compile(r"current\s+smoker|currently\s+smok|active\s+(?:tobacco|smok)|"
                         r"smokes\s+(?:daily|\d)|\btobacco\s+use\s*[:=]?\s*current", re.I)
# Functional status is DOCUMENTED (either direction) — the gate for computing Lee.
_LEE_FUNC_DOCUMENTED = re.compile(
    r"\bADLs?\b|activities\s+of\s+daily\s+living|ambulat|\bgait\b|mobility|"
    r"bath(?:e|ing)|dressing|toileting|transfers?\b|walker|wheelchair|\bcane\b|"
    r"independent\s+(?:in|with)|assistance\s+with|difficulty\s+(?:walking|bathing|standing)|"
    r"ECOG|performance\s+status|frailty|bed[-\s]?bound|\bfalls?\b|nursing\s+home", re.I)
# Affirmative functional DIFFICULTY (scores points) — not merely 'independent'.
# \b anchors keep 'dependent' from matching inside 'inDEPENDENT'; negation is
# handled separately by _difficulty_present (so 'no difficulty walking' /
# 'independent in ADLs' don't score).
_LEE_DIFF_WALK = re.compile(
    r"\bdifficulty\s+walking|\bunable\s+to\s+walk|\buses?\s+(?:a\s+)?(?:walker|wheelchair|cane)|"
    r"\bwheelchair[-\s]?bound|\bbed[-\s]?bound|\bbedbound|\blimited\s+mobility|"
    r"\bgait\s+(?:instability|impair)|\bnon[-\s]?ambulatory", re.I)
_LEE_DIFF_BATH = re.compile(
    r"\b(?:assistance|help|difficulty|dependent)\b\s+(?:with\s+|in\s+|for\s+)?"
    r"(?:bathing|self[-\s]?care|ADLs?)|\brequires?\s+assistance\s+with\s+(?:daily|self)", re.I)
_LEE_BMI = re.compile(r"\bBMI\s*[:=]?\s*(\d{1,2}(?:\.\d)?)", re.I)
# Negation immediately before a difficulty phrase -> not a real difficulty.
_LEE_NEG_BEFORE = re.compile(
    r"(?:\bno\b|\bnot\b|\bwithout\b|\bdenies\b|\bindependent\b|\bnegative\s+for\b|"
    r"\bable\s+to\b)[\w\s,]{0,20}$", re.I)


def _difficulty_present(note: str, rx: "re.Pattern") -> bool:
    """True if a functional-difficulty phrase appears and is NOT negated by a
    preceding 'no/without/independent/denies' within a short window."""
    for m in rx.finditer(note):
        if not _LEE_NEG_BEFORE.search(note[max(0, m.start() - 25):m.start()]):
            return True
    return False


def _lee_age_points(age: int) -> int:
    for lo, pts in _LEE_AGE_BANDS:
        if age >= lo:
            return pts
    return 0  # <60 (index not validated below 60)


def compute_lee_index(note: str, age: Optional[int], sex: str = "male") -> Optional[Dict[str, Any]]:
    """Lee 4-year-mortality index. Returns None when age is unknown or functional
    status is not documented (the index needs ADL inputs — defer to SSA then)."""
    if age is None or not note:
        return None
    if not _LEE_FUNC_DOCUMENTED.search(note):
        return None
    pts = _lee_age_points(age)
    contributors = {}
    if (sex or "").lower().startswith("m"):
        pts += 2; contributors["male"] = 2
    for label, rx, p in (("diabetes", _LEE_DIABETES, 1), ("cancer", _LEE_CANCER, 2),
                         ("lung disease", _LEE_LUNG, 2), ("heart failure", _LEE_CHF, 2),
                         ("current smoker", _LEE_SMOKER, 2)):
        if rx.search(note):
            pts += p; contributors[label] = p
    m = _LEE_BMI.search(note)
    if m:
        try:
            if float(m.group(1)) < 25:
                pts += 1; contributors["BMI<25"] = 1
        except ValueError:
            pass
    if _difficulty_present(note, _LEE_DIFF_WALK):
        pts += 2; contributors["difficulty walking"] = 2
    if _difficulty_present(note, _LEE_DIFF_BATH):
        pts += 2; contributors["difficulty bathing"] = 2
    # 'managing money' / 'pushing large objects' items are not reliably charted;
    # omitted (0) — this biases the score LOW, consistent with downgrade-only use.
    if pts <= 5:
        band, m4 = "<4%", 4
    elif pts <= 9:
        band, m4 = "15%", 15
    elif pts <= 13:
        band, m4 = "42%", 42
    else:
        band, m4 = "64%", 64
    return {"score": pts, "mortality_4yr_pct": m4, "mortality_4yr_band": band,
            "contributors": contributors, "age": age}


# ---------------------------------------------------------------------------
# Schonberg index — validated 5- and 9-year mortality for community-dwelling
# adults >=65. Exact point weights from Schonberg MA et al., J Gen Intern Med
# 2009;24(10):1115-1122 (Table 2); 9-year mortality-by-score from the external
# validation, J Am Geriatr Soc 2011;59(8):1444-1451 (Table 3, development
# cohort). The 9-year horizon is the closest validated analogue to the "10-year
# survival" prostate-decision question, so this is the PREFERRED estimate when
# its self-report inputs (perceived health / functional status) are documented;
# otherwise the SSA actuarial method governs.
# ---------------------------------------------------------------------------
_SCHON_AGE_BANDS = ((85, 7), (80, 5), (75, 3), (70, 1), (65, 0))
# 9-year mortality % by total point score (upper bound of each band -> pct).
_SCHON_9YR = ((1, 11), (3, 12), (5, 17), (7, 25), (9, 35),
              (11, 53), (13, 60), (15, 71), (17, 82), (999, 89))

_SCHON_CURRENT_SMOKER = _LEE_SMOKER
_SCHON_FORMER_SMOKER = re.compile(r"former\s+smoker|ex[-\s]?smoker|quit\s+smok|"
                                  r"former\s+tobacco|previous\s+(?:tobacco|smok)", re.I)
_SCHON_COPD = re.compile(r"\bCOPD\b|chronic\s+obstructive|emphysema|chronic\s+bronchitis", re.I)
_SCHON_PERCEIVED = re.compile(
    r"(?:perceived|self[-\s]?rated|overall)\s+health\s*[:=]?\s*(\w+)|"
    r"health\s+(?:is|was|as)\s+(excellent|very\s+good|good|fair|poor)|"
    r"reports?\s+(excellent|very\s+good|good|fair|poor)\s+health|"
    r"(fair|poor)\s+(?:overall\s+)?health", re.I)
_SCHON_IADL = re.compile(
    r"dependent\s+(?:in|for)\s+(?:at\s+least\s+)?(?:>=|≥)?\s*(?:one|a|1|any|some|\d+)?\s*IADLs?|"
    r"IADL\s+depend|"
    r"difficulty\s+(?:managing|with)\s+(?:money|finances|medications?|shopping|"
    r"transportation|cooking|housework|telephone|meals)|"
    r"needs?\s+help\s+with\s+(?:shopping|finances|money|medications?|cooking|"
    r"housework|transportation)|requires?\s+assistance\s+with\s+IADL", re.I)
_SCHON_DIFF_QUARTER_MILE = re.compile(
    r"difficulty\s+walking\s+(?:a\s+)?(?:quarter[-\s]?mile|1/4\s*mile|¼\s*mile|"
    r"several\s+blocks|a\s+few\s+blocks)|unable\s+to\s+walk\s+(?:several\s+blocks|"
    r"a\s+quarter\s+mile|¼\s*mile)", re.I)
_SCHON_HOSP_MANY = re.compile(r"(?:two|three|2|3|multiple|several)\s+(?:hospitaliz|"
                              r"admissions?|admitted)|hospitaliz\w*\s+(?:twice|"
                              r"multiple\s+times)", re.I)
_SCHON_HOSP_ONE = re.compile(r"hospitaliz|\badmitted\b|\badmission\b", re.I)
_SCHON_HOSP_NONE = re.compile(r"no\s+hospitaliz|not\s+hospitaliz|denies?\s+hospitaliz|"
                              r"no\s+(?:recent\s+)?admissions?", re.I)


def _schonberg_data_present(note: str) -> bool:
    """The index adds value over age+comorbidity only when its self-report
    domains are documented. Require perceived health OR functional (IADL/walking)
    status to be described; otherwise defer to the SSA estimate."""
    return bool(_SCHON_PERCEIVED.search(note) or _LEE_FUNC_DOCUMENTED.search(note))


def _schon_9yr_mortality(score: int) -> int:
    for hi, pct in _SCHON_9YR:
        if score <= hi:
            return pct
    return 89


def compute_schonberg_index(note: str, age: Optional[int], sex: str = "male") -> Optional[Dict[str, Any]]:
    """Schonberg 9-year-mortality index -> estimated 9-year survival %. None when
    age <65 / unknown or the self-report inputs aren't documented."""
    if age is None or age < 65 or not note or not _schonberg_data_present(note):
        return None
    pts = 0
    for lo, p in _SCHON_AGE_BANDS:
        if age >= lo:
            pts += p
            break
    contributors = {}
    if (sex or "").lower().startswith("m"):
        pts += 3; contributors["male"] = 3
    if _SCHON_CURRENT_SMOKER.search(note):
        pts += 3; contributors["current smoker"] = 3
    elif _SCHON_FORMER_SMOKER.search(note):
        pts += 1; contributors["former smoker"] = 1
    m = _LEE_BMI.search(note)
    if m:
        try:
            if float(m.group(1)) < 25:
                pts += 2; contributors["BMI<25"] = 2
        except ValueError:
            pass
    for label, rx in (("COPD", _SCHON_COPD), ("diabetes", _LEE_DIABETES), ("cancer", _LEE_CANCER)):
        if rx.search(note):
            pts += 2; contributors[label] = 2
    if _SCHON_HOSP_NONE.search(note):
        pass
    elif _SCHON_HOSP_MANY.search(note):
        pts += 3; contributors["≥2 hospitalizations"] = 3
    elif _SCHON_HOSP_ONE.search(note):
        pts += 1; contributors["1 hospitalization"] = 1
    # perceived health
    pm = _SCHON_PERCEIVED.search(note)
    if pm:
        val = next((g for g in pm.groups() if g), "").lower()
        if val in ("fair", "poor"):
            pts += 2; contributors["fair/poor perceived health"] = 2
        elif val == "good":
            pts += 1; contributors["good perceived health"] = 1
    if _SCHON_IADL.search(note):
        pts += 2; contributors["IADL dependency"] = 2
    if _difficulty_present(note, _SCHON_DIFF_QUARTER_MILE):
        pts += 3; contributors["difficulty walking ¼ mile"] = 3
    mort9 = _schon_9yr_mortality(pts)
    return {"score": pts, "mortality_9yr_pct": mort9,
            "survival_9yr_pct": 100 - mort9, "contributors": contributors, "age": age}


def format_life_expectancy(le: Optional[Dict[str, Any]]) -> str:
    """One-line clinician-facing summary, or '' if unknown."""
    if not le:
        return ""
    q_disp = {"healthiest": "healthiest quartile",
              "average": "average health",
              "least-healthy": "least-healthy quartile"}[le["quartile"]]
    return (f"Estimated life expectancy ~{le['years']:g} years "
            f"(SSA actuarial {le['base_years']:g} yr at age {le['age']} "
            f"x{le['multiplier']:g} for {q_disp}).")
