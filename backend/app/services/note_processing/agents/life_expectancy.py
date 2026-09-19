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
