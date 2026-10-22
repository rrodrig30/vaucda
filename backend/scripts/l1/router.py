#!/usr/bin/env python3
"""
L1 section router (milestone 1).

Splits a VistA clinic-prep extract into:
  - NARRATIVE sections  -> per-note segments for L1 (each tagged urologic /
    non_urologic), the part regex extracts poorly.
  - STRUCTURED sections -> left for the EXISTING deterministic extractors,
    UNCHANGED (RXOP meds, CH/SLT/MIC labs, PLL/PLA problem list, SR surgery,
    SP pathology, II imaging, AR allergies). SP is also surfaced as the L1
    pathology grade-reference.

Goal (scope-doc M1 exit): every section is routed; the structured path is
untouched. No model is invoked here — this is the boundary that L1 plugs into
in M4.

CLI:
  ./venv/bin/python scripts/l1/router.py <extract.txt>            # show routing
  ./venv/bin/python scripts/l1/router.py --validate [dir ...]     # corpus coverage
"""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.note_processing.source_normalizers.vista_to_cprs import (  # noqa: E402
    split_vista_sections,
)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from segments import extract_segments  # noqa: E402

# Section codes -> destination. SPN (tumor-board / consult notes) is the only
# narrative section; everything else is structured (deterministic path).
NARRATIVE_CODES = {"SPN"}
STRUCTURED_CODES = {"PLL", "PLA", "RXOP", "SR", "SP", "II",
                    "CH", "SLT", "MIC", "AR", "CT"}
PATHOLOGY_CODE = "SP"  # also fed to L1 as the grade reference

_URO = re.compile(
    r"prostate|prostatic|\bPSA\b|\bRCC\b|renal cell|renal mass|kidney|nephr|"
    r"bladder|urotheli|\bTURBT\b|cystoscop|ureter|testic|penile|adrenal|"
    r"urolog|GU\b|hydronephro|nephrolithiasis|urolithiasis|\bBPH\b|\bLUTS\b",
    re.IGNORECASE)
_NONURO_CA = re.compile(
    r"\b(lung|colon|colorectal|pancrea\w+|breast|gastric|hepatocellular|"
    r"esophag\w+|ovarian|endometrial|glioma|melanoma|lymphoma|leukemia|"
    r"head and neck|cholangio\w+|small cell|non.small cell)\b"
    r"[^.\n]{0,30}(cancer|carcinoma|malignan|tumou?r|adenocarc|mass|lesion)",
    re.IGNORECASE)


def is_urologic_segment(text: str) -> bool:
    """Conservative: a segment is non_urologic only when a NON-urologic cancer
    is named AND there is no urologic anchor. Default urologic (keep)."""
    if _URO.search(text):
        return True
    return not _NONURO_CA.search(text)


@dataclass
class RouteResult:
    narrative_segments: list = field(default_factory=list)   # [(Segment, primary_context)]
    structured: dict = field(default_factory=dict)           # {code: body} (deterministic path)
    pathology: str = ""                                      # SP body (L1 grade ref)
    unknown_codes: list = field(default_factory=list)        # sections we don't classify


def route_extract(raw_text: str, patient_file: str = "") -> RouteResult:
    sections = split_vista_sections(raw_text)
    res = RouteResult()
    for code, body in sections.items():
        if code in NARRATIVE_CODES:
            continue  # handled via extract_segments below
        elif code in STRUCTURED_CODES:
            res.structured[code] = body
        else:
            res.unknown_codes.append(code)
    res.pathology = sections.get(PATHOLOGY_CODE, "")
    for seg in extract_segments(raw_text, patient_file):
        ctx = "urologic" if is_urologic_segment(seg.text) else "non_urologic"
        res.narrative_segments.append((seg, ctx))
    return res


def _validate(dirs):
    import glob
    from app.services.note_processing.source_normalizers.vista_to_cprs import _KNOWN_CODES
    seen_codes = set()
    n_files = n_segs = n_nonuro = 0
    narr_bytes = struct_bytes = 0
    orphans = set()
    for d in dirs:
        for f in glob.glob(d + "/*.txt"):
            n_files += 1
            raw = Path(f).read_text(errors="ignore")
            r = route_extract(raw, Path(f).name)
            for code in split_vista_sections(raw):
                seen_codes.add(code)
            orphans |= set(r.unknown_codes)
            struct_bytes += sum(len(b) for b in r.structured.values())
            for seg, ctx in r.narrative_segments:
                n_segs += 1
                narr_bytes += seg.char_len
                if ctx == "non_urologic":
                    n_nonuro += 1
    classified = NARRATIVE_CODES | STRUCTURED_CODES
    print(f"files routed: {n_files}")
    print(f"section codes seen: {sorted(seen_codes)}")
    print(f"all classified: {seen_codes <= classified}  (orphans: {sorted(orphans) or 'none'})")
    print(f"narrative segments (-> L1): {n_segs}  ({n_nonuro} non_urologic)")
    tot = narr_bytes + struct_bytes or 1
    print(f"byte split: narrative {narr_bytes} ({100*narr_bytes//tot}%) | "
          f"structured {struct_bytes} ({100*struct_bytes//tot}%)")
    print(f"known codes in normalizer: {sorted(_KNOWN_CODES)}")


def main():
    if "--validate" in sys.argv:
        dirs = [a for a in sys.argv[2:] if not a.startswith("--")] or [
            "../tests/Tumor_6_24_2026", "../tests/loose_batch", "../tests/Monday_batch"]
        _validate(dirs)
        return
    fp = Path(sys.argv[1])
    r = route_extract(fp.read_text(errors="ignore"), fp.name)
    print(f"{fp.name}")
    print(f"  structured (deterministic, unchanged): {sorted(r.structured)}")
    print(f"  pathology reference (SP): {len(r.pathology)} chars")
    print(f"  narrative segments -> L1: {len(r.narrative_segments)}")
    for seg, ctx in r.narrative_segments:
        print(f"    [{ctx:12s}] {seg.note_date} {seg.char_len:>6d}c  {seg.title[:46]}")
    if r.unknown_codes:
        print(f"  UNKNOWN (unrouted) codes: {r.unknown_codes}")


if __name__ == "__main__":
    main()
