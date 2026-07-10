#!/usr/bin/env python
"""Audit HPI date-grounding across a paired batch (gold-free, source-grounded).

Independent of the composer's own verifier: it checks the RENDERED HPI against
the SOURCE chart. A biopsy or treatment YEAR asserted in the HPI must appear in
the source next to that kind of event. Catches the copied-forward phantom date
(JELLSEY: "Biopsy on October 29, 2025" when the only documented biopsy is
8/16/2022).

  U-BIOPSY   — an HPI sentence about a biopsy cites a year not documented as a
               biopsy year in the source.
  U-TREATMENT— an HPI sentence about radiation/ADT/prostatectomy cites a year not
               documented as a treatment year in the source.

Conservative: a class is only checked when the source has >=1 documented year of
that class; a sentence that also cites a correct year is not flagged.

Usage: python -m eval.audit_hpi_grounding <inputs_dir> <notes_dir>
"""
from __future__ import annotations
import glob, os, re, sys

_HPI = re.compile(r"(?ims)^HPI:\s*(.*?)(?=\n[A-Z][A-Za-z /]{1,40}:\s|\Z)")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_BIOPSY_KW = re.compile(r"biops", re.I)
_TX_KW = re.compile(r"radiation|\bXRT\b|\bEBRT\b|\bIMRT\b|brachy|prostatectom|\bADT\b|"
                    r"androgen|eligard|lupron|leuprolide|degarelix|goserelin|orgovyx|"
                    r"relugolix|abiraterone|enzalutamide|apalutamide|darolutamide", re.I)
# year adjacent to a biopsy / treatment mention in the SOURCE
_SRC_BIOPSY = re.compile(r"biops\w*[^.\n]{0,40}((?:19|20)\d{2})|((?:19|20)\d{2})[^.\n]{0,15}biops", re.I)
_SRC_BIOPSY_MD = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-](\d{2,4}))\s*(?:prostate\s+)?biops|"
                            r"biops\w*\s*(\d{1,2}[/-]\d{1,2}[/-](\d{2,4}))", re.I)
_SRC_TX = re.compile(
    r"(?:radiation|\bXRT\b|\bEBRT\b|brachy|prostatectom|\bADT\b|eligard|lupron|"
    r"leuprolide|abiraterone)[^.\n]{0,40}((?:19|20)\d{2})|"
    r"((?:19|20)\d{2})[^.\n]{0,25}(?:radiation|\bXRT\b|\bEBRT\b|brachy|prostatectom|\bADT\b)", re.I)


def _years(regex, text):
    out = set()
    for m in regex.finditer(text):
        for g in m.groups():
            if g and re.fullmatch(r"(19|20)\d{2}", g):
                out.add(g)
            elif g and re.fullmatch(r"\d{2}", g):
                out.add(("20" if int(g) < 50 else "19") + g)
    return out


def _hpi(note):
    m = _HPI.search(note)
    return (m.group(1).strip() if m else "")


def _sentences(t):
    return re.split(r"(?<=[.!?])\s+", t)


def _match(nd, stem):
    for ext in (".vaucda", ".txt"):
        for p in glob.glob(os.path.join(nd, f"*{stem}*{ext}")):
            return p
    return None


def main(argv):
    if len(argv) != 2:
        print("usage: python -m eval.audit_hpi_grounding <inputs_dir> <notes_dir>", file=sys.stderr); return 2
    inputs, notes = argv
    rows = []
    for src in sorted(glob.glob(os.path.join(inputs, "*.txt"))):
        stem = os.path.basename(src)[:-4]; np = _match(notes, stem)
        if not np:
            continue
        source = open(src, errors="ignore").read()
        hpi = _hpi(open(np, errors="ignore").read())
        if not hpi:
            continue
        b_years = _years(_SRC_BIOPSY, source) | _years(_SRC_BIOPSY_MD, source)
        t_years = _years(_SRC_TX, source)
        ub, ut = [], []
        for s in _sentences(hpi):
            yrs = set(re.findall(r"\b((?:19|20)\d{2})\b", s))
            if not yrs:
                continue
            if "no biops" in s.lower():
                continue
            if _BIOPSY_KW.search(s) and b_years and not (yrs & b_years):
                ub.append(sorted(yrs))
            if _TX_KW.search(s) and t_years and not (yrs & t_years):
                ut.append(sorted(yrs))
        rows.append((stem, ub, ut))
    print(f"\n{'='*80}\nHPI GROUNDING AUDIT — {notes}\n{'='*80}\naudited: {len(rows)}\n")
    for label, idx in (("U-BIOPSY: HPI biopsy year not documented as a biopsy", 1),
                       ("U-TREATMENT: HPI treatment year not documented as treatment", 2)):
        bad = [r for r in rows if r[idx]]
        print(f"{label}: {len(bad)}/{len(rows)}")
        for r in bad:
            print(f"     - {r[0]:22s} {r[idx]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
