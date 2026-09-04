#!/usr/bin/env python3
"""
Per-field scorer for L1 v2 extractions vs gold labels.

Deterministic, noise-free metrics (the L1 yardstick): diagnosis P/R/F1,
treatment-event P/R/F1, diagnosis_date accuracy, grade accuracy (cancer-aware:
prostate GG, RCC Fuhrman, bladder WHO), and procedures-vs-imaging separation.
Scored over segments present in BOTH label sets.

Usage:
  ./venv/bin/python scripts/l1/score.py <gold_dir> <candidate_dir>
"""
import json
import re
import sys
from pathlib import Path


def _norm_date(d):
    if not d:
        return None
    m = re.match(r"(\d{4})(?:-(\d{2}))?", str(d))
    return (m.group(1), m.group(2)) if m else None


def _date_match(a, b):
    na, nb = _norm_date(a), _norm_date(b)
    if na is None or nb is None:
        return na == nb
    return na[0] == nb[0]


def _name_key(s):
    s = (s or "").lower()
    for kw in ("prostate", "renal", "rcc", "kidney", "bladder", "urotheli",
               "erectile", "bph", "luts", "stone", "lithiasis", "cyst", "mass",
               "hydronephro", "stricture", "testic", "ureter"):
        if kw in s:
            return "rcc" if kw in ("renal", "rcc", "kidney") else \
                   ("bladder" if kw in ("bladder", "urotheli") else
                    ("stone" if kw in ("stone", "lithiasis") else kw))
    return s[:8]


def _grade_val(g):
    if not g:
        return None
    return (g.get("grade_group"), g.get("nuclear_grade"),
            g.get("who_grade"), g.get("bladder_stage"))


def _ev_match(a, b):
    if (a.get("modality") or "").lower() != (b.get("modality") or "").lower():
        return False
    aa, ba = (a.get("agent") or "").lower(), (b.get("agent") or "").lower()
    if aa and ba and aa.split()[0] == ba.split()[0]:
        return True
    return _date_match(a.get("start_date"), b.get("start_date"))


def _load(d):
    out = {}
    for f in (Path(d) / "labels").glob("*.json"):
        try:
            out[f.stem] = json.loads(f.read_text())
        except Exception:
            pass
    return out


def _prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0
    r = tp / (tp + fn) if (tp + fn) else 0
    f = 2 * p * r / (p + r) if (p + r) else 0
    return p, r, f


def main():
    gold, cand = _load(sys.argv[1]), _load(sys.argv[2])
    common = sorted(set(gold) & set(cand))
    if not common:
        print("no overlapping labeled segments")
        return
    dtp = dfp = dfn = 0
    etp = efp = efn = 0
    dxd_ok = dxd_n = gr_ok = gr_n = 0
    img_in_proc = 0  # candidate procedures that are actually imaging
    IMG = re.compile(r"\b(CT|MRI|US|ultrasound|PET|PSMA|bone scan|x-ray|NM|scan)\b", re.I)

    for sid in common:
        g, c = gold[sid], cand[sid]
        # diagnoses
        gd, cd = list(g.get("diagnoses") or []), list(c.get("diagnoses") or [])
        used = set()
        for ge in gd:
            hit = None
            for i, ce in enumerate(cd):
                if i in used:
                    continue
                if _name_key(ge.get("name")) == _name_key(ce.get("name")):
                    hit = i
                    break
            if hit is not None:
                used.add(hit)
                dtp += 1
                if ge.get("diagnosis_date"):
                    dxd_n += 1
                    if _date_match(ge.get("diagnosis_date"), cd[hit].get("diagnosis_date")):
                        dxd_ok += 1
                if ge.get("grade") and _grade_val(ge.get("grade")) != (None, None, None, None):
                    gr_n += 1
                    if _grade_val(ge.get("grade")) == _grade_val(cd[hit].get("grade")):
                        gr_ok += 1
            else:
                dfn += 1
        dfp += len(cd) - len(used)
        # treatments
        gev, cev = list(g.get("treatment_events") or []), list(c.get("treatment_events") or [])
        u2 = set()
        for ge in gev:
            hit = next((i for i, ce in enumerate(cev) if i not in u2 and _ev_match(ge, ce)), None)
            if hit is not None:
                u2.add(hit)
                etp += 1
            else:
                efn += 1
        efp += len(cev) - len(u2)
        # procedures/imaging separation (candidate hygiene)
        for p in c.get("procedures") or []:
            if IMG.search(p.get("type") or ""):
                img_in_proc += 1

    dp, dr, df = _prf(dtp, dfp, dfn)
    ep, er, ef = _prf(etp, efp, efn)

    def pct(a, b):
        return f"{(100*a/b):.0f}% ({a}/{b})" if b else "n/a"

    print(f"=== L1 v2 EVAL vs gold ({len(common)} segments) ===")
    print(f"diagnoses        P={dp:.2f} R={dr:.2f} F1={df:.2f}  (tp={dtp} fp={dfp} fn={dfn})")
    print(f"  diagnosis_date acc:  {pct(dxd_ok, dxd_n)}")
    print(f"  grade acc (by system): {pct(gr_ok, gr_n)}")
    print(f"treatment_events P={ep:.2f} R={er:.2f} F1={ef:.2f}  (tp={etp} fp={efp} fn={efn})")
    print(f"candidate procedures that are actually imaging: {img_in_proc}")


if __name__ == "__main__":
    main()
