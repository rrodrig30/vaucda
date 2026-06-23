"""
LLM prompt builder + lenient JSON parser for constrained HPI
generation.

The prompt:
  - Instructs the LLM to emit ONLY a JSON object matching the
    HPIDraft schema — no prose, no markdown, no commentary.
  - Embeds the schema's controlled vocabularies inline so the
    LLM knows the exact enum values.
  - Surfaces the deterministic ground truth (PSA Curve, PSH,
    PATHOLOGY, MEDICATIONS, banner) so the LLM has all the
    values it must reference.
  - When called as a retry, embeds the prior validation errors so
    the LLM can correct them precisely.

The parser:
  - Tolerates markdown code fences (```json ... ```)
  - Tolerates leading / trailing prose around the JSON object
  - Extracts the first balanced { ... } span and json.loads() it
  - Returns (draft, parse_error) — never raises
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from .hpi_fact_validator import FactValidationError, GroundTruth
from .hpi_schema import (
    PSA_DIRECTIONS,
    SEX_VALUES,
    TREATMENT_MODALITIES,
    TREATMENT_STATUSES,
    PROCEDURE_TYPES,
    VERIFIED_IN_SOURCES,
    VISIT_TYPES,
    ValidationError,
    UROLOGIC_MEDS,
)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

# Compact schema description embedded in the prompt. We do NOT dump
# the entire Python schema dict (too noisy for the LLM) — we hand-write
# a concise JSON-shape description with allowed enum values inline.

def _schema_block() -> str:
    return f"""\
Required output shape (HPIDraft JSON):

