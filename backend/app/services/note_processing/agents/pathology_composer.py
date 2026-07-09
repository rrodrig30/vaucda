"""LLM-forward Pathology composer with a completeness-repair loop.

The regex pathology extractor (extract_pathology) misses most of the report:
across a 52-case tumor-clinic batch the rendered PATHOLOGY section carried only
46% of the documented findings, and it's prostate-shaped (missed penile SCC,
renal-cell histology, etc.). A verbatim/grounding check can't help — omissions
are invisible to it.

This composer inverts that:
  1. Build a pathology-focused context from the WHOLE chart (not the regex
     slice), so no report is hidden from the model.
  2. The LLM composes an organ-appropriate PATHOLOGY section for every specimen
     and every cancer.
  3. COMPLETENESS-REPAIR LOOP: the deterministic organ-agnostic finding ledger
     (eval-independent copy in gu pathology_findings) tells us exactly which
     documented findings the draft omitted; we re-prompt with that explicit
     checklist and loop until covered. The model doesn't have to self-remember
     — the ledger is the checklist.
  4. Grounding is reported against the full-chart finding set (fabrication /
     wrong-grade guard).

Safe-degrade: on any error or when disabled (VAUCDA_PATH_COMPOSER=0) the caller
falls back to the existing synthesize_pathology.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Callable, Optional, Set

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], str]

# Lines that carry pathology; a block is captured with a few lines of context.
_PATH_LINE = re.compile(
    r"gleason|grade\s+group|\bGG[1-5]\b|adenocarcinoma|carcinoma|urothelial|"
    r"transitional\s+cell|renal\s+cell|\bRCC\b|clear[\s-]cell|papillary|"
    r"chromophobe|squamous\s+cell|seminoma|germ\s+cell|sarcomatoid|"
    r"specimen|biopsy|prostatectomy|\bTURBT\b|nephrectomy|orchiectomy|"
    r"\bmargin|extraprostatic|seminal\s+vesicle|lymphovascular|perineural|"
    r"muscularis|carcinoma\s+in\s+situ|\bCIS\b|\bASAP\b|atypical\s+small|"
    r"Fuhrman|ISUP|nuclear\s+grade|\bp?[cp]?T[0-4]\b|histolog|patholog",
    re.IGNORECASE)


# The actual DIAGNOSIS lines (grade / histology / stage) — never truncate these
# out. A chart can have hundreds of generic "biopsy"/"specimen"/"pathology"
# keyword lines that fill the budget before the real report (FRAGA).
_PATH_FINDING_LINE = re.compile(
    r"gleason|grade\s+group|adenocarcinoma|urothelial\s+carcinoma|"
    r"transitional\s+cell|renal\s+cell\s+carcinoma|\bRCC\b|clear[\s-]cell|"
    r"chromophobe|squamous\s+cell\s+carcinoma|\bseminoma\b|germ\s+cell|"
    r"sarcomatoid|Fuhrman|ISUP|\bp?[cp]?T[0-4][a-d]?\b|myelolipoma",
    re.IGNORECASE)


def build_pathology_context(chart: str, max_chars: int = 22000) -> str:
    """Pathology-bearing regions (line + neighbors) from the whole chart.

    Two-pass so the real report is never truncated out: FINDING lines (grade /
    histology / stage) are included first with wider context, then the broader
    pathology-keyword lines fill the remaining budget."""
    if not chart:
        return ""
    lines = chart.splitlines()

    def _blocks(regex, before, after):
        keep = set()
        for i, ln in enumerate(lines):
            if regex.search(ln):
                for j in range(max(0, i - before), min(len(lines), i + after)):
                    keep.add(j)
        return keep

    finding = _blocks(_PATH_FINDING_LINE, 3, 6)   # priority: real diagnoses
    broad = _blocks(_PATH_LINE, 2, 4) - finding    # context: everything else
    if not finding and not broad:
        return ""

    def _render(idxs):
        out, prev = [], -2
        for i in sorted(idxs):
            if i != prev + 1:
                out.append("...")
            out.append(lines[i])
            prev = i
        return "\n".join(out)

    ctx = _render(finding)
    if len(ctx) < max_chars and broad:
        ctx += "\n...\n" + _render(broad)
    return ctx[:max_chars]


def _findings(text: str) -> Set[str]:
    # Reuse the eval ledger when available; fall back to a minimal local set.
    try:
        from ..pathology_findings import core_findings
        return core_findings(text)
    except Exception:
        f: Set[str] = set()
        for a, b in re.findall(r"gleason(?:'s)?\s+(?:score\s+)?(\d)\s*\+\s*(\d)", text, re.I):
            f.add(f"gleason:{a}+{b}")
        for g in re.findall(r"(?:grade\s+group|\bGG)\s*[:=]?\s*([1-5])\b", text, re.I):
            f.add(f"gg:{g}")
        for key, pat in (("adeno", r"adenocarcinoma"),
                         ("uro", r"urothelial\s+(?:cell\s+)?carcinoma|\bTCC\b"),
                         ("rcc", r"renal\s+cell\s+carcinoma|\bRCC\b"),
                         ("scc", r"squamous\s+cell\s+carcinoma|\bSCCa?\b"),
                         ("seminoma", r"\bseminoma\b")):
            if re.search(pat, text, re.I):
                f.add(f"histology:{key}")
        return f


def _compose_prompt(ctx: str) -> str:
    return f"""\
