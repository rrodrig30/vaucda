#!/usr/bin/env python3
"""
For each gold segment, write the patient's SURGICAL PATHOLOGY (SP) section to
<gold_dir>/segments/<id>.pathology.txt, so the labeler/L1 can ALWAYS search
pathology results for each cancer's grade and to confirm whether a mass is
biopsy-proven malignant (vs. of uncertain pathology).

Grades frequently live in SP ("CLEAR-CELL RENAL CELL CARCINOMA, GRADE 1",
"GLEASON'S GRADE 3+4=7"), NOT in the consult narrative.

Usage:
  ./venv/bin/python scripts/l1/add_pathology.py <gold_dir>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.note_processing.source_normalizers.vista_to_cprs import (  # noqa: E402
    split_vista_sections,
)

SOURCE_DIRS = [
    Path(__file__).resolve().parents[2] / "../tests/Tumor_6_24_2026",
    Path(__file__).resolve().parents[2] / "../tests/loose_batch",
    Path(__file__).resolve().parents[2] / "../tests/Monday_batch",
]


def _locate(name):
    for d in SOURCE_DIRS:
        if (d / name).exists():
            return d / name
    return None


def main():
    gold = Path(sys.argv[1])
    seg_dir = gold / "segments"
    written = had_path = 0
    src_cache: dict = {}
    for meta_p in sorted(seg_dir.glob("*.meta.json")):
        meta = json.loads(meta_p.read_text())
        pf = meta["patient_file"]
        if pf not in src_cache:
            sp = ""
            src = _locate(pf)
            if src:
                sp = split_vista_sections(src.read_text(errors="ignore")).get("SP", "")
            src_cache[pf] = sp
        sp = src_cache[pf]
        body = sp.strip() if sp.strip() and "No data available" not in sp else \
            "(no surgical pathology on file)"
        if body.startswith("(no"):
            content = body
        else:
            had_path += 1
            content = ("=== PATIENT SURGICAL PATHOLOGY (SP) — search for each "
                       "cancer's grade; confirm mass malignancy ===\n" + body)
        (seg_dir / f"{meta['segment_id']}.pathology.txt").write_text(content)
        written += 1
    print(f"wrote {written} pathology references ({had_path} with pathology data) "
          f"to {seg_dir}")


if __name__ == "__main__":
    main()
