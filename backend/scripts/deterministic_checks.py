#!/usr/bin/env python3
"""
Deterministic per-class note-accuracy checks (no LLM) for VAUCDA.

The LLM-judge assessment has run-to-run variance (~+/-20) that now exceeds the
per-fix signal. These checks are fully deterministic and reproducible, so they
give a stable yardstick for the specific error classes the fixes target.

Each check compares a generated note against its source input and counts
violations. Conservative by design (favor precision) so the numbers are
trustworthy.

Checks:
  med_continuation   Plan says "continue <drug>" for a drug NOT in the
                     authoritative VistA RXOP active-outpatient list, excluding
                     Eligard/ADT (intermittent — absence != stopped).
  psa_hallucination  A PSA value cited in the note that does not appear in the
                     source.
  tx_hallucination   A treatment modality/agent the note claims that does not
                     appear anywhere in the source.
  gleason_undergrade The note's stated Grade Group is LOWER than the maximum
                     Grade Group documented in the source pathology.

Usage:
  ./venv/bin/python scripts/deterministic_checks.py <input_dir> <output_dir> [files...]
"""
import re
import sys
from pathlib import Path

# ---- vocab -----------------------------------------------------------------
# Oncologic/urologic drugs we audit in "continue X" Plan clauses.
_AUDIT_DRUGS = {
    "finasteride", "dutasteride", "tamsulosin", "silodosin", "alfuzosin",
    "abiraterone", "enzalutamide", "apalutamide", "darolutamide",
    "bicalutamide", "docetaxel", "cabazitaxel", "sildenafil", "tadalafil",
    "methenamine", "oxybutynin", "mirabegron", "solifenacin",
}
# ADT / intermittent agents — EXEMPT from med_continuation (Eligard rule).
_ADT_EXEMPT = {
    "eligard", "leuprolide", "lupron", "goserelin", "zoladex", "degarelix",
    "relugolix", "orgovyx", "firmagon", "adt", "androgen",
}
# Treatment terms audited for hallucination, as (note_pattern, source_pattern).
# The source pattern is broader where the note may use a GENERIC term while the
# source names the specific agent (e.g. note "chemotherapy" vs source
# "docetaxel") — otherwise a correct generic label reads as a hallucination.
_TX_TERMS = {
    "prostatectomy": (r"prostatectom|\bRALP\b|\bRARP\b|\bRRP\b",
                      r"prostatectom|\bRALP\b|\bRARP\b|\bRRP\b"),
    "radiation": (r"radiation|radiotherapy|\bEBRT\b|\bXRT\b|\bIMRT\b|\bSBRT\b|brachytherap",
                  r"radiation|radiotherapy|\bEBRT\b|\bXRT\b|\bIMRT\b|\bSBRT\b|\bIGRT\b|brachytherap|cyberknife"),
    "abiraterone": (r"abiraterone", r"abiraterone|zytiga"),
    "enzalutamide": (r"enzalutamide", r"enzalutamide|xtandi"),
    "apalutamide": (r"apalutamide", r"apalutamide|apaluatimide|erleada"),
    "chemotherapy": (r"\bchemotherap",
                     r"chemotherap|docetaxel|cabazitaxel|taxotere|jevtana"),
    "lu-177": (r"lutetium|lu[- ]?177|pluvicto", r"lutetium|lu[- ]?177|pluvicto"),
    "cryotherapy": (r"cryoablat|cryotherap", r"cryoablat|cryotherap"),
    "nephrectomy": (r"nephrectom", r"nephrectom"),
    "cystectomy": (r"cystectom", r"cystectom"),
}

_GLEASON_TO_GG = {
    "3+3": 1, "3+4": 2, "4+3": 3,
    "4+4": 4, "3+5": 4, "5+3": 4,
    "4+5": 5, "5+4": 5, "5+5": 5,
}


