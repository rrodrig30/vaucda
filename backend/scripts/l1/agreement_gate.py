#!/usr/bin/env python3
"""
M2: confidence-tier the silver labels by agreement with the regex baseline.

The regex baseline is high-precision on the EASY facts. So:
- silver that CONTAINS the regex-found facts (no contradiction) = consistent;
  the teacher's extra facts are its recall gain (the training signal).
- silver that DROPS regex-found facts = a possible teacher miss -> low tier,
  flag for review.

This does NOT filter — every silver example is kept for training; the tier is
a weight / QA signal. Writes <train_dir>/confidence.json.

Usage:
  ./venv/bin/python scripts/l1/agreement_gate.py <train_dir>
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from regex_baseline import to_l1  # noqa: E402


def _norm_y(d):
    m = re.match(r"(\d{4})", str(d or ""))
    return m.group(1) if m else None


def _ev_match(a, b):
    if (a.get("modality") or "").lower() != (b.get("modality") or "").lower():
        return False
    if _norm_y(a.get("start_date")) and _norm_y(a.get("start_date")) == _norm_y(b.get("start_date")):
        return True
    aa, ba = (a.get("agent") or "").lower(), (b.get("agent") or "").lower()
    return bool(aa and ba and aa.split()[0] == ba.split()[0])


def main():
    train = Path(sys.argv[1])
    seg_dir, lab_dir = train / "segments", train / "labels"
    conf = {}
    for lab_p in sorted(lab_dir.glob("*.json")):
        sid = lab_p.stem
        silver = json.loads(lab_p.read_text())
        seg = (seg_dir / f"{sid}.txt")
        if not seg.exists():
            continue
        rx = to_l1(seg.read_text(errors="ignore"), sid)
        rtx, stx = rx.get("treatment_events") or [], silver.get("treatment_events") or []
        matched = sum(1 for re_ev in rtx if any(_ev_match(re_ev, se) for se in stx))
        consistency = matched / len(rtx) if rtx else 1.0
        # regex prostate dx present but silver has no cancer dx => contradiction
        rx_has_cancer = any(d.get("category") == "cancer" for d in rx.get("diagnoses") or [])
        s_has_cancer = any(d.get("category") == "cancer" for d in silver.get("diagnoses") or [])
        dx_contra = rx_has_cancer and not s_has_cancer
        tier = ("high" if consistency >= 0.8 and not dx_contra else
                "medium" if consistency >= 0.5 and not dx_contra else "low")
        conf[sid] = {
            "tier": tier, "consistency": round(consistency, 2),
            "regex_tx": len(rtx), "silver_tx": len(stx),
            "silver_dx": len(silver.get("diagnoses") or []),
            "dx_contradiction": dx_contra,
        }
    (train / "confidence.json").write_text(json.dumps(conf, indent=1))
    from collections import Counter
    tiers = Counter(c["tier"] for c in conf.values())
    print(f"gated {len(conf)} silver labels -> {train/'confidence.json'}")
    print("tiers:", dict(tiers))
    lows = [s for s, c in conf.items() if c["tier"] == "low"]
    if lows:
        print(f"low-tier (review — silver dropped regex facts): {lows[:8]}{'...' if len(lows)>8 else ''}")


if __name__ == "__main__":
    main()
