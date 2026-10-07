#!/usr/bin/env python
"""Automated audit of Assessment-section defects across a paired batch.

Gold-free self-checks against the source chart for the failure modes seen in
the tumor-clinic batch:

  A) INCIDENTAL_LED    — the Assessment OPENS with an incidental "of uncertain
     significance" (adrenal/cyst) while the patient has a cancer.
  B) BENIGN_FOLLOWUP   — source radiology calls the adrenal BENIGN, yet the
     Assessment recommends adrenal imaging / surveillance / repeat follow-up.
  C) GARBAGE           — hallucinated scanner-metadata / artifact text leaked
     into the narrative ("phantom", "diameter phantom", CPT "code 5xxxx", ...).
  D) CANCER_UNCOVERED  — a cancer documented in the source pathology is not
     addressed anywhere in the Assessment (multi-cancer completeness).

Usage: python -m eval.audit_assessment <inputs_dir> <notes_dir>
"""
from __future__ import annotations

import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval.pathology_findings import core_findings  # noqa: E402

_CANCER_SRC = re.compile(
    r"gleason|grade\s+group|adenocarcinoma|urothelial\s+carcinoma|"
    r"renal\s+cell\s+carcinoma|\bRCC\b|squamous\s+cell\s+carcinoma\b|seminoma|"
    r"(?:prostate|bladder|renal|kidney|penile|testicular)\s+cancer", re.I)
_ADRENAL_BENIGN_SRC = re.compile(
    r"adrenal[^.\n]{0,80}?(myelolipoma|adenoma|washout|<\s*10\s*HU|lipid[\s-]poor|benign)",
    re.I)
_ADRENAL_FOLLOWUP = re.compile(
    r"adrenal[^.\n]{0,60}?(imaging|surveillance|repeat|follow[\s-]?up|re-?image|"
    r"monitor|CT|MRI)|(?:repeat|dedicated|follow[\s-]?up)[^.\n]{0,30}?adrenal", re.I)
_GARBAGE = re.compile(
    r"\bphantom\b|diameter\s+phantom|\bkVp\b|\bmAs\b|reconstruction\s+kernel|"
    r"\bcode\s+5\d{4}\b|SEE\s+NOTE\s+\d|CPT\s+\d{5}", re.I)
# map organ -> the words that show that organ is addressed
_ORGAN_WORDS = {
    "prostate": ["prostate", "prostatic"], "renal": ["renal", "kidney"],
    "bladder": ["bladder", "urothelial"], "penile": ["penile", "penis"],
    "testicular": ["testicular", "testis"],
}
_FINDING_ORGAN = {
    "gleason": "prostate", "gg": "prostate",
    "histology:adenocarcinoma": "prostate",
    "histology:urothelial-carcinoma": "bladder",
    "histology:renal-cell-carcinoma": "renal",
    "histology:squamous-cell-carcinoma": "penile",
}


def _assessment(note):
    m = re.search(r"(?ims)^ASSESSMENT:?\s*(.*?)(?=\n(?:PROBLEM|PLAN)\b|\Z)", note)
    return m.group(1).strip() if m else ""


def _match(notes_dir, stem):
    for ext in (".vaucda", ".txt"):
        for p in glob.glob(os.path.join(notes_dir, f"*{stem}*{ext}")):
            return p
    return None


def _cancer_organs(source):
    organs = set()
    for f in core_findings(source):
        for k, org in _FINDING_ORGAN.items():
            if f == k or f.startswith(k):
                organs.add(org)
    return organs


def main(argv):
    if len(argv) != 2:
        print("usage: python -m eval.audit_assessment <inputs_dir> <notes_dir>", file=sys.stderr)
        return 2
    inputs, notes = argv
    rows = []
    for src in sorted(glob.glob(os.path.join(inputs, "*.txt"))):
        stem = os.path.basename(src)[:-4]
        np = _match(notes, stem)
        if not np:
            continue
        source = open(src, errors="ignore").read()
        a = _assessment(open(np, errors="ignore").read())
        if not a:
            continue
        opener = " ".join(re.split(r"(?<=[.!?])\s+", a)[:1]).lower()
        has_cancer = bool(_CANCER_SRC.search(source))
        A = has_cancer and bool(re.search(r"(adrenal|cyst)[^.\n]*uncertain\s+significance", opener))
        B = bool(_ADRENAL_BENIGN_SRC.search(source)) and bool(_ADRENAL_FOLLOWUP.search(a))
        C = bool(_GARBAGE.search(a))
        a_lc = a.lower()
        uncovered = [o for o in _cancer_organs(source)
                     if not any(w in a_lc for w in _ORGAN_WORDS.get(o, [o]))]
        rows.append((stem, A, B, C, uncovered))
    print(f"\n{'='*80}\nASSESSMENT AUDIT — {notes}\n{'='*80}\naudited: {len(rows)}\n")
    for label, idx in (("A) incidental-led opener despite cancer", 1),
                       ("B) recommends follow-up on a BENIGN adrenal", 2),
                       ("C) hallucinated scanner/artifact garbage", 3)):
        bad = [r for r in rows if r[idx]]
        print(f"{label}: {len(bad)}/{len(rows)}")
        for r in bad:
            print(f"     - {r[0]}")
    unc = [r for r in rows if r[4]]
    print(f"D) a documented cancer NOT addressed in Assessment: {len(unc)}/{len(rows)}")
    for r in unc:
        print(f"     - {r[0]}: missing {r[4]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
