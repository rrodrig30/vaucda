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
import re
import sys
from pathlib import Path

# record lists that carry a source_quote per item
_REC_LISTS = ("diagnoses", "treatment_events", "procedures", "imaging", "metastases")


def _resolve(rec: dict, haystacks: list, stats: list):
    """Resolve source_quote -> [span, source] using a flexible-whitespace regex
    over each haystack (segment, then pathology). Tolerates the newline/space
    normalization teachers apply when copying multi-line text into JSON, while
    keeping exact offsets in the original."""
    q = rec.pop("source_quote", None)
    span = None
    src = None
    if q and q.split():
        pat = re.compile(r"\s+".join(re.escape(t) for t in q.split()), re.S)
        for name, text in haystacks:
            m = pat.search(text)
            if m:
                span = [m.start(), m.end()]
                src = name
                break
    stats.append(span is not None)
    rec["source_span"] = span
    rec["source"] = src  # "segment" | "pathology" | None
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
        path_p = seg_dir / f"{sid}.pathology.txt"
        seg_text = seg_p.read_text(errors="ignore") if seg_p.exists() else ""
        path_text = path_p.read_text(errors="ignore") if path_p.exists() else ""
        haystacks = [("segment", seg_text), ("pathology", path_text)]
        out = {"segment_id": sid,
               "primary_context": lab.get("primary_context", "urologic")}
        for key in _REC_LISTS:
            out[key] = [_resolve(dict(r), haystacks, quote_stats) for r in (lab.get(key) or [])]
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
