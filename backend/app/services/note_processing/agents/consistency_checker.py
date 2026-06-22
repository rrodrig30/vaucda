"""
Stage-1 Consistency Checker

A second-pass LLM agent that reads the FULLY ASSEMBLED Stage-1 note
and returns a strict JSON list of inconsistencies. The note builder
then applies the corrections deterministically.

The checker's job is narrow: catch LLM-judgment failures the
deterministic post-processors fundamentally can't (CC/HPI topic
mismatch, internal contradictions, date-out-of-order PSA claims,
hallucinated treatment-without-PSH-support). It does NOT generate
prose. It produces a JSON payload like:

    [
      {
        "issue": "TREATMENT_NOT_IN_PSH",
        "evidence": "underwent radical prostatectomy in 2024",
        "action": "remove_sentence",
        "sentence": "He underwent radical prostatectomy in 2024."
      },
      {
        "issue": "INTERNAL_CONTRADICTION",
        "evidence": "denies history of urologic cancers ... renal cell carcinoma",
        "action": "flag_only"
      }
    ]

The action vocabulary is intentionally tiny — the LLM CANNOT rewrite
prose. It can:
    remove_sentence  — delete a specific sentence from the HPI/Assessment
    replace_value    — substitute one exact value with another
    flag_only        — surface to provider but auto-edit nothing

Safety caps:
  - max 2 sentence removals per note
  - max 1 value replacement per note
  - any LLM output that doesn't parse as valid JSON is discarded silently
  - any action that targets a sentence not present in the note is dropped

The checker reads the same deterministic ground-truth blocks the HPI
agent built so it has authoritative facts to compare against.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from ..llm_helper import synthesize_with_llm

if TYPE_CHECKING:
    from app.services.llm_config_manager import LLMTaskConfig

logger = logging.getLogger(__name__)


ALLOWED_ISSUES = {
    "CC_HPI_TOPIC_MISMATCH",     # HPI primary topic != CC
    "TREATMENT_NOT_IN_PSH",      # HPI claims s/p X but PSH lacks X
    "INTERNAL_CONTRADICTION",    # HPI both denies and asserts same condition
    "PSA_DATE_OUT_OF_ORDER",     # HPI presents PSA dates non-chronologically
    "PSA_VALUE_NOT_IN_CURVE",    # HPI cites a PSA value not in PSA Curve
    "SEX_PRONOUN_MISMATCH",      # HPI uses pronouns inconsistent with Sex banner
    "FRAGMENT_SENTENCE",         # Trailing/orphan sentence with no clinical content
    "STALE_INTERVAL_SYMPTOM",    # Subjective claim ("reports stable") without source-date anchor for a pre-visit chart prep
}

ALLOWED_ACTIONS = {"remove_sentence", "replace_value", "flag_only"}

MAX_REMOVE_SENTENCE = 2
MAX_REPLACE_VALUE = 1


@dataclass
class ConsistencyFinding:
    """One issue surfaced by the checker."""
    issue: str
    evidence: str
    action: str
    sentence: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    section: str = "HPI"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue": self.issue,
            "evidence": self.evidence,
            "action": self.action,
            "sentence": self.sentence,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "section": self.section,
        }


@dataclass
class ConsistencyResult:
    """All findings from one checker pass + the applied note."""
    findings: List[ConsistencyFinding] = field(default_factory=list)
    applied_note: str = ""
    applied_actions: int = 0
    flag_only_count: int = 0


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_CHECKER_INSTRUCTIONS = """\
You are a clinical-note consistency checker. You are given a fully
assembled Stage-1 urology note. Your ONLY job is to find specific,
verifiable inconsistencies and return them as a JSON array. You do
NOT write prose. You do NOT add information. You do NOT correct
grammar.

