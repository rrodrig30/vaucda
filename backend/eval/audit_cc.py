#!/usr/bin/env python
"""Automated audit of CHIEF-COMPLAINT defects across a paired batch (gold-free).

  A) BENIGN_INCIDENTAL_LED — the CC's LEADING finding is an adrenal/cyst framed
     as "mass"/"uncertain significance"/"neoplasm" while the source radiology
     characterizes that finding as BENIGN (myelolipoma / lipid-rich-washout
     adenoma / simple Bosniak I-II cyst). The benign incidental should not be
     the visit's chief complaint (MOLINA: adrenal myelolipoma).
  B) UNCERTAIN_MISLABELS_CANCER — the CC calls a renal/bladder lesion "of
     uncertain significance" while the source documents a tissue-confirmed,
     definitively-treated cancer of that organ (Hx of RCC / s/p nephrectomy /
     ablation for cancer). A resected, pathology-proven cancer is not
     "uncertain" (FLORES: Hx RCC s/p partial nephrectomy). Genuinely untreated
     "possible RCC / consideration of nephrectomy" (KIND) is NOT flagged.

Usage: python -m eval.audit_cc <inputs_dir> <notes_dir>
"""
from __future__ import annotations
import glob, os, re, sys

# --- source characterizations -------------------------------------------------
_ADRENAL_BENIGN = re.compile(
    r"adrenal[^.\n]{0,90}?(myelolipoma|adenoma|washout|<\s*10\s*HU|lipid[\s-]poor|"
    r"macroscopic fat|fat[\s-]containing|benign)|myelolipoma", re.I)
# confirmed + treated organ cancer (definitive, not "possible/consideration of")
# An ESTABLISHED prior cancer: history/known-of the carcinoma AND definitive
# treatment already completed (s/p resection/ablation). Excludes newly-found or
# scheduled-for-treatment lesions (MARTINEZ: TURBT scheduled 7/13; RIPLEY: none).
_RENAL_CA_TREATED = re.compile(
    r"(hx|history|known)\s+of\s+(right|left|bilateral\s+)?(rcc|renal\s+cell\s+carcinoma)"
    r"[^.\n]{0,60}?(s/?p|resect|nephrectomy|ablation|ned)", re.I)
_BLADDER_CA_TREATED = re.compile(
    r"(hx|history|known)\s+of[^.\n]{0,30}?(bladder\s+cancer|urothelial\s+carcinoma)"
    r"[^.\n]{0,60}?(s/?p|resect|turbt|cystectomy|ned)", re.I)


def _cc(note):
    m = re.search(r"(?im)^CC:\s*(.+)$", note)
    return m.group(1).strip() if m else ""


def _lead_clause(cc):
    # first finding before ';' or ' and '
    return re.split(r";| and ", cc, maxsplit=1)[0].lower()


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
        cc = _cc(open(np, errors="ignore").read())
        if not cc:
            continue
        lead = _lead_clause(cc)
        cc_lc = cc.lower()
        # A) benign incidental leads the CC
        A = (("adrenal" in lead or "cyst" in lead)
             and re.search(r"uncertain significance|mass|neoplasm", lead)
             and bool(_ADRENAL_BENIGN.search(source)) and "adrenal" in lead)
        # B) uncertain-significance label over a confirmed/treated organ cancer
        B = False
        if re.search(r"(renal|kidney)[^;]{0,40}?of uncertain significance", cc_lc):
            B = bool(_RENAL_CA_TREATED.search(source))
        if not B and re.search(r"bladder[^;]{0,40}?of uncertain significance", cc_lc):
            B = bool(_BLADDER_CA_TREATED.search(source))
        rows.append((stem, bool(A), bool(B), cc[:70]))
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
