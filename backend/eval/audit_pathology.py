#!/usr/bin/env python
"""Organ-agnostic pathology completeness + grounding audit for a paired batch.

For each source/note pair it computes, over the pathology-finding ledger
(eval/pathology_findings.py — Gleason/GG/other-grade/histology across ALL GU
cancers):
  - completeness (recall): source findings covered by the note / by the
    PATHOLOGY section  -> catches OMISSIONS
  - grounding (precision): note findings absent from source -> catches
    FABRICATION / wrong grade

Usage: python -m eval.audit_pathology <inputs_dir> <notes_dir>
"""
from __future__ import annotations
import glob, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval.pathology_findings import core_findings  # noqa: E402


def _section(note):
    m = re.search(r"(?ims)^PATHOLOGY(?:\s+RESULTS)?:\s*(.*?)(?=\n[A-Z][A-Z /]{2,}:|\Z)", note)
    return m.group(1).strip() if m else ""


def _match(notes_dir, stem):
    for ext in (".vaucda", ".txt"):
        for p in glob.glob(os.path.join(notes_dir, f"*{stem}*{ext}")):
            return p
    return None


def main(argv):
    if len(argv) != 2:
        print("usage: python -m eval.audit_pathology <inputs_dir> <notes_dir>", file=sys.stderr)
        return 2
    inputs, notes = argv
    src_tot = cov_all = cov_sec = fab = 0
    affected, fabs = [], []
    for src in sorted(glob.glob(os.path.join(inputs, "*.txt"))):
        stem = os.path.basename(src)[:-4]
        np = _match(notes, stem)
        if not np:
            continue
        s = core_findings(open(src, errors="ignore").read())
        if not s:
            continue
        note = open(np, errors="ignore").read()
        n_all, n_sec = core_findings(note), core_findings(_section(note))
        src_tot += len(s); cov_all += len(s & n_all); cov_sec += len(s & n_sec)
        miss = s - n_sec
        if miss:
            affected.append((stem, sorted(miss)))
        bad = n_all - s  # cited by note, not in source
        if bad:
            fab += len(bad); fabs.append((stem, sorted(bad)))
    print(f"\n{'='*80}\nPATHOLOGY AUDIT (organ-agnostic) — {notes}\n{'='*80}")
    print(f"source pathology findings: {src_tot}")
    print(f"  COMPLETENESS anywhere-in-note : {cov_all}/{src_tot} ({cov_all*100//max(1,src_tot)}%)")
    print(f"  COMPLETENESS pathology-section: {cov_sec}/{src_tot} ({cov_sec*100//max(1,src_tot)}%)")
    print(f"  patients with a section omission: {len(affected)}")
    print(f"  GROUNDING fabricated/absent findings: {fab}")
    for stem, bad in fabs[:10]:
        print(f"    ⚠ {stem}: note cites {bad} not in source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
