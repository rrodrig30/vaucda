#!/usr/bin/env python
"""Automated audit of CHIEF-COMPLAINT defects across a paired batch (gold-free).

  A) BENIGN_INCIDENTAL_LED — the CC's LEADING finding is an adrenal/cyst framed
     as "mass"/"uncertain significance"/"neoplasm" while the source radiology
     characterizes that finding as BENIGN (MOLINA: adrenal myelolipoma).
  B) UNCERTAIN_MISLABELS_CANCER — the CC calls a renal/bladder lesion "of
     uncertain significance" while the source documents a tissue-confirmed,
     definitively-treated cancer of that organ (FLORES: Hx RCC s/p partial
     nephrectomy). Untreated "possible RCC" (KIND) is NOT flagged.

The defect definitions live in app/services/note_processing/cc_checks.py so the
offline audit and the runtime CC verifier share one implementation.

Usage: python -m eval.audit_cc <inputs_dir> <notes_dir>
"""
from __future__ import annotations
import glob, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services.note_processing.cc_checks import (  # noqa: E402
    cc_body, benign_incidental_leads, uncertain_mislabels_cancer)


def _match(nd, stem):
    for ext in (".vaucda", ".txt"):
        for p in glob.glob(os.path.join(nd, f"*{stem}*{ext}")):
            return p
    return None


def main(argv):
    if len(argv) != 2:
        print("usage: python -m eval.audit_cc <inputs_dir> <notes_dir>", file=sys.stderr); return 2
    inputs, notes = argv
    rows = []
    for src in sorted(glob.glob(os.path.join(inputs, "*.txt"))):
        stem = os.path.basename(src)[:-4]; np = _match(notes, stem)
        if not np:
            continue
        source = open(src, errors="ignore").read()
        cc = cc_body(open(np, errors="ignore").read())
        if not cc:
            continue
        rows.append((stem, benign_incidental_leads(cc, source),
                     uncertain_mislabels_cancer(cc, source), cc[:70]))
    print(f"\n{'='*80}\nCC AUDIT — {notes}\n{'='*80}\naudited: {len(rows)}\n")
    for label, idx in (("A) benign incidental (adrenal/cyst) leads the CC", 1),
                       ("B) 'uncertain significance' mislabels a confirmed/treated cancer", 2)):
        bad = [r for r in rows if r[idx]]
        print(f"{label}: {len(bad)}/{len(rows)}")
        for r in bad:
            print(f"     - {r[0]:22s} | {r[3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
