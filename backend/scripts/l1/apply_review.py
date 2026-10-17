#!/usr/bin/env python3
"""
Fold a clinician's review verdicts (from review.html's "Download review") back
into the gold labels.

- verdict "ok"  -> stamps the label as reviewed/approved (frozen).
- verdict "fix" -> stamps the correction note for action; these are listed so
  the structured fix can be applied (by hand or with assistance).

Usage:
  ./venv/bin/python scripts/l1/apply_review.py <gold_dir> <review_verdicts.json>
"""
import json
import sys
from pathlib import Path


def main():
    gold = Path(sys.argv[1])
    verdicts = json.loads(Path(sys.argv[2]).read_text())
    lab_dir = gold / "labels"
    ok = fix = unrev = 0
    fixes = []
    for sid, v in verdicts.items():
        p = lab_dir / f"{sid}.json"
        if not p.exists():
            continue
        lab = json.loads(p.read_text())
        lab["_review"] = {"verdict": v.get("verdict", "unreviewed"),
                          "correction": v.get("correction", "")}
        p.write_text(json.dumps(lab, indent=1))
        if v.get("verdict") == "ok":
            ok += 1
        elif v.get("verdict") == "fix":
            fix += 1
            fixes.append((sid, v.get("correction", "").strip()))
        else:
            unrev += 1

    print(f"approved (ok): {ok}   needs-fix: {fix}   unreviewed: {unrev}")
    if fixes:
        print("\n--- corrections to apply ---")
        for sid, note in fixes:
            print(f"  {sid}: {note or '(no note)'}")
    frozen = ok + fix  # everything touched; ok are final, fix pending structured edit
    print(f"\n{ok} labels approved & frozen. {fix} pending structured correction.")
    print("Share this run (or the review_verdicts.json) and the 'needs-fix' "
          "items can be corrected in the JSON for you.")


if __name__ == "__main__":
    main()
