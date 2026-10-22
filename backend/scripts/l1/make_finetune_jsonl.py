#!/usr/bin/env python3
"""
M2: package silver labels into a LoRA SFT JSONL for fine-tuning medgemma-27b.

Each training example is a chat pair:
  user  = the L1 extraction instruction + the segment text + the patient's
          surgical-pathology reference (exactly what L1 sees at inference)
  assistant = the silver v2 extraction JSON (source_quote form — the model
          emits quotes; a deterministic step resolves them to spans, matching
          the labeler).

Reads the RAW teacher result (labels carry source_quote). Optionally stamps a
confidence tier from agreement_gate.py.

Usage:
  ./venv/bin/python scripts/l1/make_finetune_jsonl.py <train_dir> <result.json> <out.jsonl> [confidence.json]
"""
import json
import sys
from pathlib import Path

# The inference-time instruction (mirrors the labeler prompt, minus the
# "gold-standard" framing). Kept in sync with label_segments.workflow.js.
INSTRUCTION = """You are a urologic-oncology data abstractor. Extract structured clinical facts from ONE narrative note segment plus the patient's surgical pathology, into the v2 schema.

Rules:
- DIAGNOSES (one per distinct urologic diagnosis, cancer AND benign): category=cancer only when pathology confirms malignancy; category=indeterminate for a mass/lesion of unknown pathology (e.g. unbiopsied renal mass — name it "renal mass of uncertain significance", NEVER "benign"); category=benign only for known-benign conditions (ED, BPH, stones, simple cyst).
- diagnosis_date = biopsy-confirmed date for cancers, NOT earliest elevated-PSA date.
- GRADE is cancer-specific (always SEARCH the pathology): prostate -> gleason-isup (gleason + grade_group MAX core); RCC -> fuhrman (nuclear_grade 1-4); bladder -> who (who_grade + bladder_stage). Leave grade null only if genuinely absent.
- TREATMENTS link to their cancer via for_diagnosis; keep specific agent (leuprolide/abiraterone/Lu-177 PSMA/IMRT) plus modality; fill start_date AND end_date for ranges.
- procedures = INTERVENTIONS only; imaging[] = CT/MRI/US/PET/bone-scan; labs and DRE are NOT facts here.
- primary_context = non_urologic for a non-urologic-primary tumor-board note (still capture cross-specialty treatment facts).
- Every record needs a verbatim source_quote. Dates ISO. Return ONLY the JSON object."""


def main():
    train = Path(sys.argv[1])
    result = json.loads(Path(sys.argv[2]).read_text())
    out = Path(sys.argv[3])
    conf = json.loads(Path(sys.argv[4]).read_text()) if len(sys.argv) > 4 and Path(sys.argv[4]).exists() else {}

    labels = result.get("labels", result if isinstance(result, list) else [])
    seg_dir = train / "segments"
    n = 0
    with out.open("w") as fh:
        for lab in labels:
            sid = lab.get("segment_id")
            seg_p, path_p = seg_dir / f"{sid}.txt", seg_dir / f"{sid}.pathology.txt"
            if not seg_p.exists():
                continue
            seg = seg_p.read_text(errors="ignore")
            path = path_p.read_text(errors="ignore") if path_p.exists() else "(no surgical pathology on file)"
            target = {k: v for k, v in lab.items() if k != "segment_id"}
            user = (INSTRUCTION + "\n\n=== NOTE SEGMENT ===\n" + seg
                    + "\n\n=== SURGICAL PATHOLOGY ===\n" + path)
            rec = {
                "segment_id": sid,
                "confidence": conf.get(sid, {}).get("tier", "unknown"),
                "messages": [
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": json.dumps(target, ensure_ascii=False)},
                ],
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"wrote {n} SFT examples -> {out}")
    if conf:
        from collections import Counter
        tiers = Counter(conf.get(s, {}).get("tier", "unknown") for s in [l["segment_id"] for l in labels])
        print("confidence tiers:", dict(tiers))


if __name__ == "__main__":
    main()
