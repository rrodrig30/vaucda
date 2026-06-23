"""
HPI agent v2 — constrained-JSON generation orchestrator.

Pipeline:
  1. Build GroundTruth from deterministic extractors
  2. Build LLM prompt embedding schema + ground truth
  3. Call LLM
  4. Parse JSON (lenient — strips fences, prose preamble)
  5. Validate JSON against schema
  6. Validate JSON against ground truth (cross-check every cited value)
  7. If errors at any step: retry with feedback (max 2 retries)
  8. If all retries fail: fall back to caller-supplied v1 HPI text,
     or a minimal deterministic skeleton if no fallback provided
  9. On success: render JSON → clinical prose via deterministic
     templates (cannot hallucinate)

Returns an HPIv2Result with the final prose AND a structured audit
trail of every validation attempt — so the caller can log, alert,
or surface findings to a provider review panel.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .hpi_fact_validator import (
    FactValidationError,
    GroundTruth,
    PSAEntry,
    format_fact_errors,
    validate_facts,
)
from .hpi_json_prompt import build_hpi_json_prompt, parse_hpi_json
from .hpi_renderer import render_full_hpi
from .hpi_schema import ValidationError, format_errors, validate_hpi_draft

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class AttemptAudit:
    """One attempt at LLM → parse → validate."""
    attempt_number: int
    parse_error: Optional[str] = None
    schema_errors: List[ValidationError] = field(default_factory=list)
    fact_errors: List[FactValidationError] = field(default_factory=list)
    draft_accepted: bool = False


@dataclass
class HPIv2Result:
    """Outcome of the constrained-HPI pipeline."""
    hpi_text: str                                  # final rendered prose
    used_fallback: bool                            # True if v2 failed
    fallback_reason: Optional[str] = None          # why v2 failed (if it did)
    accepted_draft: Optional[Dict] = None          # JSON draft used to render
    attempts: List[AttemptAudit] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ground-truth builder
# ---------------------------------------------------------------------------

# Map text tokens to canonical modality enum
_MODALITY_FROM_TEXT = {
    r"\b(?:radical\s+)?prostatectomy\b|\bRALP\b|\bRARP\b|\bRRP\b": "prostatectomy",
    r"\b(?:radiation|radiotherapy|EBRT|XRT|IMRT|SBRT|IGRT)\b": "radiation",
    r"\bbrachytherapy\b|\bseed\s+implant": "brachytherapy",
    r"\bHIFU\b|\bcryotherapy\b|\bcryoablation\b|\bfocal\s+therapy\b": "focal-therapy",
    r"\bADT\b|\bandrogen\s+deprivation\b|\bleuprolide\b|\blupron\b|\beligard\b|\bdegarelix\b|\bgoserelin\b|\brelugolix\b": "ADT",
    r"\bTURP\b|\btransurethral\s+resection.{0,20}prostate\b": "TURP",
    r"\bTURBT\b|\btransurethral\s+resection.{0,20}bladder\b": "TURBT",
    r"\bnephrectomy\b": "nephrectomy",
    r"\bcystectomy\b": "cystectomy",
    r"\bureteroscopy\b|\bURS\b": "ureteroscopy",
    r"\borchiectomy\b": "orchiectomy",
    r"\bvaricocelectomy\b": "varicocelectomy",
    r"\bhydrocelectomy\b|\bspermatocelectomy\b": "hydrocelectomy",
}


def _extract_psa_entries(psa_text: str) -> List[PSAEntry]:
    """Parse PSA Curve text into PSAEntry list.

    Accepts the existing extract_psa output format:
      '[r] Feb 02, 2026 15:18    5.55 H'
      'Feb 02, 2026 15:18: 5.55'
    Returns entries sorted newest-first.
    """
    from datetime import datetime as _dt
    entries: List[PSAEntry] = []
    if not psa_text:
        return entries
    date_re = re.compile(
        r"([A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})"
    )
    for raw_line in psa_text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if not re.search(r"\d", line):
            continue
        m_date = date_re.search(line)
        if not m_date:
            continue
        # Last decimal on the line is the PSA value
        nums = re.findall(r"\d+\.\d+", line)
        if not nums:
            continue
        try:
            value = float(nums[-1])
        except ValueError:
            continue
        try:
            dt = _dt.strptime(m_date.group(1).replace(",", ""),
                              "%b %d %Y")
            iso = dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
        entries.append(PSAEntry(value=value, date=iso))
    # Sort newest first
    entries.sort(key=lambda e: e.date, reverse=True)
    # Dedup adjacent identical entries
    seen = set()
    out = []
    for e in entries:
        key = (e.value, e.date)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _extract_gleason_grade_groups(pathology_text: str) -> tuple:
    """Pull all Gleason / Grade Group values from pathology text."""
    gleasons = set()
    ggs = set()
    if not pathology_text:
        return gleasons, ggs
    for m in re.finditer(r"Gleason(?:'s)?\s+(?:Score\s+|Grade\s+)?(\d)\s*\+\s*(\d)",
                         pathology_text, re.IGNORECASE):
        gleasons.add(f"{m.group(1)}+{m.group(2)}")
    for m in re.finditer(r"(?:Grade\s+Group|GG)\s*(\d)",
                         pathology_text, re.IGNORECASE):
        try:
            ggs.add(int(m.group(1)))
        except ValueError:
            pass
    return gleasons, ggs


def _extract_medications(medications_text: str) -> set:
    """Pull lowercased medication names from a MEDICATIONS section."""
    meds = set()
    if not medications_text:
        return meds
    for line in medications_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # "1. Tamsulosin Hcl 0.4Mg Cap - Take ..."
        m = re.match(r"\s*\d+\.\s*([A-Za-z][A-Za-z\s/\-]+?)\s+(?:\d|Tab|Cap|"
                     r"Inj|Soln|Susp|Gel|Patch|Cream|Spray|Pwdr|Tablet)",
                     line, re.IGNORECASE)
        if m:
            name = m.group(1).strip().lower()
            # Take first word as the generic root
            root = name.split()[0]
            meds.add(root)
        else:
            # Fall back: take first word of the line after stripping number prefix
            cleaned = re.sub(r"^\s*\d+\.\s*", "", line)
            first_word = cleaned.split()[0] if cleaned.split() else ""
            if first_word and first_word.isalpha() and len(first_word) > 2:
                meds.add(first_word.lower())
    return meds


def _extract_confirmed_modalities(psh_text: str, pathology_text: str,
                                  pmh_text: str) -> set:
    """Scan PSH + pathology + PMH for canonical treatment modalities."""
    modalities = set()
    blob = " ".join([psh_text or "", pathology_text or "", pmh_text or ""])
    for pattern, modality in _MODALITY_FROM_TEXT.items():
        if re.search(pattern, blob, re.IGNORECASE):
            modalities.add(modality)
    return modalities


def _extract_procedure_dates(procedure_findings) -> dict:
    """Convert clinical_timeline.ProcedureFinding list into a
    dict mapping ISO date → set of procedure types."""
    result: Dict[str, set] = {}
    if not procedure_findings:
        return result
    for pf in procedure_findings:
        date_key = getattr(pf, "date_key", "") or ""
        proc = getattr(pf, "procedure", "")
        if not date_key or not proc:
            continue
        result.setdefault(date_key, set()).add(proc)
    return result


def build_ground_truth(
    patient_name: str = "",
    patient_age: int = 0,
    patient_sex: str = "",
    visit_date: str = "",
    psa_data: str = "",
    psh_text: str = "",
    pmh_text: str = "",
    pathology_text: str = "",
    medications_text: str = "",
    imaging_text: str = "",
    procedure_findings: Optional[List] = None,
    treatment_naive: bool = True,
) -> GroundTruth:
    """Build a GroundTruth from existing-extractor outputs."""
    gleasons, ggs = _extract_gleason_grade_groups(pathology_text)
    return GroundTruth(
        name=patient_name,
        age=int(patient_age) if patient_age else 0,
        sex=patient_sex.lower() if patient_sex else "",
        visit_date=visit_date,
        psa_entries=_extract_psa_entries(psa_data),
        confirmed_treatment_modalities=_extract_confirmed_modalities(
            psh_text, pathology_text, pmh_text,
        ),
        treatment_naive=treatment_naive,
        pathology_text=pathology_text or "",
        gleason_scores=gleasons,
        grade_groups=ggs,
        psh_text=psh_text or "",
        pmh_text=pmh_text or "",
        medications=_extract_medications(medications_text),
        procedure_dates=_extract_procedure_dates(procedure_findings),
        imaging_text=imaging_text or "",
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

LLMCallable = Callable[[str], str]  # prompt → raw output


def generate_hpi_v2(
    gt: GroundTruth,
    llm_call: LLMCallable,
    max_retries: int = 2,
    v1_fallback_text: Optional[str] = None,
) -> HPIv2Result:
    """Generate an HPI via constrained-JSON pipeline.

    Args:
      gt:               GroundTruth assembled from deterministic extractors
      llm_call:         function (prompt: str) -> raw LLM output (str).
                        Caller wires this to whatever LLM provider they use.
      max_retries:      how many retry attempts after the first failure
                        (default 2 → up to 3 LLM calls total)
      v1_fallback_text: HPI text from the legacy free-text agent. Used
                        only if v2 cannot produce a valid draft after
                        all retries. Pass None to fall back to a
                        deterministic skeleton instead.

    Returns:
      HPIv2Result with the final hpi_text and a complete audit trail.
    """
    attempts: List[AttemptAudit] = []
    schema_errors: List[ValidationError] = []
    fact_errors: List[FactValidationError] = []

    for attempt_n in range(max_retries + 1):
        audit = AttemptAudit(attempt_number=attempt_n + 1)

        prompt = build_hpi_json_prompt(
            gt,
            schema_errors=schema_errors if attempt_n > 0 else None,
            fact_errors=fact_errors if attempt_n > 0 else None,
        )

        try:
            raw = llm_call(prompt)
        except Exception as e:
            logger.warning(f"HPI v2 LLM call failed (attempt {attempt_n + 1}): {e}")
            audit.parse_error = f"LLM call exception: {e}"
            attempts.append(audit)
            continue

        draft, parse_err = parse_hpi_json(raw or "")
        if parse_err:
            audit.parse_error = parse_err
            attempts.append(audit)
            _dump_failure(gt, attempt_n + 1, "parse_error", parse_err, raw)
            # Reset errors for next retry (parse failure → no schema/fact info)
            schema_errors = []
            fact_errors = []
            continue

        schema_errors = validate_hpi_draft(draft)
        audit.schema_errors = list(schema_errors)
        if schema_errors:
            attempts.append(audit)
            _dump_failure(gt, attempt_n + 1, "schema_errors",
                          "; ".join(f"{e.path}:{e.code}" for e in schema_errors), raw)
            fact_errors = []  # don't run fact validator on schema-invalid draft
            continue

        fact_errors = validate_facts(draft, gt)
        # ERROR-severity only — WARN doesn't block
        blocking_fact_errors = [e for e in fact_errors if e.severity == "ERROR"]
        audit.fact_errors = list(fact_errors)
        if blocking_fact_errors:
            fact_errors = blocking_fact_errors  # only resurface ERRORs in retry
            attempts.append(audit)
            _dump_failure(gt, attempt_n + 1, "fact_errors",
                          "; ".join(f"{e.path}:{e.code}" for e in blocking_fact_errors), raw)
            continue

        # ---- ACCEPTED ----
        audit.draft_accepted = True
        attempts.append(audit)
        hpi_text = render_full_hpi(draft)
        return HPIv2Result(
            hpi_text=hpi_text,
            used_fallback=False,
            accepted_draft=draft,
            attempts=attempts,
        )

    # All retries exhausted → fall back
    fallback_reason = _summarize_failure(attempts)
    fallback_text = v1_fallback_text or _deterministic_skeleton_fallback(gt)
    return HPIv2Result(
        hpi_text=fallback_text,
        used_fallback=True,
        fallback_reason=fallback_reason,
        accepted_draft=None,
        attempts=attempts,
    )


def _dump_failure(gt, attempt_n: int, kind: str, detail: str, raw: str) -> None:
    """Optional debug dump of failing LLM output. Gated by VAUCDA_HPI_V2_DEBUG=1.

    Appends one block per failure to logs/hpi_v2_failures.log so we can inspect
    what the LLM actually emitted vs. what the validator rejected."""
    if os.environ.get("VAUCDA_HPI_V2_DEBUG", "0") != "1":
        return
    try:
        dump_path = Path(os.environ.get("VAUCDA_HPI_V2_DEBUG_FILE",
                                         "logs/hpi_v2_failures.log"))
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        with dump_path.open("a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"PATIENT: {gt.name}  ATTEMPT {attempt_n}  KIND={kind}\n")
            f.write(f"DETAIL: {detail}\n")
            f.write(f"{'-'*80}\nRAW LLM OUTPUT (len={len(raw or '')}):\n")
            f.write(raw or "<empty>")
            f.write(f"\n{'='*80}\n")
    except Exception as _e:
        logger.warning(f"HPI v2 debug dump failed: {_e}")


def _summarize_failure(attempts: List[AttemptAudit]) -> str:
    """Build a one-line summary of why v2 failed."""
    if not attempts:
        return "no attempts made"
    last = attempts[-1]
    if last.parse_error:
        return f"all {len(attempts)} attempts failed (last: parse error: {last.parse_error[:80]})"
    if last.schema_errors:
        codes = sorted({e.code for e in last.schema_errors})
        return f"all {len(attempts)} attempts failed (schema errors: {codes})"
    if last.fact_errors:
        codes = sorted({e.code for e in last.fact_errors if e.severity == 'ERROR'})
        return f"all {len(attempts)} attempts failed (fact errors: {codes})"
    return f"all {len(attempts)} attempts failed"


def _deterministic_skeleton_fallback(gt: GroundTruth) -> str:
    """Render a minimal HPI from ground truth alone — no LLM needed.

    Used only when v2 fails and no v1 fallback is provided. Guaranteed
    to be factually accurate (only contains ground-truth values) but
    very terse."""
    parts: List[str] = []
    if gt.name and gt.age and gt.sex:
        parts.append(f"{gt.name} is a {gt.age}-year-old {gt.sex} who returns for urology follow-up.")
    if gt.confirmed_treatment_modalities:
        treatments = ", ".join(sorted(gt.confirmed_treatment_modalities))
        parts.append(f"Confirmed prior urologic treatments: {treatments}.")
    if gt.psa_entries:
        cur = gt.psa_entries[0]
        line = f"Most recent PSA {cur.value} ng/mL on {cur.date}"
        if len(gt.psa_entries) >= 2:
            prior = gt.psa_entries[1]
            line += f" (prior: {prior.value} ng/mL on {prior.date})"
        parts.append(line + ".")
    if gt.gleason_scores or gt.grade_groups:
        bits = []
        if gt.gleason_scores:
            bits.append(f"Gleason {'/'.join(sorted(gt.gleason_scores))}")
        if gt.grade_groups:
            bits.append(f"Grade Group {'/'.join(str(g) for g in sorted(gt.grade_groups))}")
        parts.append("Pathology: " + ", ".join(bits) + ".")
    if not parts:
        return "Urology follow-up — see source for clinical details."
    return " ".join(parts)
