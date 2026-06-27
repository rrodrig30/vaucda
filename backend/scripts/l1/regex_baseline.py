#!/usr/bin/env python3
"""
Export the CURRENT (regex/heuristic) extractors' output per gold segment, in
the L1 schema, as the baseline candidate L1 must beat (scope-doc milestone 3
exit criterion: "beats regex per-field on gold").

For each <gold_dir>/segments/<id>.txt, runs extract_clinical_timeline (the
narrative extractor L1 replaces) and maps its events to the L1 schema, then
writes <out_dir>/labels/<id>.json.

Usage:
  ./venv/bin/python scripts/l1/regex_baseline.py <gold_dir> <out_dir>
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.note_processing.clinical_timeline import (  # noqa: E402
    extract_clinical_timeline,
)

# timeline modality string -> (L1 modality, agent or None)
_MOD_MAP = [
    (r"prostatectomy", ("prostatectomy", None)),
    (r"radiation", ("radiation", None)),
    (r"brachytherapy", ("brachytherapy", None)),
    (r"Lu-177|PSMA", ("radioligand", "Lu-177 PSMA")),
    (r"abiraterone", ("ARSI", "abiraterone")),
    (r"enzalutamide", ("ARSI", "enzalutamide")),
    (r"apalutamide", ("ARSI", "apalutamide")),
    (r"darolutamide", ("ARSI", "darolutamide")),
    (r"bicalutamide", ("ADT", "bicalutamide")),
    (r"Eligard|leuprolide|goserelin|degarelix|ADT", ("ADT", "leuprolide")),
    (r"chemotherapy|docetaxel|cabazitaxel", ("chemotherapy", None)),
    (r"nephrectomy", ("nephrectomy", None)),
    (r"cystectomy", ("cystectomy", None)),
    (r"focal|cryo", ("focal", None)),
]
_STATUS = {"TREATMENT_STARTED": "started", "TREATMENT_COMPLETED": "completed",
           "TREATMENT_RESTARTED": "ongoing", "TREATMENT_DECLINED": "declined"}


def _map_mod(modality: str):
    for pat, out in _MOD_MAP:
        if re.search(pat, modality, re.I):
            return out
    return ("other", modality or None)


def _iso(date_key: str):
    return date_key or None  # timeline date_key is already ISO-ish (YYYY[-MM[-DD]])


_GLEASON_TO_GG = {"3+3": 1, "3+4": 2, "4+3": 3, "4+4": 4, "3+5": 4, "5+3": 4,
                  "4+5": 5, "5+4": 5, "5+5": 5}


def _max_gg(text: str):
    ggs = [int(g) for g in re.findall(r"Grade\s+Group\s+(\d)", text, re.I)]
    gl = None
    for a, b in re.findall(r"\b([3-5])\s*\+\s*([3-5])\b", text):
        ggs.append(_GLEASON_TO_GG.get(f"{a}+{b}", 0))
        gl = f"{a}+{b}"
    return (max(ggs) if ggs else None), gl


def to_l1(segment_text: str, sid: str) -> dict:
    tl = extract_clinical_timeline(segment_text)
    tx, dx = [], None
    for e in tl:
        if e.event_type.startswith("TREATMENT_") and e.modality:
            mod, agent = _map_mod(e.modality)
            tx.append({
                "modality": mod, "agent": agent,
                "start_date": _iso(e.date_key), "end_date": None,
                "status": _STATUS.get(e.event_type, "started"),
                "intent": None, "source_span": None,
            })
        elif e.event_type == "DIAGNOSIS" and dx is None:
            dx = {"cancer_type": e.modality or "cancer",
                  "diagnosis_date": _iso(e.date_key),
                  "gleason": None, "grade_group": None,
                  "stage_tnm": None, "risk": None, "source_span": None}
    # Grade group / Gleason — the production pipeline extracts these in
    # patient_status_facts/pathology, so include them for a fair baseline.
    gg, gl = _max_gg(segment_text)
    if gg is not None:
        if dx is None:
            dx = {"cancer_type": "prostate cancer", "diagnosis_date": None,
                  "stage_tnm": None, "risk": None, "source_span": None}
        dx["grade_group"], dx["gleason"] = gg, gl
    return {"segment_id": sid, "diagnosis": dx, "treatment_events": tx,
            "procedures": [], "metastases": []}


def main():
    gold_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    seg_dir = gold_dir / "segments"
    ld = out_dir / "labels"
    ld.mkdir(parents=True, exist_ok=True)
    n = 0
    for seg in sorted(seg_dir.glob("*.txt")):
        sid = seg.stem
        (ld / f"{sid}.json").write_text(
            json.dumps(to_l1(seg.read_text(errors="ignore"), sid), indent=1))
        n += 1
    print(f"wrote {n} regex-baseline extractions to {ld}")


if __name__ == "__main__":
    main()