Return a JSON array. Each element is an object with these fields:

  issue       : exactly one of the issue codes listed below
  evidence    : short quote from the note showing the problem (<200 chars)
  action      : exactly one of {remove_sentence, replace_value, flag_only}
  sentence    : (only for remove_sentence) the EXACT sentence to delete,
                copied verbatim from the note (including trailing period)
  old_value   : (only for replace_value) the exact substring to replace
  new_value   : (only for replace_value) the exact substring to use
  section     : the section the problem is in (default "HPI")

Allowed issue codes — find ONLY these:

  CC_HPI_TOPIC_MISMATCH
    The HPI's primary topic does not match the CC. Example: CC is
    "bladder cancer" but HPI focuses on nasopharyngeal carcinoma.
    Action: flag_only (do NOT remove sentences — let provider review).

  TREATMENT_NOT_IN_PSH
    The HPI claims the patient underwent / completed / is s/p a
    definitive treatment (radiation, prostatectomy, brachytherapy,
    cystectomy, nephrectomy, focal therapy) but the PAST SURGICAL
    HISTORY section lists no matching procedure.
    Action: remove_sentence (the offending sentence).

  INTERNAL_CONTRADICTION
    Two sentences in the HPI contradict each other (e.g., "denies
    history of urologic cancers" + "has a 4 cm renal mass most likely
    renal cell carcinoma"; or "completed treatment" + "remains on
    active surveillance").
    Action: flag_only.

  PSA_DATE_OUT_OF_ORDER
    The HPI presents PSA dates non-chronologically. For example,
    "PSA increased from 7.19 (August 2025) to 6.91 (October 2025)"
    when October is AFTER August but the value DECREASED. Verify
    against the PSA CURVE section.
    Action: flag_only.

  PSA_VALUE_NOT_IN_CURVE
    The HPI cites a PSA value as "ng/mL" that does not appear in
    the PSA CURVE section (±0.05 tolerance).
    Action: replace_value (replace with the current PSA from the
    curve), OR flag_only if you cannot determine the correct value.

  SEX_PRONOUN_MISMATCH
    The HPI uses "he/his/him" for a banner that says "Sex: FEMALE",
    or "she/her" for "Sex: MALE".
    Action: flag_only.

  FRAGMENT_SENTENCE
    An HPI sentence has no clinical content — just a label (e.g.,
    "Radical retropubic prostatectomy (1999)" with no surrounding
    narrative), or starts with "This represents..." / "Note that..."
    with no antecedent.
    Action: remove_sentence.

  STALE_INTERVAL_SYMPTOM
    The HPI states the patient "reports" a subjective symptom as if
    interviewed today, but the note is a pre-visit chart prep and the
    statement is not anchored to a source date.
    Action: flag_only (don't auto-edit; let provider confirm).

CRITICAL RULES:

1. Return ONLY the JSON array. No prose. No markdown code fences.
   No explanation. The first character of your output must be "["
   and the last must be "]".
2. If there are no inconsistencies, return [].
3. For remove_sentence: the "sentence" field MUST be the exact
   verbatim substring of the note. If the sentence does not match
   character-for-character, your action will be dropped.
4. For replace_value: old_value MUST appear verbatim in the note.
5. Do NOT flag stylistic issues. Do NOT flag missing data. ONLY
   flag the issues listed above.
6. Do NOT remove sentences that contain pertinent positives or
   negatives ("denies hematuria", "reports nocturia") even if you
   suspect they may be stale — use STALE_INTERVAL_SYMPTOM with
   flag_only for those.
7. Maximum 4 findings total. If you find more, return the 4 most
   clinically impactful.
"""


def _build_prompt(stage1_note: str, authoritative_facts: Optional[str]) -> str:
    """Assemble the full checker prompt with the note + ground truth."""
    parts = [_CHECKER_INSTRUCTIONS]
    if authoritative_facts and authoritative_facts.strip():
        parts.append(
            "\n=== AUTHORITATIVE GROUND TRUTH (from deterministic extractors) ===\n"
            + authoritative_facts.strip()
            + "\n=== END GROUND TRUTH ===\n"
        )
    parts.append(
        "\n=== STAGE-1 NOTE TO CHECK ===\n"
        + stage1_note.strip()
        + "\n=== END NOTE ===\n"
    )
    parts.append(
        "\nReturn the JSON array now. Output the array and nothing else.\n"
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# JSON parsing (lenient)
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _parse_findings(raw: str) -> List[ConsistencyFinding]:
    """Parse the checker LLM output into ConsistencyFinding objects.

    Tolerates:
      - Markdown code fences wrapping the JSON
      - Leading/trailing prose (we extract the first [...] bracket span)

    Returns [] on any parse failure — silent fail by design. We never
    raise out of the checker, since malformed output should never
    block note rendering.
    """
    if not raw or not raw.strip():
        return []

    text = _FENCE_RE.sub("", raw.strip())
    # Find the first '[' and the matching ']'.
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        logger.warning("Consistency checker: no JSON array in output")
        return []
    blob = text[start:end + 1]

    try:
        items = json.loads(blob)
    except json.JSONDecodeError as e:
        logger.warning(f"Consistency checker: JSON parse failed: {e}")
        return []

    if not isinstance(items, list):
        logger.warning("Consistency checker: top level not a list")
        return []

    out: List[ConsistencyFinding] = []
    for item in items[:4]:  # safety cap on findings
        if not isinstance(item, dict):
            continue
        issue = item.get("issue", "").strip()
        action = item.get("action", "").strip()
        if issue not in ALLOWED_ISSUES:
            continue
        if action not in ALLOWED_ACTIONS:
            continue
        out.append(ConsistencyFinding(
            issue=issue,
            evidence=str(item.get("evidence", "") or "")[:300],
            action=action,
            sentence=item.get("sentence") or None,
            old_value=item.get("old_value") or None,
            new_value=item.get("new_value") or None,
            section=str(item.get("section", "HPI") or "HPI"),
        ))
    return out


# ---------------------------------------------------------------------------
# Action application
# ---------------------------------------------------------------------------

# Safety gate: remove_sentence ONLY auto-applies for issue types that
# are clearly safe to delete. For higher-stakes issues (treatment
# claims, contradictions), downgrade auto-edit to flag_only — those
# need provider review, not silent deletion of potentially-real
# clinical content.
_AUTO_REMOVE_ISSUES = {
    "FRAGMENT_SENTENCE",
}
# Issues that the LLM may LABEL as remove_sentence but we downgrade
# to flag_only because the cost of an incorrect removal is high:
#   - TREATMENT_NOT_IN_PSH: the PSH may simply not list the procedure;
#     the HPI mention could still be correct.
#   - CC_HPI_TOPIC_MISMATCH: dropping HPI sentences risks gutting the
#     entire clinical narrative.
#   - INTERNAL_CONTRADICTION: provider has to decide which side is right.
_FORCE_FLAG_ONLY_ISSUES = {
    "TREATMENT_NOT_IN_PSH",
    "CC_HPI_TOPIC_MISMATCH",
    "INTERNAL_CONTRADICTION",
    "STALE_INTERVAL_SYMPTOM",
    "SEX_PRONOUN_MISMATCH",
    "PSA_DATE_OUT_OF_ORDER",
}


# Strict numeric-value validator. Replace_value is only applied when
# the new_value matches a clinical-value shape (number + optional unit).
# This blocks the LLM from substituting prompt text or arbitrary prose
# as a "replacement value".
_VALUE_SHAPE_RE = re.compile(
    r"^\s*[<>]?\s*\d+(?:\.\d+)?\s*"
    r"(?:ng/mL|ng/dL|mg/dL|mg/dl|U/L|mEq/L|mIU/mL|nmol/L|%|H|L)?\s*$",
    re.IGNORECASE,
)


def _apply_actions(note: str, findings: List[ConsistencyFinding]) -> tuple[str, int, int]:
    """Apply remove_sentence / replace_value actions to the note.

    Returns (modified_note, n_applied, n_flag_only).

    Safety gates:
      - remove_sentence only fires for issue types in _AUTO_REMOVE_ISSUES
      - higher-stakes issues are auto-downgraded to flag_only
      - replace_value only fires when new_value matches _VALUE_SHAPE_RE
        (number + optional unit) — this blocks the LLM from substituting
        prose or prompt-text as the replacement
      - if a sentence isn't present verbatim, action is skipped
      - if old_value isn't present, action is skipped
      - cap on remove (MAX_REMOVE_SENTENCE) and replace (MAX_REPLACE_VALUE)
    """
    n_applied = 0
    n_flag_only = 0
    n_remove = 0
    n_replace = 0

    out = note
    for f in findings:
        # Downgrade high-stakes auto-edit attempts to flag_only.
        effective_action = f.action
        if effective_action == "remove_sentence" and f.issue not in _AUTO_REMOVE_ISSUES:
            effective_action = "flag_only"
        if effective_action == "replace_value" and f.issue in _FORCE_FLAG_ONLY_ISSUES:
            effective_action = "flag_only"

        if effective_action == "flag_only":
            n_flag_only += 1
            continue

        if effective_action == "remove_sentence":
            if n_remove >= MAX_REMOVE_SENTENCE:
                continue
            if not f.sentence or not isinstance(f.sentence, str):
                continue
            target = f.sentence.strip()
            if not target:
                continue
            if target not in out:
                logger.info(
                    f"Consistency checker: target sentence not found verbatim "
                    f"({f.issue!r}): {target[:80]!r}"
                )
                continue
            # Drop the sentence and clean up surrounding whitespace.
            out = out.replace(target, "", 1)
            out = re.sub(r"  +", " ", out)
            out = re.sub(r"\s+([.,;:])", r"\1", out)
            n_remove += 1
            n_applied += 1
            continue

        if effective_action == "replace_value":
            if n_replace >= MAX_REPLACE_VALUE:
                continue
            if not f.old_value or not f.new_value:
                continue
            if f.old_value not in out:
                continue
            # Reject replacement values that don't match a clinical
            # numeric shape — the LLM has been observed substituting
            # prompt-text ("PSA CURVE section value (+/-0.05 tolerance)")
            # as the new_value, which would corrupt the note.
            if not _VALUE_SHAPE_RE.match(f.new_value):
                logger.info(
                    f"Consistency checker: rejected non-numeric new_value: "
                    f"{f.new_value!r}"
                )
                continue
            # Also: old_value must match the same shape (we're only
            # replacing numeric clinical values, not arbitrary text).
            if not _VALUE_SHAPE_RE.match(f.old_value):
                continue
            out = out.replace(f.old_value, f.new_value, 1)
            n_replace += 1
            n_applied += 1
            continue

    return out, n_applied, n_flag_only


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_consistency_check(
    stage1_note: str,
    authoritative_facts: Optional[str] = None,
    task_config: Optional["LLMTaskConfig"] = None,
) -> ConsistencyResult:
    """Run the second-pass consistency check on an assembled Stage-1 note.

    Returns a ConsistencyResult with the (possibly modified) note, the
    list of findings, and counts of applied / flag-only actions.

    Failure modes are silent: any LLM error, JSON-parse error, or
    schema violation results in the unmodified note being returned. The
    checker never blocks note rendering.
    """
    if not stage1_note or not stage1_note.strip():
        return ConsistencyResult(applied_note=stage1_note or "")

    prompt = _build_prompt(stage1_note, authoritative_facts)

    try:
        raw = synthesize_with_llm(
            prompt=prompt,
            temperature=0.0,
            task_config=task_config,
        )
    except Exception as e:
        logger.warning(f"Consistency checker LLM call failed: {e}")
        return ConsistencyResult(applied_note=stage1_note)

    findings = _parse_findings(raw)
    if not findings:
        return ConsistencyResult(applied_note=stage1_note)

    modified, n_applied, n_flag_only = _apply_actions(stage1_note, findings)
    return ConsistencyResult(
        findings=findings,
        applied_note=modified,
        applied_actions=n_applied,
        flag_only_count=n_flag_only,
    )
