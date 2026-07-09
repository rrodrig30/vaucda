#!/usr/bin/env python
"""Automated audit of PLAN-section defects across a paired batch (gold-free).

  A) INCIDENTAL_LED_PROBLEM — Problem #1 is an incidental "of uncertain
     significance" (adrenal/cyst) while the patient has a cancer.
  B) BENIGN_FOLLOWUP        — source radiology calls the adrenal BENIGN yet the
     Plan orders adrenal imaging / surveillance / repeat follow-up.
  C) GARBAGE                — hallucinated scanner/CPT metadata in a plan bullet.

Usage: python -m eval.audit_plan <inputs_dir> <notes_dir>
"""
from __future__ import annotations
import glob, os, re, sys

_CANCER_SRC = re.compile(
    r"gleason|grade\s+group|adenocarcinoma|urothelial\s+carcinoma|"
    r"renal\s+cell\s+carcinoma|\bRCC\b|squamous\s+cell\s+carcinoma\b|seminoma|"
    r"(?:prostate|bladder|renal|kidney|penile|testicular)\s+cancer", re.I)
_ADRENAL_BENIGN_SRC = re.compile(
    r"adrenal[^.\n]{0,80}?(myelolipoma|adenoma|washout|<\s*10\s*HU|lipid[\s-]poor|benign)", re.I)
# A plan line ORDERS adrenal follow-up if it mentions the adrenal alongside an
# imaging/surveillance modality AND a scheduling/recurrence verb, and is not
# negated ("no further adrenal imaging required"). Token order is irrelevant so
# "Repeat CT ... for adrenal ... annually" is caught.
_IMG = re.compile(r"\b(imaging|CT|MRI|ultrasound|US|re-?image|surveillance)\b", re.I)
_SCHED = re.compile(r"\b(repeat|schedule|obtain|order|dedicated|annual|annually|"
                    r"q\d|months?|next\s+imaging|follow[\s-]?up|monitor)\b", re.I)
_NEG = re.compile(r"\bno\b|\bnot\b|without|no\s+further|"
                  r"not\s+(required|indicated|needed)", re.I)
def _orders_adrenal_followup(plan):
    for ln in plan.splitlines():
        if "adrenal" not in ln.lower():
            continue
        if _IMG.search(ln) and _SCHED.search(ln) and not _NEG.search(ln):
            return True
    return False
_PROBLEM1_INCIDENTAL = re.compile(
    r"(?im)^\s*problem\s*#?\s*1\s*:\s*.*(adrenal|renal\s+cyst|cyst)[^\n]*uncertain\s+significance")
_GARBAGE = re.compile(
    r"\bphantom\b|\bkVp\b|\bmAs\b|reconstruction\s+kernel|\bcode\s+5\d{4}\b|"
    r"\bCPT\s+\d{5}\b|SEE\s+NOTE\s+\d|\bDLP\b|\bCTDIvol\b", re.I)


def _plan(note):
    m = re.search(r"(?ims)^PLAN:\s*(.*?)\Z", note)
    return m.group(1).strip() if m else ""


def _match(nd, stem):
    for ext in (".vaucda", ".txt"):
        for p in glob.glob(os.path.join(nd, f"*{stem}*{ext}")):
            return p
    return None


def main(argv):
    if len(argv) != 2:
        print("usage: python -m eval.audit_plan <inputs_dir> <notes_dir>", file=sys.stderr); return 2
    inputs, notes = argv
    rows = []
    for src in sorted(glob.glob(os.path.join(inputs, "*.txt"))):
        stem = os.path.basename(src)[:-4]; np = _match(notes, stem)
        if not np: continue
        source = open(src, errors="ignore").read(); plan = _plan(open(np, errors="ignore").read())
        if not plan: continue
        A = bool(_CANCER_SRC.search(source)) and bool(_PROBLEM1_INCIDENTAL.search(plan))
        B = bool(_ADRENAL_BENIGN_SRC.search(source)) and _orders_adrenal_followup(plan)
        C = bool(_GARBAGE.search(plan))
        rows.append((stem, A, B, C))
    print(f"\n{'='*80}\nPLAN AUDIT — {notes}\n{'='*80}\naudited: {len(rows)}\n")
    for label, idx in (("A) incidental 'uncertain significance' as Problem #1 despite cancer", 1),
                       ("B) orders follow-up on a BENIGN adrenal", 2),
                       ("C) hallucinated scanner/CPT garbage in a plan bullet", 3)):
        bad = [r for r in rows if r[idx]]
        print(f"{label}: {len(bad)}/{len(rows)}")
        for r in bad: print(f"     - {r[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