{{
  "intro": {{                                  // REQUIRED
    "name": "<full name from banner>",         // REQUIRED string
    "age": <integer from banner>,              // REQUIRED integer
    "sex": <"male" | "female">,                // REQUIRED, enum
    "visit_type": <one of: {sorted(VISIT_TYPES)}>,  // REQUIRED
    "visit_reason": "<short reason for today>"  // REQUIRED string
  }},
  "prior_diagnosis": {{                        // optional
    "primary_dx": "<diagnosis name>",
    "dx_date": "<YYYY | YYYY-MM | YYYY-MM-DD>",  // ISO format ONLY
    "gleason": "<e.g. 3+3, 3+4, 4+3, 4+4, 4+5>",
    "grade_group": <1-5>,
    "risk_category": "<very-low | low | intermediate | high | null>",
    "verified_in": <one of: {sorted(VERIFIED_IN_SOURCES)}>
  }},
  "treatment_history": [                       // optional array
    {{
      "modality": <one of: {sorted(TREATMENT_MODALITIES)}>,
      "status": <one of: {sorted(TREATMENT_STATUSES)}>,
      "date": "<YYYY | YYYY-MM | YYYY-MM-DD>",
      "verified_in": <one of: {sorted(VERIFIED_IN_SOURCES)}>,
      "narrative_note": "<optional one-clause detail>"
    }}
  ],
  "psa_trajectory": {{                         // optional but include if PSA data exists
    "current_value": <number, ng/mL>,          // MUST be from PSA CURVE
    "current_date": "<YYYY-MM-DD>",            // MUST match the value's date
    "prior_value": <number>,                   // optional, MUST be from PSA CURVE
    "prior_date": "<YYYY-MM-DD>",
    "peak_value": <number>,                    // optional, MUST be from PSA CURVE
    "peak_date": "<YYYY-MM-DD>",
    "direction": <one of: {sorted(PSA_DIRECTIONS)}>,  // REQUIRED if psa_trajectory present
    "narrative_descriptor": "<stable | rising | declining | fluctuating>"
  }},
  "procedure_findings": [                      // optional array
    {{
      "procedure_type": <one of: {sorted(PROCEDURE_TYPES)}>,
      "date": "<YYYY-MM-DD>",                  // MUST match a procedure date in source
      "finding": "<one short clause summarizing the finding>",
      "verified_in": <one of: {sorted(VERIFIED_IN_SOURCES)}>
    }}
  ],
  "current_regimen": [                         // optional array of CURRENT urologic meds
    {{
      "medication": "<generic name>",          // MUST appear in MEDICATIONS section
      "indication": "<BPH | ED | OAB | ADT | etc>",
      "verified_in": "MEDICATIONS"
    }}
  ],
  "interval_status": {{                        // optional
    "last_visit_date": "<YYYY-MM-DD>",
    "summary": "<1-2 sentences anchored to last visit date>",
    "denies": ["<symptom>", ...]
  }},
  "today_reason": "<single sentence reason for today's visit>"  // REQUIRED
}}
"""


def _ground_truth_block(gt: GroundTruth) -> str:
    """Surface the deterministic ground truth the LLM must use."""
    lines: List[str] = [
        "Authoritative ground truth (use these EXACT values — do not invent):",
        "",
        f"BANNER: name={gt.name!r}, age={gt.age}, sex={gt.sex!r}, visit_date={gt.visit_date!r}",
        "",
    ]
    if gt.psa_entries:
        lines.append("PSA CURVE (newest first — every PSA value you cite MUST be in this list):")
        for e in gt.psa_entries[:25]:
            lines.append(f"  {e.value} ng/mL on {e.date}")
        lines.append("")
    if gt.confirmed_treatment_modalities:
        lines.append(
            f"CONFIRMED PRIOR TREATMENTS (from PSH/pathology — only these "
            f"may be cited as 'completed' / 'ongoing'):"
        )
        for m in sorted(gt.confirmed_treatment_modalities):
            lines.append(f"  - {m}")
        lines.append("")
    else:
        lines.append("CONFIRMED PRIOR TREATMENTS: (none — patient is treatment-naive)")
        lines.append("")
    if gt.gleason_scores or gt.grade_groups:
        lines.append("PATHOLOGY FACTS:")
        if gt.gleason_scores:
            lines.append(f"  Gleason scores in pathology: {sorted(gt.gleason_scores)}")
        if gt.grade_groups:
            lines.append(f"  Grade Groups in pathology: {sorted(gt.grade_groups)}")
        lines.append("")
    if gt.medications:
        lines.append("MEDICATIONS in MEDICATIONS section (only meds in this list may "
                     "appear in current_regimen):")
        for m in sorted(gt.medications)[:20]:
            lines.append(f"  - {m}")
        if len(gt.medications) > 20:
            lines.append(f"  ... and {len(gt.medications) - 20} more")
        lines.append("")
    if gt.procedure_dates:
        lines.append("PROCEDURE EVENTS (date → types):")
        for date in sorted(gt.procedure_dates, reverse=True)[:15]:
            types = sorted(gt.procedure_dates[date])
            lines.append(f"  {date}: {types}")
        lines.append("")
    if gt.pathology_text:
        snippet = gt.pathology_text[:500].strip()
        lines.append(f"PATHOLOGY TEXT (excerpt):\n{snippet}")
        lines.append("")
    if gt.psh_text:
        snippet = gt.psh_text[:400].strip()
        lines.append(f"PAST SURGICAL HISTORY (excerpt):\n{snippet}")
        lines.append("")
    return "\n".join(lines)


def _retry_feedback_block(
    schema_errors: List[ValidationError],
    fact_errors: List[FactValidationError],
) -> str:
    """When this is a retry attempt, surface the prior errors so the
    LLM can correct them precisely."""
    if not schema_errors and not fact_errors:
        return ""
    lines = ["YOUR PREVIOUS DRAFT HAD ERRORS — FIX THESE EXACTLY:", ""]
    if schema_errors:
        lines.append("Schema errors:")
        for e in schema_errors:
            line = f"  - {e.path}: [{e.code}] {e.message}"
            if e.expected is not None:
                line += f" (allowed: {e.expected})"
            if e.found is not None:
                line += f" (got: {e.found!r})"
            lines.append(line)
        lines.append("")
    if fact_errors:
        lines.append("Fact-validation errors (the value you cited is NOT in the ground truth):")
        for e in fact_errors:
            line = f"  - [{e.severity}] {e.path}: [{e.code}] {e.message}"
            if e.expected is not None:
                line += f" (allowed: {e.expected})"
            if e.found is not None:
                line += f" (got: {e.found!r})"
            lines.append(line)
        lines.append("")
    lines.append("Re-emit the COMPLETE corrected JSON object. Do NOT explain — output JSON only.")
    return "\n".join(lines)


def build_hpi_json_prompt(
    gt: GroundTruth,
    schema_errors: Optional[List[ValidationError]] = None,
    fact_errors: Optional[List[FactValidationError]] = None,
) -> str:
    """Assemble the prompt for HPI JSON generation.

    If schema_errors / fact_errors are provided, this is a retry —
    the prompt includes the prior errors so the LLM can correct."""

    sections = [
        "You are a clinical documentation assistant producing a STRUCTURED "
        "HPI for a urology clinic note. You will emit ONLY a single JSON "
        "object conforming to the HPIDraft schema below. No prose. No "
        "explanation. No markdown code fences. The first character of "
        "your output MUST be `{` and the last MUST be `}`.",
        "",
        "ABSOLUTE RULES:",
        "  1. EVERY value in the JSON must come from the authoritative "
        "ground truth shown below. Do not invent values.",
        "  2. Every PSA value in psa_trajectory MUST appear in the PSA "
        "CURVE (±0.05 tolerance).",
        "  3. Every treatment in treatment_history MUST be a confirmed "
        "prior treatment OR a logically-implied active-surveillance.",
        "  4. Every medication in current_regimen MUST appear in the "
        "MEDICATIONS list.",
        "  5. Every Gleason / Grade Group cited MUST appear in PATHOLOGY.",
        "  6. The intro name/age/sex MUST match the banner exactly.",
        "  7. PSA direction MUST be consistent with values: "
        "if current > prior then direction is 'increased'; "
        "if current < prior then 'decreased'; "
        "if approximately equal then 'stable'.",
        "  8. Dates MUST be ISO format (YYYY or YYYY-MM or YYYY-MM-DD). "
        "Do NOT use MM/DD/YYYY or 'Feb 2, 2026'.",
        "  9. If a section has no data (e.g., patient is treatment-naive), "
        "OMIT the field or set it to null. Do NOT invent placeholder content.",
        "  10. The 'today_reason' field must reflect the documented reason "
        "for THIS visit (chart-prep — patient has not been interviewed today).",
        "",
        _schema_block(),
        "",
        _ground_truth_block(gt),
        "",
        _retry_feedback_block(schema_errors or [], fact_errors or []),
        "",
        "Output the JSON object now. Do NOT wrap it in code fences. "
        "Do NOT include any text before or after the JSON.",
    ]
    return "\n".join(s for s in sections if s)


# ---------------------------------------------------------------------------
# Lenient JSON parser
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$",
                       re.IGNORECASE | re.MULTILINE)


def parse_hpi_json(raw: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Parse the LLM output into an HPIDraft dict.

    Returns (draft, parse_error). One of the two is non-None.

    Tolerances:
      - Markdown code fences (```json / ```)
      - Leading/trailing prose around the JSON object
      - Trailing commas (json.loads is strict; we don't fix those here —
        the LLM is instructed to emit strict JSON)
    """
    if not raw or not raw.strip():
        return None, "empty LLM output"

    text = _FENCE_RE.sub("", raw.strip()).strip()

    # Find the first '{' and the matching '}' via balanced-brace scan.
    start = text.find("{")
    if start < 0:
        return None, "no '{' found in LLM output"

    # Walk forward, counting depth, ignoring braces inside strings.
    depth = 0
    in_string = False
    escape = False
    end = -1
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end < 0:
        return None, "unmatched '{' in LLM output (no balanced closing brace)"

    blob = text[start:end + 1]
    try:
        draft = json.loads(blob)
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"

    if not isinstance(draft, dict):
        return None, f"top-level JSON is {type(draft).__name__}, not object"

    return draft, None
