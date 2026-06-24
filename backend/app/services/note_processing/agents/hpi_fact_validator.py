"""
HPIDraft fact validator.

Cross-checks every clinically meaningful value in a draft against the
deterministic ground truth extracted from the source document. Catches
the cases schema validation cannot:

  - PSA value cited in draft but not in PSA Curve
  - Treatment claim with no PSH/PATHOLOGY/timeline support
  - Procedure finding date doesn't match the source procedure date
  - Name / age / sex disagree with the banner
  - PSA direction inconsistent with current vs prior values
  - Medication not in the MEDICATIONS list
  - Date chronology issues (prior > current, etc.)

Inputs:
  draft:        HPIDraft dict (already schema-valid)
  ground_truth: GroundTruth dataclass populated from source extractors

Output:
  List of FactValidationError with precise field paths and messages.
  Empty list = factually valid.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Ground truth dataclass
# ---------------------------------------------------------------------------

@dataclass
class PSAEntry:
    value: float
    date: str  # "YYYY-MM-DD"


@dataclass
class GroundTruth:
    """Deterministic facts extracted from the source. Built by the
    HPI orchestrator from existing extractors before the LLM is called.
    """
    # Banner
    name: str = ""
    age: int = 0
    sex: str = ""  # 'male' / 'female'
    visit_date: str = ""  # YYYY-MM-DD

    # PSA Curve — list of (value, date) sorted newest-first
    psa_entries: List[PSAEntry] = field(default_factory=list)

    # Treatment evidence
    confirmed_treatment_modalities: Set[str] = field(default_factory=set)
    treatment_naive: bool = True

    # Pathology
    pathology_text: str = ""  # raw PATHOLOGY section text
    gleason_scores: Set[str] = field(default_factory=set)  # {"3+3", "3+4", ...}
    grade_groups: Set[int] = field(default_factory=set)    # {1, 2, ...}

    # PSH text (raw)
    psh_text: str = ""

    # PMH text (raw)
    pmh_text: str = ""

    # Medications — list of generic-lowercased names
    medications: Set[str] = field(default_factory=set)

    # Procedure findings (date -> set of procedure_type)
    procedure_dates: Dict[str, Set[str]] = field(default_factory=dict)

    # Imaging text
    imaging_text: str = ""


# ---------------------------------------------------------------------------
# Fact validation error
# ---------------------------------------------------------------------------

class FactValidationError:
    __slots__ = ("path", "code", "message", "found", "expected", "severity")

    def __init__(self, path: str, code: str, message: str,
                 found: Any = None, expected: Any = None,
                 severity: str = "ERROR"):
        self.path = path
        self.code = code
        self.message = message
        self.found = found
        self.expected = expected
        self.severity = severity

    def __repr__(self):
        return f"<FactError {self.path}: [{self.code}] {self.message}>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> Optional[datetime]:
    """Parse ISO date YYYY / YYYY-MM / YYYY-MM-DD into a datetime."""
    if not s:
        return None
    parts = s.split("-")
    try:
        if len(parts) == 1:
            return datetime(int(parts[0]), 1, 1)
        if len(parts) == 2:
            return datetime(int(parts[0]), int(parts[1]), 1)
        if len(parts) == 3:
            return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None
    return None


def _approx_value_match(a: float, b: float, tol: float = 0.05) -> bool:
    return abs(a - b) < tol


def _date_within_window(claimed: str, truth: str, days: int = 31) -> bool:
    """True if two ISO dates are within `days` of each other.
    Tolerates month-only vs day-precision dates."""
    d1 = _parse_date(claimed)
    d2 = _parse_date(truth)
    if d1 is None or d2 is None:
        return False
    return abs((d1 - d2).days) <= days


# ---------------------------------------------------------------------------
# Per-section validators
# ---------------------------------------------------------------------------

def _validate_intro(intro: Dict, gt: GroundTruth,
                    errors: List[FactValidationError]) -> None:
    if not intro:
        return
    # Name: case-insensitive substring match (banner may include middle name)
    claimed_name = (intro.get("name") or "").strip()
    if claimed_name and gt.name:
        # Extract surname from both (last word)
        claimed_last = claimed_name.split()[-1].lower()
        truth_last = gt.name.split()[-1].lower() if gt.name else ""
        if truth_last and claimed_last != truth_last:
            errors.append(FactValidationError(
                "intro.name", "NAME_MISMATCH",
                f"draft name '{claimed_name}' surname doesn't match banner '{gt.name}'",
                found=claimed_name, expected=gt.name,
            ))
    # Age: must match (±0)
    if intro.get("age") is not None and gt.age:
        if intro["age"] != gt.age:
            errors.append(FactValidationError(
                "intro.age", "AGE_MISMATCH",
                f"draft age {intro['age']} != banner age {gt.age}",
                found=intro["age"], expected=gt.age,
            ))
    # Sex
    claimed_sex = (intro.get("sex") or "").lower()
    if claimed_sex and gt.sex and claimed_sex != gt.sex.lower():
        errors.append(FactValidationError(
            "intro.sex", "SEX_MISMATCH",
            f"draft sex '{claimed_sex}' != banner '{gt.sex}'",
            found=claimed_sex, expected=gt.sex,
        ))


def _validate_psa_trajectory(psa: Dict, gt: GroundTruth,
                             errors: List[FactValidationError]) -> None:
    if not psa:
        return

    # current_value must be in PSA Curve (within 0.05 tolerance)
    cv = psa.get("current_value")
    cd = psa.get("current_date")
    if cv is not None and gt.psa_entries:
        match = next(
            (e for e in gt.psa_entries if _approx_value_match(e.value, float(cv))),
            None,
        )
        if match is None:
            errors.append(FactValidationError(
                "psa_trajectory.current_value", "PSA_VALUE_NOT_IN_CURVE",
                f"PSA value {cv} not present in PSA Curve",
                found=cv,
                expected=[e.value for e in gt.psa_entries[:5]],
            ))
        elif cd:
            # current_date should match (within 31 days) the matched entry
            if not _date_within_window(cd, match.date):
                errors.append(FactValidationError(
                    "psa_trajectory.current_date", "PSA_DATE_MISMATCH",
                    f"PSA value {cv} cited with date {cd} "
                    f"but PSA Curve shows that value on {match.date}",
                    found=cd, expected=match.date,
                ))

    # prior_value must also be in PSA Curve
    pv = psa.get("prior_value")
    if pv is not None and gt.psa_entries:
        match = next(
            (e for e in gt.psa_entries if _approx_value_match(e.value, float(pv))),
            None,
        )
        if match is None:
            errors.append(FactValidationError(
                "psa_trajectory.prior_value", "PSA_VALUE_NOT_IN_CURVE",
                f"PSA value {pv} not present in PSA Curve",
                found=pv,
            ))

    # peak_value must be in PSA Curve
    pkv = psa.get("peak_value")
    if pkv is not None and gt.psa_entries:
        match = next(
            (e for e in gt.psa_entries if _approx_value_match(e.value, float(pkv))),
            None,
        )
        if match is None:
            errors.append(FactValidationError(
                "psa_trajectory.peak_value", "PSA_VALUE_NOT_IN_CURVE",
                f"Peak PSA value {pkv} not present in PSA Curve",
                found=pkv,
            ))

    # direction MUST be consistent with current vs prior numbers.
    # The 'meaningful change' threshold is the larger of an absolute
    # floor (0.1 ng/mL — assay noise + biologic variability) and 10% of
    # the prior value (relative noise scales with the value). For
    # undetectable post-treatment PSAs (e.g. 0.02 → 0.04), the
    # threshold is 0.1, so the change is correctly classified 'stable'
    # rather than 'increased'.
    direction = psa.get("direction")
    if cv is not None and pv is not None and direction:
        meaningful_change = max(0.1, abs(pv) * 0.10)
        diff = cv - pv
        if diff > meaningful_change and direction not in ("increased", "fluctuating"):
            errors.append(FactValidationError(
                "psa_trajectory.direction", "DIRECTION_INCONSISTENT",
                f"current {cv} > prior {pv} (delta {diff:+.2f} > "
                f"threshold {meaningful_change:.2f}) but direction is '{direction}'",
                found=direction, expected="increased",
            ))
        elif diff < -meaningful_change and direction not in ("decreased", "fluctuating"):
            errors.append(FactValidationError(
                "psa_trajectory.direction", "DIRECTION_INCONSISTENT",
                f"current {cv} < prior {pv} (delta {diff:+.2f} < "
                f"-{meaningful_change:.2f}) but direction is '{direction}'",
                found=direction, expected="decreased",
            ))
        elif abs(diff) <= meaningful_change and direction not in ("stable",):
            errors.append(FactValidationError(
                "psa_trajectory.direction", "DIRECTION_INCONSISTENT",
                f"current {cv} ≈ prior {pv} (delta {diff:+.2f} within "
                f"±{meaningful_change:.2f}) but direction is '{direction}'",
                found=direction, expected="stable",
            ))

    # Date chronology: prior_date must be earlier than current_date
    if cd and psa.get("prior_date"):
        d_cur = _parse_date(cd)
        d_prior = _parse_date(psa["prior_date"])
        if d_cur and d_prior and d_prior > d_cur:
            errors.append(FactValidationError(
                "psa_trajectory", "DATE_OUT_OF_ORDER",
                f"prior_date {psa['prior_date']} is after current_date {cd}",
                found=psa["prior_date"], expected=f"<= {cd}",
            ))


def _validate_treatment_history(events: List[Dict], gt: GroundTruth,
                                errors: List[FactValidationError]) -> None:
    if not events:
        return
    truth_lc = (gt.psh_text + "\n" + gt.pathology_text + "\n" + gt.pmh_text).lower()
    for i, evt in enumerate(events):
        modality = evt.get("modality", "")
        status = evt.get("status", "")
        verified_in = evt.get("verified_in", "")
        path = f"treatment_history[{i}]"
        # If marking as 'completed' / 'ongoing', the modality must have
        # evidence in PSH / pathology / PMH OR be in the confirmed list
        if status in ("completed", "ongoing", "discontinued"):
            # active-surveillance is special — implied by absence of treatment
            if modality == "active-surveillance":
                continue
            modality_in_truth = (
                modality in gt.confirmed_treatment_modalities
                or _modality_mentioned_in_text(modality, truth_lc)
            )
            if not modality_in_truth:
                errors.append(FactValidationError(
                    f"{path}.modality", "TREATMENT_UNSUPPORTED",
                    f"treatment '{modality}' (status={status}) not found in "
                    f"PSH/pathology/PMH",
                    found=modality, expected=sorted(gt.confirmed_treatment_modalities),
                ))


def _modality_mentioned_in_text(modality: str, text_lc: str) -> bool:
    """Heuristic: does the lowercased text contain a recognizable token
    for this modality?"""
    tokens = {
        "prostatectomy": ["prostatectomy", "ralp", "rarp", "rrp", "open prostatectomy"],
        "radiation": ["radiation", "xrt", "ebrt", "imrt", "sbrt", "igrt", "radiotherapy"],
        "brachytherapy": ["brachytherapy", "seed implant"],
        "focal-therapy": ["hifu", "cryotherapy", "cryoablation", "focal therapy", "tulsa"],
        "ADT": ["adt", "androgen deprivation", "leuprolide", "lupron", "eligard",
                "degarelix", "goserelin", "relugolix"],
        "TURP": ["turp", "transurethral resection of prostate", "transurethral resection: ", "prostate, transurethral"],
        "TURBT": ["turbt", "transurethral resection of bladder"],
        "nephrectomy": ["nephrectomy"],
        "cystectomy": ["cystectomy"],
        "chemotherapy": ["chemotherapy", "docetaxel", "cabazitaxel"],
        "immunotherapy": ["nivolumab", "ipilimumab", "pembrolizumab", "immunotherapy"],
        "ureteroscopy": ["ureteroscopy", "urs"],
        "shock-wave-lithotripsy": ["swl", "shock wave"],
        "PCNL": ["pcnl", "percutaneous nephrolithotomy"],
        "orchiectomy": ["orchiectomy"],
        "varicocelectomy": ["varicocelectomy"],
        "hydrocelectomy": ["hydrocelectomy", "spermatocelectomy"],
        "cystoscopy-with-treatment": ["cystoscopy"],
    }
    for tok in tokens.get(modality, [modality.lower()]):
        if tok in text_lc:
            return True
    return False


def _validate_prior_diagnosis(dx: Dict, gt: GroundTruth,
                              errors: List[FactValidationError]) -> None:
    if not dx:
        return
    # Gleason must match if cited
    g = dx.get("gleason")
    if g and gt.gleason_scores:
        if g not in gt.gleason_scores:
            errors.append(FactValidationError(
                "prior_diagnosis.gleason", "GLEASON_NOT_IN_PATHOLOGY",
                f"Gleason {g} not in pathology",
                found=g, expected=sorted(gt.gleason_scores),
            ))
    # Grade Group must match if cited
    gg = dx.get("grade_group")
    if gg and gt.grade_groups:
        if gg not in gt.grade_groups:
            errors.append(FactValidationError(
                "prior_diagnosis.grade_group", "GG_NOT_IN_PATHOLOGY",
                f"Grade Group {gg} not in pathology",
                found=gg, expected=sorted(gt.grade_groups),
            ))

    # Gleason ↔ Grade Group consistency. LLM frequently confuses the
    # Gleason sum (which can be 6, 7, 8, 9, 10) with the Grade Group
    # (1-5). E.g. Woods has Gleason 4+4 → GG4, not GG8. ISUP 2014:
    #   3+3 → 1
    #   3+4 → 2
    #   4+3 → 3
    #   4+4 / 3+5 / 5+3 → 4
    #   4+5 / 5+4 / 5+5 → 5
    GLEASON_TO_GG = {
        "3+3": 1, "3+4": 2, "4+3": 3,
        "4+4": 4, "3+5": 4, "5+3": 4,
        "4+5": 5, "5+4": 5, "5+5": 5,
    }
    if g and gg and g in GLEASON_TO_GG:
        expected_gg = GLEASON_TO_GG[g]
        if gg != expected_gg:
            # WARN-only: GG vs Gleason is a derivable fact and the
            # Gleason itself is the primary anchor (separately verified
            # against pathology). Blocking on this just pushed v2 into
            # retry loops with no clear win.
            errors.append(FactValidationError(
                "prior_diagnosis.grade_group", "GLEASON_GG_MISMATCH",
                f"Gleason {g} corresponds to Grade Group {expected_gg}, "
                f"not {gg} (ISUP 2014 grading)",
                found=gg, expected=expected_gg, severity="WARN",
            ))

    # Risk category ↔ Grade Group consistency for prostate cancer.
    # Approximate NCCN mapping:
    #   GG1: very-low / low (depending on PSA, T-stage)
    #   GG2: intermediate (favorable)
    #   GG3: intermediate (unfavorable)
    #   GG4-5: high / very-high
    risk = dx.get("risk_category")
    # Risk-category check anchored to DERIVED GG from Gleason rather
    # than the (possibly-wrong) LLM-emitted GG. If LLM emits Gleason
    # 4+4 (correct, validated against pathology) but GG=8 (wrong), we
    # still want to catch risk="low" — derive GG from Gleason for the
    # comparison. Gleason itself is independently validated as
    # GLEASON_NOT_IN_PATHOLOGY so the derivation is sound.
    derived_gg = GLEASON_TO_GG.get(g) if g else None
    effective_gg = derived_gg if derived_gg is not None else gg
    if risk and isinstance(risk, str) and effective_gg:
        rl = risk.strip().lower()
        if effective_gg in (4, 5) and rl in ("very-low", "low", "very low"):
            # ERROR-severity: labeling high-grade (GG4-5) disease as
            # "low-risk" is clinically unsafe — would mislead a reader
            # into believing surveillance is appropriate when it isn't.
            errors.append(FactValidationError(
                "prior_diagnosis.risk_category", "RISK_GG_MISMATCH",
                f"Grade Group {effective_gg} (from Gleason {g}) is "
                f"high-risk; risk_category '{risk}' is inconsistent",
                found=risk, expected="high",
            ))
        if effective_gg == 1 and rl in ("high", "very-high", "very high"):
            errors.append(FactValidationError(
                "prior_diagnosis.risk_category", "RISK_GG_MISMATCH",
                f"Grade Group 1 is low-risk; risk_category "
                f"'{risk}' is inconsistent",
                found=risk, expected="low",
            ))


def _validate_procedure_findings(findings: List[Dict], gt: GroundTruth,
                                 errors: List[FactValidationError]) -> None:
    if not findings:
        return
    for i, pf in enumerate(findings):
        path = f"procedure_findings[{i}]"
        proc_type = pf.get("procedure_type", "")
        date = pf.get("date", "")
        if not date:
            continue
        # Match date against procedure_dates index (within 31 days)
        found_match = False
        for known_date, known_procs in gt.procedure_dates.items():
            if proc_type in known_procs and _date_within_window(date, known_date):
                found_match = True
                break
        if not found_match:
            # Soft warning — pathology / imaging may still substantiate
            blob_lc = (gt.pathology_text + "\n" + gt.imaging_text).lower()
            if not _date_in_text(date, blob_lc):
                errors.append(FactValidationError(
                    path, "PROCEDURE_DATE_UNSUPPORTED",
                    f"{proc_type} on {date} not in procedure findings or "
                    f"pathology/imaging text",
                    found=date, severity="WARN",
                ))


def _date_in_text(iso_date: str, text_lc: str) -> bool:
    """Soft: does the text contain any form of this date?"""
    d = _parse_date(iso_date)
    if d is None:
        return False
    forms = [
        f"{d.month}/{d.day}/{d.year}",
        f"{d.month:02d}/{d.day:02d}/{d.year}",
        f"{d.year}-{d.month:02d}-{d.day:02d}",
        f"{d.year:04d}",  # at minimum the year
    ]
    return any(f in text_lc for f in forms)


def _validate_current_regimen(regimen: List[Dict], gt: GroundTruth,
                              errors: List[FactValidationError]) -> None:
    if not regimen:
        return
    for i, item in enumerate(regimen):
        path = f"current_regimen[{i}]"
        med = (item.get("medication") or "").lower()
        if not med:
            continue
        # Med name should appear in medications text (as a substring)
        med_root = med.split()[0]  # first word
        if gt.medications and not any(med_root in m for m in gt.medications):
            errors.append(FactValidationError(
                f"{path}.medication", "MED_NOT_IN_LIST",
                f"medication '{med}' not in MEDICATIONS section",
                found=med, expected=sorted(list(gt.medications)[:8]),
            ))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _validate_visit_reason_consistency(draft: Dict, gt: "GroundTruth",
                                        errors: List[FactValidationError]) -> None:
    """Check that intro.visit_reason and today_reason are consistent
    with both the draft's own prior_diagnosis/treatment_history AND
    the ground truth's confirmed treatments.

    Two failure modes this catches:
      (a) draft-internal contradiction (Woods earlier failure):
          visit_reason "low-risk active surveillance" while
          prior_diagnosis.risk_category="high".
      (b) GT-anchored contradiction (Woods current failure):
          visit_reason "active surveillance" while the LLM
          omitted radiation from treatment_history but GT
          (PSH/pathology) confirms the patient is s/p radiation.
    """
    intro = draft.get("intro") or {}
    visit_reason = (intro.get("visit_reason") or "").lower()
    today_reason = (draft.get("today_reason") or "").lower()
    combined = visit_reason + " " + today_reason

    dx = draft.get("prior_diagnosis") or {}
    risk = (dx.get("risk_category") or "")
    risk_lc = risk.strip().lower() if isinstance(risk, str) else ""

    # 1. Risk-category contradiction: visit_reason names a risk level
    # that disagrees with prior_diagnosis.risk_category.
    if risk_lc in ("high", "very-high", "very high"):
        if re.search(r"\b(?:very[\s-]?low[\s-]?risk|low[\s-]?risk|low\s+grade)\b",
                     combined):
            errors.append(FactValidationError(
                "intro.visit_reason", "VISIT_REASON_RISK_MISMATCH",
                f"visit_reason describes 'low-risk' but "
                f"prior_diagnosis.risk_category is {risk!r}",
                found=visit_reason or today_reason,
                expected=risk,
            ))
    if risk_lc in ("low", "very-low", "very low"):
        if re.search(r"\bhigh[\s-]?risk\b", combined):
            errors.append(FactValidationError(
                "intro.visit_reason", "VISIT_REASON_RISK_MISMATCH",
                f"visit_reason describes 'high-risk' but "
                f"prior_diagnosis.risk_category is {risk!r}",
                found=visit_reason or today_reason,
                expected=risk,
            ))

    # 2. Treatment contradiction. Anchor to BOTH draft.treatment_history
    # AND ground truth's confirmed treatments — the LLM can mask the
    # contradiction by omitting the treatment from its draft, but the
    # GT (extracted deterministically from PSH/pathology) is unforgiving.
    th = draft.get("treatment_history") or []
    draft_completed_definitive = {
        e.get("modality") for e in th
        if e.get("status") == "completed"
        and e.get("modality") in {"prostatectomy", "radiation", "brachytherapy",
                                    "focal-therapy", "nephrectomy", "cystectomy"}
    }
    gt_completed_definitive = {
        m for m in (gt.confirmed_treatment_modalities or set())
        if m in {"prostatectomy", "radiation", "brachytherapy",
                  "focal-therapy", "nephrectomy", "cystectomy",
                  "ADT", "chemotherapy"}
    }
    completed_definitive = draft_completed_definitive | gt_completed_definitive
    ongoing_as = any(
        e.get("modality") == "active-surveillance"
        and e.get("status") in ("ongoing", "completed")
        for e in th
    )
    mentions_as = re.search(r"\bactive\s+surveillance\b", combined) is not None
    mentions_post_treatment = re.search(
        r"\b(?:post[\s-]?(?:treatment|prostatectomy|radiation|imrt|xrt|ebrt)|"
        r"after\s+(?:radiation|imrt|prostatectomy|ebrt|xrt|brachy|nephrectomy)|"
        r"s/p\s+(?:imrt|radiation|prostatectomy|nephrectomy|ralp|rrp|rarp))\b",
        combined,
    )

    if mentions_as and completed_definitive and not ongoing_as:
        errors.append(FactValidationError(
            "intro.visit_reason", "VISIT_REASON_TREATMENT_MISMATCH",
            f"visit_reason / today_reason names 'active surveillance' "
            f"but the patient has completed definitive treatment "
            f"{sorted(completed_definitive)!r} (per PSH/pathology). "
            f"The patient is s/p treatment, not on AS.",
            found=visit_reason or today_reason,
            expected=f"post-treatment framing referring to {sorted(completed_definitive)!r}",
        ))
    if (mentions_post_treatment and not completed_definitive
            and not ongoing_as):
        # Less common direction: visit_reason claims post-treatment but
        # neither draft nor GT has any completed treatment. Could be
        # incomplete extraction; use WARN not ERROR.
        errors.append(FactValidationError(
            "intro.visit_reason", "VISIT_REASON_TREATMENT_MISMATCH",
            f"visit_reason describes post-treatment status but no "
            f"completed treatment is recorded",
            found=visit_reason or today_reason,
            severity="WARN",
        ))

    # 3. Missing oncologic treatment in draft. If GT confirms a completed
    # cancer-directed treatment but draft.treatment_history omits it,
    # the HPI will inevitably misframe the patient. ERROR-severity so
    # the LLM is forced to include it.
    missing_oncologic = gt_completed_definitive - draft_completed_definitive
    # Filter to treatments meaningful to surface — surgical-treatment-
    # only entries like nephrectomy aren't always documented as
    # "completed" in PSH-based GT, so be conservative: only require
    # prostate-cancer-directed entries when there's a prostate cancer
    # signal in pathology or prior_diagnosis.
    prostate_signal = (
        "prostate" in (dx.get("primary_dx") or "").lower()
        or "prostate" in (gt.pathology_text or "").lower()
        or bool(gt.gleason_scores)
    )
    pca_treatments = {"prostatectomy", "radiation", "brachytherapy",
                      "focal-therapy", "ADT"}
    if prostate_signal:
        missing_pca = missing_oncologic & pca_treatments
        if missing_pca:
            errors.append(FactValidationError(
                "treatment_history", "TREATMENT_HISTORY_MISSING_KEY_MODALITY",
                f"PSH/pathology confirms the patient is s/p "
                f"{sorted(missing_pca)!r} but treatment_history omits "
                f"it. Add an entry with status='completed' and the "
                f"appropriate modality.",
                expected=sorted(missing_pca),
            ))


def validate_facts(draft: Dict, gt: GroundTruth) -> List[FactValidationError]:
    """Cross-validate a schema-valid HPIDraft against ground truth.

    Returns list of FactValidationError (severity=ERROR or WARN).
    Empty list = factually valid.
    """
    errors: List[FactValidationError] = []
    _validate_intro(draft.get("intro") or {}, gt, errors)
    _validate_psa_trajectory(draft.get("psa_trajectory") or {}, gt, errors)
    _validate_treatment_history(draft.get("treatment_history") or [], gt, errors)
    _validate_prior_diagnosis(draft.get("prior_diagnosis") or {}, gt, errors)
    _validate_procedure_findings(draft.get("procedure_findings") or [], gt, errors)
    _validate_current_regimen(draft.get("current_regimen") or [], gt, errors)
    # Cross-section internal consistency (visit_reason vs the rest)
    _validate_visit_reason_consistency(draft, gt, errors)
    return errors


def is_factually_valid(draft: Dict, gt: GroundTruth) -> bool:
    """True iff no ERROR-severity violations."""
    return not any(e.severity == "ERROR" for e in validate_facts(draft, gt))


def format_fact_errors(errors: List[FactValidationError]) -> str:
    if not errors:
        return "(no fact-validation errors)"
    lines = [f"{len(errors)} fact-validation issue(s):"]
    for e in errors:
        line = f"  - [{e.severity}] {e.path}: [{e.code}] {e.message}"
        if e.expected is not None:
            line += f" (expected: {e.expected})"
        if e.found is not None:
            line += f" (got: {e.found!r})"
        lines.append(line)
    return "\n".join(lines)
