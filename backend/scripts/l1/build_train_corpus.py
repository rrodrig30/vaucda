#!/usr/bin/env python3
"""
M2: assemble the L1 SILVER training corpus.

Selects the treatment-narrative segments across the corpus, EXCLUDING the
frozen gold (held out for eval), and writes each segment's text + meta +
surgical-pathology reference into <train_dir>/segments/ — the same layout the
teacher labeler and write_labels expect. The teacher then draft-labels these
into silver training data; agreement_gate.py tiers them by confidence.

Usage:
  ./venv/bin/python scripts/l1/build_train_corpus.py <train_dir> [--limit N]
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from segments import extract_segments  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.note_processing.source_normalizers.vista_to_cprs import (  # noqa: E402
    split_vista_sections,
)

SOURCE_DIRS = ["../tests/Tumor_6_24_2026", "../tests/loose_batch", "../tests/Monday_batch"]


def main():
    train = Path(sys.argv[1])
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    gold_ids = {m["segment_id"] for m in json.load(open("../tests/l1_gold/manifest.json"))}
    seg_dir = train / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    # cache patient SP pathology
    sp_cache: dict = {}
    manifest, seen = [], set()
    for d in SOURCE_DIRS:
        for f in sorted(Path(d).glob("*.txt")):
            raw = f.read_text(errors="ignore")
            sp = sp_cache.setdefault(f.name, split_vista_sections(raw).get("SP", ""))
            for s in extract_segments(raw, f.name):
                if not s.has_treatment_narrative:
                    continue
                if s.segment_id in gold_ids or s.segment_id in seen:
                    continue
                seen.add(s.segment_id)
                (seg_dir / f"{s.segment_id}.txt").write_text(s.text)
                meta = {k: v for k, v in asdict(s).items() if k != "text"}
                (seg_dir / f"{s.segment_id}.meta.json").write_text(json.dumps(meta, indent=1))
                body = (sp.strip() if sp.strip() and "No data available" not in sp
                        else "(no surgical pathology on file)")
                content = body if body.startswith("(no") else (
                    "=== PATIENT SURGICAL PATHOLOGY (SP) — search for each "
                    "cancer's grade; confirm mass malignancy ===\n" + body)
                (seg_dir / f"{s.segment_id}.pathology.txt").write_text(content)
                manifest.append(meta)
                if limit and len(manifest) >= limit:
                    break
            if limit and len(manifest) >= limit:
                break
        if limit and len(manifest) >= limit:
            break

    (train / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"train corpus: {len(manifest)} segments (gold held out) -> {seg_dir}")
    print(json.dumps([m["segment_id"] for m in manifest]))


if __name__ == "__main__":
    main()
