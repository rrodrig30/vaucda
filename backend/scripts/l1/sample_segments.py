#!/usr/bin/env python3
"""
Stratified, DETERMINISTIC sampler for the L1 gold-eval segment set.

Selects ~N narrative segments across the test corpus, prioritizing
treatment-narrative segments (what L1 most needs to get right), capping per
patient for diversity, and spreading across cancer types / note titles.

Writes, into <gold_dir>/segments/:
    <segment_id>.txt      the raw segment text (what L1 / the labeler sees)
    <segment_id>.meta.json segment metadata
and <gold_dir>/manifest.json (the frozen sample list).

Deterministic: ordering is by sha1(segment_id) so re-running reproduces the
same set (no RNG).

Usage:
  ./venv/bin/python scripts/l1/sample_segments.py <gold_dir> [N] [dir1 dir2 ...]
"""
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from segments import extract_segments  # noqa: E402

DEFAULT_DIRS = [
    "../tests/Tumor_6_24_2026",
    "../tests/loose_batch",
    "../tests/Monday_batch",
]
PER_PATIENT_CAP = 2  # diversity: at most this many segments per patient


def _hash(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def main():
    gold_dir = Path(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 100
    dirs = sys.argv[3:] or DEFAULT_DIRS

    # Collect all segments.
    allsegs = []
    seen_patient = set()
    for d in dirs:
        for f in sorted(Path(d).glob("*.txt")):
            seen_patient.add(f.name)
            allsegs += extract_segments(f.read_text(errors="ignore"), f.name)

    # Stratify: treatment-narrative first, then deterministic order; cap per pt.
    def sort_key(s):
        # rich + treatment segments first, then stable by hash
        rank = (0 if s.has_treatment_narrative else 1, 0 if s.rich_title else 1)
        return (*rank, _hash(s.segment_id))

    allsegs.sort(key=sort_key)
    picked, per_pt = [], {}
    for s in allsegs:
        if per_pt.get(s.patient_file, 0) >= PER_PATIENT_CAP:
            continue
        picked.append(s)
        per_pt[s.patient_file] = per_pt.get(s.patient_file, 0) + 1
        if len(picked) >= n:
            break

    segdir = gold_dir / "segments"
    segdir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for s in picked:
        (segdir / f"{s.segment_id}.txt").write_text(s.text)
        meta = {k: v for k, v in asdict(s).items() if k != "text"}
        (segdir / f"{s.segment_id}.meta.json").write_text(json.dumps(meta, indent=1))
        manifest.append(meta)
    (gold_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))

    tx = sum(m["has_treatment_narrative"] for m in manifest)
    print(f"sampled {len(picked)} segments from {len(seen_patient)} patients "
          f"({tx} treatment-narrative) -> {segdir}")
    print(f"manifest: {gold_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
