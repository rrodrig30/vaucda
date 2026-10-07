#!/usr/bin/env python3
"""
L1 narrative-segment extractor.

Splits a VistA clinic-prep extract into individual narrative note bodies (the
SPN consult/note section), which are L1's unit of input. Structured sections
(RXOP meds, CH/SLT labs, PLL problem list, DEM) are intentionally NOT segmented
here — they stay on the deterministic path.

Each segment is small (typically 0.5–8 KB), so it fits a 27B model's context
even though whole extracts run 156 KB median / 455 KB max.

CLI:
  ./venv/bin/python scripts/l1/segments.py <extract.txt>          # list segments
  ./venv/bin/python scripts/l1/segments.py <extract.txt> --dump <outdir>
"""
import hashlib
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# Allow running from the backend dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.note_processing.source_normalizers.vista_to_cprs import (  # noqa: E402
    split_vista_sections,
)

# Note header inside the SPN section: "MM/DD/YYYY HH:MM  Local Title: <TITLE>"
_NOTE_HDR = re.compile(
    r"(?m)^(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+\d{1,2}:\d{2}\s+"
    r"(?:Local|Standard)\s+Title:\s*(?P<title>[^\n]+)"
)

# Titles whose bodies carry treatment/diagnosis narrative worth extracting.
# (Used only to TAG segments for stratified sampling, not to drop any.)
_RICH_TITLE_RE = re.compile(
    r"ONCOLOGY|UROLOGY|TUMOR\s+BOARD|CONSULT|PROGRESS|H\s*&\s*P|HISTORY|"
    r"RADIATION|HEM[\s/-]*ONC",
    re.IGNORECASE,
)
_TREATMENT_HINT_RE = re.compile(
    r"prostatectom|radiation|\bXRT\b|\bEBRT\b|\bIMRT\b|\bSBRT\b|brachytherap|"
    r"leuprolide|eligard|lupron|goserelin|degarelix|abiraterone|enzalutamide|"
    r"apalutamide|darolutamide|docetaxel|cabazitaxel|lutetium|pluvicto|"
    r"cryoablat|nephrectom|cystectom|Gleason|Grade\s+Group",
    re.IGNORECASE,
)


@dataclass
class Segment:
    patient_file: str
    segment_id: str        # stable hash id
    note_date: str         # MM/DD/YYYY
    title: str
    char_len: int
    has_treatment_narrative: bool
    rich_title: bool
    text: str


def extract_segments(raw_text: str, patient_file: str = "") -> list:
    """Return the narrative Segments from one VistA extract (SPN notes)."""
    sections = split_vista_sections(raw_text)
    spn = sections.get("SPN", "")
    if not spn.strip():
        return []
    segs = []
    hdrs = list(_NOTE_HDR.finditer(spn))
    for i, m in enumerate(hdrs):
        start = m.start()
        end = hdrs[i + 1].start() if i + 1 < len(hdrs) else len(spn)
        body = spn[start:end].strip()
        if len(body) < 60:  # skip empty/stub notes
            continue
        title = m.group("title").strip()
        sid = hashlib.sha1(
            f"{patient_file}|{m.group('date')}|{title}|{len(body)}".encode()
        ).hexdigest()[:12]
        segs.append(Segment(
            patient_file=patient_file,
            segment_id=sid,
            note_date=m.group("date"),
            title=title,
            char_len=len(body),
            has_treatment_narrative=bool(_TREATMENT_HINT_RE.search(body)),
            rich_title=bool(_RICH_TITLE_RE.search(title)),
            text=body,
        ))
    return segs


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    fp = Path(sys.argv[1])
    segs = extract_segments(fp.read_text(errors="ignore"), fp.name)
    if "--dump" in sys.argv:
        outdir = Path(sys.argv[sys.argv.index("--dump") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        for s in segs:
            (outdir / f"{s.segment_id}.json").write_text(
                json.dumps(asdict(s), indent=1)
            )
        print(f"dumped {len(segs)} segments to {outdir}")
        return
    print(f"{fp.name}: {len(segs)} segments "
          f"({sum(s.has_treatment_narrative for s in segs)} with treatment narrative)")
    for s in segs:
        tag = "TX" if s.has_treatment_narrative else "  "
        print(f"  [{tag}] {s.note_date} {s.char_len:>6d}c  {s.title[:48]}")


if __name__ == "__main__":
    main()
