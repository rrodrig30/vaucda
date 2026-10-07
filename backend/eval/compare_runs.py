#!/usr/bin/env python
"""Side-by-side comparison of two eval scorecards (JSON from run_eval --json).

Usage:
  python -m eval.compare_runs A.json B.json

Prints per-metric pass rates for A vs B, the per-patient/per-metric cells that
DIFFER, and a plain-English verdict on whether B helped, hurt, or was neutral
vs A. Use it to answer questions like "does L1 actually improve accuracy?"
with numbers.
"""
from __future__ import annotations

import json
import sys

METRICS = ["primary_diagnosis", "no_false_diagnosis", "no_cross_cancer",
           "psa_grounded", "completeness"]


def _load(path):
    with open(path) as f:
        return json.load(f)


def _rate(run, metric):
    passed = tot = 0
    for p in run["patients"].values():
        if not p or metric not in p:
            continue
        tot += 1
        passed += 1 if p[metric]["passed"] else 0
    return passed, tot


def main(argv):
    if len(argv) != 2:
        print("usage: python -m eval.compare_runs A.json B.json", file=sys.stderr)
        return 2
    A, B = _load(argv[0]), _load(argv[1])
    la, lb = A.get("label", argv[0]), B.get("label", argv[1])

    print(f"\n{'='*78}\nEVAL COMPARISON\n  A = {la}\n  B = {lb}\n{'='*78}\n")

    # per-metric pass rates
    print(f"{'metric':22}{'A':>16}{'B':>16}{'Δ (B-A)':>12}")
    print("-" * 66)
    a_tot = b_tot = a_pass = b_pass = 0
    for m in METRICS:
        ap, at = _rate(A, m)
        bp, bt = _rate(B, m)
        a_pass += ap; a_tot += at; b_pass += bp; b_tot += bt
        ar = ap / at * 100 if at else 0
        br = bp / bt * 100 if bt else 0
        print(f"{m:22}{f'{ar:.0f}% ({ap}/{at})':>16}"
              f"{f'{br:.0f}% ({bp}/{bt})':>16}{f'{br-ar:+.0f}pp':>12}")
    ao = a_pass / a_tot * 100 if a_tot else 0
    bo = b_pass / b_tot * 100 if b_tot else 0
    print("-" * 66)
    print(f"{'OVERALL':22}{f'{ao:.1f}% ({a_pass}/{a_tot})':>16}"
          f"{f'{bo:.1f}% ({b_pass}/{b_tot})':>16}{f'{bo-ao:+.1f}pp':>12}")

    # per-patient cells that differ
    print("\nPER-PATIENT DIFFERENCES (only cells where A and B disagree):")
    any_diff = False
    b_better = b_worse = 0
    for pid in sorted(set(A["patients"]) | set(B["patients"])):
        pa, pb = A["patients"].get(pid), B["patients"].get(pid)
        if not pa or not pb:
            print(f"  {pid}: missing in {'A' if not pa else 'B'} — skipped")
            continue
        for m in METRICS:
            if m not in pa or m not in pb:
                continue
            if pa[m]["passed"] != pb[m]["passed"]:
                any_diff = True
                if pb[m]["passed"]:
                    b_better += 1
                    print(f"  ✅ {pid} / {m}: A FAIL → B PASS")
                    print(f"        A: {pa[m]['detail']}")
                else:
                    b_worse += 1
                    print(f"  ❌ {pid} / {m}: A PASS → B FAIL")
                    print(f"        B: {pb[m]['detail']}")
    if not any_diff:
        print("  (none — A and B score identically on every metric/patient)")

    # verdict
    print(f"\n{'='*78}")
    delta = bo - ao
    if b_better == 0 and b_worse == 0:
        verdict = "NEUTRAL — B changes nothing measurable vs A."
    elif b_better > b_worse:
        verdict = f"B HELPS — {b_better} cell(s) fixed, {b_worse} regressed ({delta:+.1f}pp overall)."
    elif b_worse > b_better:
        verdict = f"B HURTS — {b_worse} cell(s) regressed, {b_better} fixed ({delta:+.1f}pp overall)."
    else:
        verdict = f"MIXED — {b_better} fixed, {b_worse} regressed (net {delta:+.1f}pp)."
    print(f"VERDICT: {verdict}\n{'='*78}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
