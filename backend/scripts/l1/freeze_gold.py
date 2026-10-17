#!/usr/bin/env python3
"""
Freeze the L1 gold-label set: validate -> snapshot (read-only) -> checksummed
manifest. After freezing, the gold is the immutable answer key for training and
grading L1.

- Validates every label structurally against the v2 contract (required fields,
  category/modality/status/grade.system enums). Aborts if anything is invalid
  (rules.txt: no silent acceptance of bad data).
- Snapshots labels + segment meta + pathology refs to
  <gold_dir>/frozen/<version>/ and makes it read-only.
- Writes a PHI-free manifest (counts + sha256 + version) to
  scripts/l1/GOLD_FREEZE.json (committable) and into the snapshot.

Usage:
  ./venv/bin/python scripts/l1/freeze_gold.py <gold_dir> <version> "<reviewer note>"
"""
import hashlib
import json
import os
import shutil
import sys
from datetime import date
from pathlib import Path

CATEGORY = {"cancer", "benign", "indeterminate"}
MODALITY = {"prostatectomy", "radiation", "brachytherapy", "focal", "ADT", "ARSI",
            "chemotherapy", "radioligand", "immunotherapy", "active-surveillance",
            "nephrectomy", "partial-nephrectomy", "cystectomy", "TURBT",
            "intravesical", "other"}
STATUS = {"started", "ongoing", "completed", "discontinued", "declined", "planned"}
GRADE_SYS = {"gleason-isup", "fuhrman", "who", "other", None}
PRIMARY = {"urologic", "non_urologic"}


def validate(sid, lab):
    errs = []
    if lab.get("primary_context") not in PRIMARY:
        errs.append(f"primary_context={lab.get('primary_context')}")
    for k in ("diagnoses", "treatment_events", "procedures", "imaging", "metastases"):
        if not isinstance(lab.get(k), list):
            errs.append(f"{k} not a list")
    for d in lab.get("diagnoses") or []:
        if d.get("category") not in CATEGORY:
            errs.append(f"dx category={d.get('category')}")
        if not d.get("id") or not d.get("name"):
            errs.append("dx missing id/name")
        g = d.get("grade")
        if g and g.get("system") not in GRADE_SYS:
            errs.append(f"grade.system={g.get('system')}")
    for e in lab.get("treatment_events") or []:
        if e.get("modality") not in MODALITY:
            errs.append(f"tx modality={e.get('modality')}")
        if e.get("status") not in STATUS:
            errs.append(f"tx status={e.get('status')}")
    return [f"[{sid}] {x}" for x in errs]


def main():
    gold = Path(sys.argv[1])
    version = sys.argv[2] if len(sys.argv) > 2 else "1.0"
    note = sys.argv[3] if len(sys.argv) > 3 else ""
    lab_dir = gold / "labels"

    labels = {p.stem: json.loads(p.read_text()) for p in sorted(lab_dir.glob("*.json"))}
    if not labels:
        print("no labels to freeze")
        sys.exit(1)

    errors = []
    for sid, lab in labels.items():
        errors += validate(sid, lab)
    if errors:
        print(f"VALIDATION FAILED ({len(errors)} issues) — NOT frozen:")
        for e in errors[:40]:
            print("  " + e)
        sys.exit(2)

    # canonical content hash (order-independent)
    blob = json.dumps({k: labels[k] for k in sorted(labels)}, sort_keys=True).encode()
    sha = hashlib.sha256(blob).hexdigest()

    # stats
    from collections import Counter
    cats = Counter(); n_tx = n_img = n_proc = n_mets = 0; nonuro = 0
    for lab in labels.values():
        for d in lab.get("diagnoses") or []:
            cats[d.get("category")] += 1
        n_tx += len(lab.get("treatment_events") or [])
        n_img += len(lab.get("imaging") or [])
        n_proc += len(lab.get("procedures") or [])
        n_mets += len(lab.get("metastases") or [])
        if lab.get("primary_context") == "non_urologic":
            nonuro += 1

    manifest = {
        "gold_version": version,
        "schema_version": 2,
        "frozen_date": date.today().isoformat(),
        "reviewer_note": note,
        "n_segments": len(labels),
        "diagnoses_by_category": dict(cats),
        "n_treatment_events": n_tx, "n_imaging": n_img,
        "n_procedures": n_proc, "n_metastases": n_mets,
        "non_urologic_segments": nonuro,
        "content_sha256": sha,
    }

    # snapshot (read-only)
    snap = gold / "frozen" / version
    if snap.exists():
        for r, _d, fs in os.walk(snap):
            for f in fs:
                os.chmod(os.path.join(r, f), 0o644)
        shutil.rmtree(snap)
    (snap / "labels").mkdir(parents=True)
    for sid, lab in labels.items():
        (snap / "labels" / f"{sid}.json").write_text(json.dumps(lab, indent=1))
    for ext in ("*.meta.json", "*.pathology.txt"):
        (snap / "segments").mkdir(exist_ok=True)
        for p in (gold / "segments").glob(ext):
            shutil.copy(p, snap / "segments" / p.name)
    (snap / "FREEZE.json").write_text(json.dumps(manifest, indent=1))
    # committable PHI-free manifest
    Path(__file__).with_name("GOLD_FREEZE.json").write_text(json.dumps(manifest, indent=1))
    # make snapshot read-only
    for r, ds, fs in os.walk(snap):
        for f in fs:
            os.chmod(os.path.join(r, f), 0o444)

    print(f"FROZEN gold v{version}  ({len(labels)} segments)")
    print(json.dumps(manifest, indent=1))
    print(f"\nsnapshot (read-only): {snap}")
    print(f"manifest (committable): {Path(__file__).with_name('GOLD_FREEZE.json')}")


if __name__ == "__main__":
    main()