def _rxop_drug_tokens(source: str) -> set:
    """Drug-name tokens from the authoritative RXOP active list in the source."""
    m = re.search(r"-+ RXOP - OUTPT RX-ACTIVE ONLY -+\n(.*?)(?=\n-{6,} [A-Z])",
                  source, re.S)
    if not m:
        return set()
    body = m.group(1)
    toks = set()
    for line in body.splitlines():
        # Drug-name lines start at col 0 with an uppercase drug name.
        if re.match(r"^[A-Z][A-Za-z].{2,}", line) and "ACTIVE" not in line \
                and "Drug" not in line:
            toks.add(line.strip().split()[0].lower())
    return toks


def _max_gg_in_text(text: str) -> int:
    ggs = [int(g) for g in re.findall(r"Grade\s+Group\s+(\d)", text, re.I)]
    for a, b in re.findall(r"\b([3-5])\s*\+\s*([3-5])\b", text):
        ggs.append(_GLEASON_TO_GG.get(f"{a}+{b}", 0))
    return max(ggs) if ggs else 0


def _note_section(note: str, header: str, until: str) -> str:
    m = re.search(rf"(?ms)^{header}.*?(?=^{until}|\Z)", note)
    return m.group(0) if m else ""


def check_one(source: str, note: str) -> dict:
    src_l = source.lower()
    flags = {"med_continuation": [], "psa_hallucination": [],
             "tx_hallucination": [], "gleason_undergrade": []}

    # 1. med_continuation
    rxop = _rxop_drug_tokens(source)
    plan = _note_section(note, "PLAN", "Time of Start") or note
    for m in re.finditer(r"continue\s+(?:the\s+)?([a-z][a-z\-]+)", plan, re.I):
        drug = m.group(1).lower()
        if drug in _ADT_EXEMPT:
            continue
        if drug in _AUDIT_DRUGS and drug not in rxop:
            flags["med_continuation"].append(drug)

    # 2. psa_hallucination — PSA values cited in note not present in source
    src_nums = set(re.findall(r"\b(\d{1,3}\.\d{1,2})\b", source))
    for m in re.finditer(r"PSA[^.\n]{0,40}?(\d{1,3}\.\d{1,2})\s*ng/m[lL]", note):
        if m.group(1) not in src_nums:
            flags["psa_hallucination"].append(m.group(1))

    # 3. tx_hallucination — treatment claimed in note absent from source
    for name, (note_pat, src_pat) in _TX_TERMS.items():
        if re.search(note_pat, note, re.I) and not re.search(src_pat, source, re.I):
            flags["tx_hallucination"].append(name)

    # 4. gleason_undergrade — note GG below source max GG
    src_max = _max_gg_in_text(source)
    note_max = _max_gg_in_text(note)
    if src_max and note_max and note_max < src_max:
        flags["gleason_undergrade"].append(f"note GG{note_max} < source GG{src_max}")

    return {k: sorted(set(v)) for k, v in flags.items()}


def main():
    in_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    files = sys.argv[3:] or [p.name for p in sorted(out_dir.glob("*.txt"))]
    totals = {"med_continuation": 0, "psa_hallucination": 0,
              "tx_hallucination": 0, "gleason_undergrade": 0}
    pts_with = dict(totals)
    detail = []
    for f in files:
        src_p, out_p = in_dir / f, out_dir / f
        if not (src_p.exists() and out_p.exists()):
            continue
        r = check_one(src_p.read_text(errors="ignore"),
                      out_p.read_text(errors="ignore"))
        n = sum(len(v) for v in r.values())
        if n:
            detail.append((f, r))
        for k, v in r.items():
            totals[k] += len(v)
            if v:
                pts_with[k] += 1

    print("=== DETERMINISTIC PER-CLASS CHECKS ===")
    print(f"files: {len([f for f in files if (out_dir/f).exists()])}\n")
    print(f"{'check':22s} {'violations':>10s} {'patients':>9s}")
    for k in totals:
        print(f"{k:22s} {totals[k]:>10d} {pts_with[k]:>9d}")
    print("\n--- per-patient detail ---")
    for f, r in detail:
        hits = "; ".join(f"{k}={v}" for k, v in r.items() if v)
        print(f"  {f:24s} {hits}")


if __name__ == "__main__":
    main()
