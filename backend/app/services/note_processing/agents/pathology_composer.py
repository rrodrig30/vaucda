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
  - Histology comes ONLY from a pathology DIAGNOSIS. An imaging impression
    ("concerning for renal cell carcinoma"), a surgery booking ("Pre-op Diag:
    Bladder Cancer (Unverified)"), a problem-list entry, or cytology atypia is
    NOT histology — never write "Histology: <cancer>" for them. A specimen
    read as benign / negative for malignancy is reported exactly so.
  - Do not editorialize; this is the pathology record.
  - If NO pathology is documented anywhere, output exactly: None documented

PATHOLOGY MATERIAL:
{ctx}

Write the PATHOLOGY RESULTS content now (no header, just the entries)."""


_HISTO_TERM_RE = re.compile(
    r"clear[\s-]cell|papillary\s+(?:renal|urothelial)|chromophobe|oncocytoma|sarcomatoid|collecting[\s-]duct|"
    r"urothelial\s+(?:cell\s+)?carcinoma|transitional\s+cell|squamous\s+cell\s+carcinoma|adenocarcinoma|"
    r"renal\s+cell\s+carcinoma|\bRCC\b|seminoma|embryonal|teratoma|yolk\s+sac|choriocarcinoma|"
    r"carcinoma\s+in\s+situ|\bCIS\b|small[\s-]cell|neuroendocrine|lymphoma|melanoma|\bPIN\b|\bASAP\b", re.I)


def _strip_ungrounded_histology_terms(draft: str, grounded_path: str) -> str:
    """Remove a 'Histology: <term>' fragment or a whole histology-only line whose
    term does not appear in any pathology report. Entries that otherwise carry
    grounded content keep everything except the ungrounded fragment."""
    if not draft:
        return draft
    gp = (grounded_path or "").lower()

    def _grounded(term: str) -> bool:
        t = re.sub(r"\s+", " ", term.lower()).strip()
        return bool(t) and (t in gp or re.sub(r"[\s-]", "", t) in re.sub(r"[\s-]", "", gp))

    out = []
    for line in draft.split("\n"):
        # "Histology: X." fragments (standalone line or trailing on an entry)
        def _frag(m):
            return "" if not _grounded(m.group(1)) else m.group(0)
        new = re.sub(r"(?i)\bhistology\s*:\s*([^.;\n]{2,60})[.;]?", _frag, line)
        if new.strip() != line.strip():
            if not new.strip():
                continue
            line = re.sub(r"\s{2,}", " ", new).rstrip()
        # a line that is ONLY an ungrounded histology claim
        terms = [t for t in _HISTO_TERM_RE.findall(line)]
        if terms and len(line.strip()) <= 60 and not any(_grounded(t) for t in terms):
            continue
        out.append(line)
    return "\n".join(out)


def _ungrounded_prompt(ctx: str, draft: str, ungrounded: Set[str]) -> str:
    return f"""\
Your PATHOLOGY section asserts histology that NO pathology report documents:
{sorted(ungrounded)}. Imaging impressions ("concerning for renal cell carcinoma"),
surgery bookings ("Pre-op Diag: Bladder Cancer (Unverified)"), problem-list
entries, and cytology atypia are NOT histologic diagnoses. Rewrite the COMPLETE
section reporting ONLY diagnoses stated in a pathology DIAGNOSIS; a specimen
read as benign / negative for malignancy must be reported exactly so, with no
histology of a cancer appended.

PATHOLOGY MATERIAL:
{ctx}

YOUR PREVIOUS DRAFT:
{draft}

Rewrite the complete PATHOLOGY RESULTS content now:"""


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


# Markers that indicate the LLM ECHOED its prompt scaffolding / raw material
# instead of composing a clean summary (opus-class failure mode) — the composed
# section must never contain these. Everything from the first such marker onward
# is cut.
_PATH_ECHO_CUT = re.compile(
    r"(?im)^\s*\**\s*(?:PATHOLOGY\s+MATERIAL|"
    r"MICROSCOPIC\s+EXAM(?:/DIAGNOSIS)?|"
    r"HISTORY\s+OF\s+PRESENT\s+ILLNESS|"
    r"Impression\s*/\s*PLAN|CHIEF\s+COMPLAINT|"
    r"Prior\s+biopsies?\s*\(OSH\)|SOURCE\s+MATERIAL|"
    r"Provider\s+Narrative|Facility\s*:|Medication\s+Reconc)\b.*",
    re.DOTALL,
)
# Standalone scaffolding/metadata fragment lines the composer sometimes leaves
# (a lone 'MATERIAL**' after a header strip, VistA export metadata rows).
_PATH_META_LINE = re.compile(
    r"(?im)^\s*\**\s*(?:MATERIAL\**|Facility\s*:[^\n]*|Provider\s+Narrative|"
    r"Date\s+(?:of\s+Onset|Modified|Reported|Verified)|VISTA\s+EXPORT|"
    r"={5,}|-{5,})\s*\**\s*$\n?",
)
# LLM meta-preamble the composer sometimes prepends.
_PATH_PREAMBLE = re.compile(
    r"^\s*(?:here\s+is|here'?s|below\s+is|the\s+following\s+is|sure[,!]?\s+here)"
    r"\b[^\n:]{0,90}:\s*\n?", re.IGNORECASE)


def _strip_path_echo(draft: str) -> str:
    """Remove a leading meta-preamble and cut any echoed prompt-scaffolding / raw
    material dump so the composed pathology can never bleed the source blob."""
    if not draft:
        return draft
    draft = _PATH_PREAMBLE.sub("", draft, count=1)
    draft = _PATH_ECHO_CUT.sub("", draft)
    draft = _PATH_META_LINE.sub("", draft)
    draft = re.sub(r"\n{3,}", "\n\n", draft)
    return draft.strip()


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
    # REQUIRED findings come only from REAL pathology reports (the deterministic
    # extraction), never from the broad context: that context carries imaging
    # impressions ("concerning for renal cell carcinoma"), surgery bookings
    # ("Pre-op Diag: Bladder Cancer (Unverified)") and cytology atypia, and the
    # repair loop was forcing the model to add "Histology: renal cell carcinoma"
    # / "urothelial carcinoma" for them (CARO: biopsy read benign).
    try:
        from ..extractors import extract_pathology
        grounded_path = extract_pathology(chart) or ""
    except Exception:  # noqa: BLE001
        grounded_path = ""
    grounded = _findings(grounded_path)
    source_findings = {f for f in _findings(ctx) if not f.startswith("histology:") or f in grounded}
    try:
        draft = _strip_path_echo((llm_call(_compose_prompt(ctx)) or "").strip())
        repairs = 0
        while source_findings and repairs < max_repair:
            missing = source_findings - _findings(draft)
            if not missing:
                break
            draft = _strip_path_echo(
                (llm_call(_repair_prompt(ctx, draft, missing)) or draft).strip())
            repairs += 1
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Pathology composer failed, falling back: {e}")
        return None
    # If echo-stripping left nothing (the model only echoed scaffolding/raw
    # material), fall back rather than emit an empty or bleeding section.
    if not draft or len(draft) < 15:
        logger.warning("Pathology composer produced only scaffolding/echo; falling back")
        return None
    # Deterministic first: any explicit histology TERM in the draft that no
    # pathology report contains is removed outright (SAENZ: a stray "Histology:
    # Clear cell." under a prostate biopsy + medical renal biopsy).
    draft = _strip_ungrounded_histology_terms(draft, grounded_path)
    # Histology the draft asserts that NO pathology report documents -> ask the
    # model to remove it once; if it persists, fall back to the deterministic
    # pathology rather than ship a fabricated histology.
    ungrounded = {f for f in _findings(draft) if f.startswith("histology:") and f not in grounded}
    if ungrounded:
        try:
            draft2 = _strip_path_echo((llm_call(_ungrounded_prompt(ctx, draft, ungrounded)) or "").strip())
            if draft2 and len(draft2) >= 15:
                draft = draft2
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Pathology ungrounded-histology repair failed: {e}")
        still = {f for f in _findings(draft) if f.startswith("histology:") and f not in grounded}
        if still:
            logger.warning(f"[PATH] ungrounded histology {sorted(still)} persisted; using deterministic pathology")
            return grounded_path or None
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
