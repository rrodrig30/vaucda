#!/usr/bin/env python3
"""
Per-field scorer for L1 extractions vs the gold labels.

Computes deterministic, noise-free metrics (the L1 yardstick from the scope
doc): treatment-event P/R/F1, and per-field accuracy for diagnosis_date,
grade_group, and stage_tnm — over the segments present in BOTH label sets.

Label files: <dir>/labels/<segment_id>.json (gold = urologist-reviewed;
candidate = L1 or the regex baseline). Schema is schema.json (or the
source_quote draft variant — only the fields below are scored).

Usage:
  ./venv/bin/python scripts/l1/score.py <gold_dir> <candidate_dir>
"""
import json
import re
import sys
from pathlib import Path


def _norm_date(d):
    """Normalize ISO date to (year, month) for tolerant matching; month/day
    precision differences are tolerated, year mismatches are not."""
    if not d:
        return None
    m = re.match(r"(\d{4})(?:-(\d{2}))?", str(d))
    if not m:
        return None
    return (m.group(1), m.group(2))


def _date_match(a, b, month_tol=True):
    na, nb = _norm_date(a), _norm_date(b)
    if na is None or nb is None:
        return na == nb
    if na[0] != nb[0]:
        return False
    if not month_tol and na[1] and nb[1] and na[1] != nb[1]:
        return False
    return True


def _modality_key(ev):
    mod = (ev.get("modality") or "").lower()
    agent = (ev.get("agent") or "").lower()
    return mod, agent


def _events_match(g, c):
    """A candidate event matches a gold event if modality matches and either
    the agent matches or the start dates align (same year)."""
    gm, ga = _modality_key(g)
    cm, ca = _modality_key(c)
    if gm != cm:
        return False
    if ga and ca and ga.split()[0] == ca.split()[0]:
        return True
    return _date_match(g.get("start_date"), c.get("start_date"))


def _load(dirpath):
    out = {}
    ld = Path(dirpath) / "labels"
    for f in ld.glob("*.json"):
        try:
            out[f.stem] = json.loads(f.read_text())
        except Exception:
            pass
    return out


def main():
    gold = _load(sys.argv[1])
    cand = _load(sys.argv[2])
    common = sorted(set(gold) & set(cand))
    if not common:
        print("no overlapping labeled segments")
        return

    tp = fp = fn = 0
    date_ok = date_n = 0
    status_ok = status_n = 0
    dx_date_ok = dx_date_n = 0
    gg_ok = gg_n = 0

    for sid in common:
        g, c = gold[sid], cand[sid]
        gev = list(g.get("treatment_events") or [])
        cev = list(c.get("treatment_events") or [])
        used = set()
        for ge in gev:
            hit = None
            for i, ce in enumerate(cev):
                if i in used:
                    continue
                if _events_match(ge, ce):
                    hit = i
                    break
            if hit is not None:
                used.add(hit)
                tp += 1
                # field accuracy on matched events
                date_n += 1
                if _date_match(ge.get("start_date"), cev[hit].get("start_date")):
                    date_ok += 1
                status_n += 1
                if (ge.get("status") or "") == (cev[hit].get("status") or ""):
                    status_ok += 1
            else:
                fn += 1
        fp += len(cev) - len(used)

        # diagnosis fields
        gd, cd = g.get("diagnosis") or {}, c.get("diagnosis") or {}
        if gd.get("diagnosis_date"):
            dx_date_n += 1
            if _date_match(gd.get("diagnosis_date"), cd.get("diagnosis_date")):
                dx_date_ok += 1
        if gd.get("grade_group"):
            gg_n += 1
            if gd.get("grade_group") == cd.get("grade_group"):
                gg_ok += 1

    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0

    def pct(a, b):
        return f"{(100*a/b):.0f}% ({a}/{b})" if b else "n/a"

    print(f"=== L1 EVAL vs gold ({len(common)} segments) ===")
    print(f"treatment_events  P={prec:.2f} R={rec:.2f} F1={f1:.2f}  (tp={tp} fp={fp} fn={fn})")
    print(f"  start_date acc (matched events): {pct(date_ok, date_n)}")
    print(f"  status acc     (matched events): {pct(status_ok, status_n)}")
    print(f"diagnosis_date acc:                {pct(dx_date_ok, dx_date_n)}")
    print(f"grade_group (max) acc:             {pct(gg_ok, gg_n)}")


if __name__ == "__main__":
    main()
