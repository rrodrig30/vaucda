#!/usr/bin/env python3
"""
Persist teacher draft labels (v2) to <gold_dir>/labels/<id>.json, converting
each record's source_quote into a source_span by locating the quote in the
segment text. Unresolvable quotes are reported (usually a paraphrase — flag for
review).

Usage:
  ./venv/bin/python scripts/l1/write_labels.py <gold_dir> <workflow_result.json>
"""
import json
import sys
from pathlib import Path

# record lists that carry a source_quote per item
_REC_LISTS = ("diagnoses", "treatment_events", "procedures", "imaging", "metastases")


def _resolve(rec: dict, text: str, stats: list):
    q = rec.pop("source_quote", None)
    span = None
    if q:
        i = text.find(q)
        if i < 0:
            i = text.replace("\n", " ").find(" ".join(q.split()))
        if i >= 0:
            span = [i, i + len(q)]
    stats.append(span is not None)
    rec["source_span"] = span
    return rec


def main():
    gold_dir = Path(sys.argv[1])
    result = json.loads(Path(sys.argv[2]).read_text())
    labels = result.get("labels", result if isinstance(result, list) else [])
    out_dir = gold_dir / "labels"
    out_dir.mkdir(parents=True, exist_ok=True)
    seg_dir = gold_dir / "segments"

    written = 0
    quote_stats: list = []
    for lab in labels:
        sid = lab.get("segment_id")
        if not sid:
            continue
        seg_p = seg_dir / f"{sid}.txt"
        text = seg_p.read_text(errors="ignore") if seg_p.exists() else ""
        out = {"segment_id": sid,
               "primary_context": lab.get("primary_context", "urologic")}
        for key in _REC_LISTS:
            out[key] = [_resolve(dict(r), text, quote_stats) for r in (lab.get(key) or [])]
        (out_dir / f"{sid}.json").write_text(json.dumps(out, indent=1))
        written += 1

    resolved = sum(quote_stats)
    print(f"wrote {written} v2 draft labels to {out_dir}")
    if quote_stats:
        print(f"source spans resolved: {resolved}/{len(quote_stats)} "
              f"({100*resolved/len(quote_stats):.0f}%)")
    print("NEXT: regenerate review.html and have the urologist re-review.")


if __name__ == "__main__":
    main()