You are a urologic pathologist assistant writing the PATHOLOGY RESULTS section
of a clinic note. Read ALL pathology material below and report EVERY documented
finding — omit nothing.

For each specimen / report, one entry (most recent or most definitive first):
  <date> — <specimen site>: <histologic diagnosis>, <grade in the CORRECT system
  for that organ> , <stage if given>, <margins / invasion / node status if given>.

Grade by organ:
  - Prostate: Gleason X+Y=Z, Grade Group N.
  - Kidney (RCC): subtype (clear cell / papillary / chromophobe), ISUP/Fuhrman grade.
  - Bladder/upper tract (urothelial): high- vs low-grade, muscularis propria
    involved or not (stage).
  - Penis: squamous cell carcinoma, depth/grade, LVI, node status.
  - Testis: germ-cell subtype(s) and %, rete/LVI, stage.

RULES:
  - A patient may have MORE THAN ONE cancer — report each.
  - Use ONLY findings documented in the material. Do NOT invent grades/stages.
  - Do not editorialize; this is the pathology record.
  - If NO pathology is documented anywhere, output exactly: None documented

PATHOLOGY MATERIAL:
{ctx}

Write the PATHOLOGY RESULTS content now (no header, just the entries)."""


def _repair_prompt(ctx: str, draft: str, missing: Set[str]) -> str:
    return f"""\
Your PATHOLOGY section OMITTED these DOCUMENTED findings: {sorted(missing)}.
Rewrite the COMPLETE section so every one of them is included (keep everything
already correct, most definitive specimen first). Use only documented findings.

PATHOLOGY MATERIAL:
{ctx}

YOUR PREVIOUS DRAFT (incomplete):
{draft}

Rewrite the complete PATHOLOGY RESULTS content now:"""


def compose_pathology(
    chart: str,
    llm_call: LLMCallable,
    max_repair: int = 2,
) -> Optional[str]:
    """Return a complete PATHOLOGY section, or None to fall back to the caller's
    existing synthesizer (no pathology material, disabled, or error)."""
    if os.environ.get("VAUCDA_PATH_COMPOSER", "1") != "1":
        return None
    ctx = build_pathology_context(chart)
    if not ctx:
        return None
    source_findings = _findings(ctx)
    try:
        draft = (llm_call(_compose_prompt(ctx)) or "").strip()
        repairs = 0
        while source_findings and repairs < max_repair:
            missing = source_findings - _findings(draft)
            if not missing:
                break
            draft = (llm_call(_repair_prompt(ctx, draft, missing)) or draft).strip()
            repairs += 1
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Pathology composer failed, falling back: {e}")
        return None
    if not draft:
        return None
    # Report residual completeness / grounding for the audit trail.
    covered = _findings(draft)
    missing = source_findings - covered
    fabricated = covered - _findings(chart)
    logger.info(
        f"[PATH] composed: {len(covered & source_findings)}/{len(source_findings)} "
        f"findings covered after {repairs} repair(s)"
        + (f"; STILL MISSING {sorted(missing)}" if missing else "")
        + (f"; UNGROUNDED {sorted(fabricated)}" if fabricated else ""))
    # Strip any leaked markdown / header the LLM may have added.
    draft = re.sub(r"^\s*[#*]*\s*PATHOLOGY(?:\s+RESULTS)?\s*[:*]*\s*\n?",
                   "", draft, flags=re.IGNORECASE)
    draft = re.sub(r"\*\*(.*?)\*\*", r"\1", draft)   # unbold
    draft = re.sub(r"(?<!\S)\*(?!\s)(.*?)(?<!\s)\*(?!\S)", r"\1", draft)  # unitalic
    draft = re.sub(r"^\s*[-*]\s+", "", draft, flags=re.MULTILINE)  # bullets -> lines
    draft = re.sub(r"\n{3,}", "\n\n", draft)
    return draft.strip()
