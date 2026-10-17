#!/usr/bin/env python
"""Automated audit of the incidental-finding failure modes across a paired
input/output batch — needs NO per-case gold. Self-checks each generated note
against its source chart for the two defects the clinician reported:

  A) CC_INCIDENTAL_LEAD — the CC leads with an incidental "of uncertain
     significance" (adrenal nodule / cyst) while the patient has a cancer.
  B) ADRENAL_BENIGN_IGNORED — the source radiology characterizes the adrenal
     as BENIGN (myelolipoma / adenoma / washout / <10 HU / benign / stable),
     yet the note still calls the adrenal "uncertain significance".

Usage:
  python -m eval.audit_incidentals <inputs_dir> <notes_dir_or_glob>
    inputs_dir : dir of *.txt source charts
    notes_dir  : dir of generated notes (*.vaucda / *.txt), matched by stem
"""
from __future__ import annotations

import glob
import os
import re
import sys

_CANCER_SRC = re.compile(
    r"gleason|grade\s+group|\bGG[1-5]\b|adenocarcinoma|"
    r"squamous\s+cell\s+carcinoma|urothelial\s+carcinoma|"
    r"renal\s+cell\s+carcinoma|\bRCC\b|seminoma|"
    r"(?:prostate|bladder|renal|kidney|penile|testicular)\s+cancer",
    re.IGNORECASE)
_ADRENAL_BENIGN_SRC = re.compile(
    r"adrenal[^.\n]{0,80}?(myelolipoma|adenoma|washout|<\s*10\s*HU|"
    r"lipid[\s-]poor|benign|stable)|"
    r"(myelolipoma|adenoma)[^.\n]{0,40}?adrenal", re.IGNORECASE)
_ADRENAL_UNCERTAIN_NOTE = re.compile(
    r"adrenal[^.\n]{0,40}?(uncertain\s+significance|indeterminate)", re.IGNORECASE)
_CC_INCIDENTAL_LEAD = re.compile(
    r"^CC:\s*(?:follow[-\s]?up\s+(?:of|for)\s+)?"
    r"(?:adrenal|renal\s+cyst|simple\s+cyst)[^;\n]*uncertain\s+significance",
    re.IGNORECASE | re.MULTILINE)


def _match(inputs_dir, stem):
    for ext in (".vaucda", ".txt"):
        for p in glob.glob(os.path.join(inputs_dir, f"*{stem}*{ext}")):
            return p
    return None


def main(argv):
    if len(argv) != 2:
        print("usage: python -m eval.audit_incidentals <inputs_dir> <notes_dir>",
              file=sys.stderr)
        return 2
    inputs_dir, notes_dir = argv
    src_files = sorted(glob.glob(os.path.join(inputs_dir, "*.txt")))
    rows = []
    for src in src_files:
        stem = os.path.basename(src)[:-4]
        note_path = _match(notes_dir, stem)
        if not note_path:
            continue
        source = open(src, errors="ignore").read()
        note = open(note_path, errors="ignore").read()
        has_cancer = bool(_CANCER_SRC.search(source))
        cc = next((l for l in note.splitlines() if l.strip().upper().startswith("CC:")), "")
        cc_incidental = bool(_CC_INCIDENTAL_LEAD.search(cc + "\n"))
        adrenal_benign_src = bool(_ADRENAL_BENIGN_SRC.search(source))
        adrenal_uncertain_note = bool(_ADRENAL_UNCERTAIN_NOTE.search(note))
        defA = cc_incidental and has_cancer
        defB = adrenal_benign_src and adrenal_uncertain_note
        rows.append((stem, has_cancer, defA, defB, cc.strip()[:90]))

    print(f"\n{'='*90}\nINCIDENTAL-FINDING AUDIT — {notes_dir}\n{'='*90}")
    print(f"paired cases audited: {len(rows)}\n")
    a = [r for r in rows if r[2]]
    b = [r for r in rows if r[3]]
    print(f"A) CC leads with incidental 'uncertain significance' despite a cancer:"
          f" {len(a)}/{len(rows)}")
    for r in a:
        print(f"     ❌ {r[0]}: {r[4]}")
    print(f"\nB) Adrenal called 'uncertain significance' though radiology says BENIGN:"
          f" {len(b)}/{len(rows)}")
    for r in b:
        print(f"     ❌ {r[0]}")
    print(f"\nSUMMARY: {len(a)} CC-lead defects, {len(b)} adrenal-benign defects, "
          f"{len(set(x[0] for x in a) | set(x[0] for x in b))} distinct patients affected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
