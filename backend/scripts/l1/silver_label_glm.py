#!/usr/bin/env python3
"""
M2 silver labeler using GLM-5.2 (Ollama) as the teacher.

glm-5.2:cloud ignores Ollama's `format` schema and wraps output in fences, so
we put the full v2 schema in the PROMPT, parse leniently (fences / brace
balance / truncation recovery — reuse the HPI-v2 parser), validate
structurally, and retry. Produces a workflow-shaped result
({"labels":[{segment_id, ...source_quote...}]}) so the existing
write_labels.py / make_finetune_jsonl.py / agreement_gate.py consume it
unchanged.

Usage:
  ./venv/bin/python scripts/l1/silver_label_glm.py <train_dir> <out_result.json> [--limit N] [--workers 6]
"""
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.services.note_processing.agents.hpi_json_prompt import parse_hpi_json  # noqa: E402

MODEL = "glm-5.2:cloud"
OLLAMA = "http://localhost:11434/api/chat"

SCHEMA_SPEC = """Output a SINGLE JSON object with EXACTLY these fields (no extra fields):
{
 "primary_context": "urologic" | "non_urologic",
 "diagnoses": [ { "id":"dx1", "category":"cancer"|"benign"|"indeterminate", "name":"...", "site":<str|null>, "diagnosis_date":<"YYYY[-MM[-DD]]"|null>, "stage_tnm":<str|null>, "grade": { "system":"gleason-isup"|"fuhrman"|"who"|"other"|null, "gleason":<str|null>, "grade_group":<int 1-5|null>, "nuclear_grade":<int 1-4|null>, "who_grade":"low-grade"|"high-grade"|null, "bladder_stage":<str|null>, "value":<str|null> }|null, "risk":<str|null>, "source_quote":"verbatim snippet" } ],
 "treatment_events": [ { "for_diagnosis":<"dx1"|null>, "modality":"prostatectomy|radiation|brachytherapy|focal|ADT|ARSI|chemotherapy|radioligand|immunotherapy|active-surveillance|nephrectomy|partial-nephrectomy|cystectomy|TURBT|intravesical|other", "agent":<str|null>, "start_date":<str|null>, "end_date":<str|null>, "status":"started|ongoing|completed|discontinued|declined|planned", "intent":<str|null>, "source_quote":"..." } ],
 "procedures": [ { "type":"...", "date":<str|null>, "finding":<str|null>, "source_quote":"..." } ],
 "imaging": [ { "modality":"...", "date":<str|null>, "impression":<str|null>, "source_quote":"..." } ],
 "metastases": [ { "site":"...", "date":<str|null>, "source_quote":"..." } ]
}
Output ONLY the JSON object — no markdown fences, no commentary."""

RULES = """You are a urologic-oncology data abstractor. Extract structured facts from ONE note segment + the patient's surgical pathology.
- DIAGNOSES (one per distinct urologic diagnosis, cancer AND benign): category="cancer" ONLY when pathology confirms malignancy; "indeterminate" for a mass/lesion of UNKNOWN pathology (unbiopsied renal mass -> name "renal mass of uncertain significance", NEVER "benign"); "benign" only for known-benign conditions (ED, BPH, stones, simple cyst).
- diagnosis_date = biopsy-confirmed date for cancers, NOT earliest elevated-PSA date.
- GRADE is cancer-specific (ALWAYS search the pathology): prostate -> gleason-isup (gleason + grade_group MAX core); RCC -> fuhrman (nuclear_grade 1-4); bladder -> who (who_grade + bladder_stage). Leave grade null only if genuinely absent.
- TREATMENTS link to their cancer via for_diagnosis; keep specific agent + modality; fill start AND end date for ranges.
- procedures = INTERVENTIONS only; imaging = CT/MRI/US/PET/bone-scan; labs and DRE are NOT facts.
- primary_context = non_urologic for a non-urologic-primary tumor-board note (still capture cross-specialty treatment facts).
- Every record needs a verbatim source_quote. Dates ISO."""

CATS = {"cancer", "benign", "indeterminate"}
MODS = {"prostatectomy", "radiation", "brachytherapy", "focal", "ADT", "ARSI",
        "chemotherapy", "radioligand", "immunotherapy", "active-surveillance",
        "nephrectomy", "partial-nephrectomy", "cystectomy", "TURBT", "intravesical", "other"}
STATS = {"started", "ongoing", "completed", "discontinued", "declined", "planned"}


def _valid(d):
    if d.get("primary_context") not in ("urologic", "non_urologic"):
        return False
    for k in ("diagnoses", "treatment_events", "procedures", "imaging", "metastases"):
        if not isinstance(d.get(k), list):
            return False
    for x in d["diagnoses"]:
        if x.get("category") not in CATS or not x.get("name"):
            return False
    for x in d["treatment_events"]:
        if x.get("modality") not in MODS or x.get("status") not in STATS:
            return False
    return True


def _call(prompt, retry_note=""):
    body = {"model": MODEL, "stream": False, "options": {"temperature": 0},
            "messages": [{"role": "user", "content": prompt + retry_note}]}
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=240))
    return r["message"]["content"]


def label_one(train, sid):
    seg = (train / "segments" / f"{sid}.txt").read_text(errors="ignore")
    pth = (train / "segments" / f"{sid}.pathology.txt")
    path = pth.read_text(errors="ignore") if pth.exists() else "(no surgical pathology on file)"
    prompt = (RULES + "\n\n" + SCHEMA_SPEC
              + "\n\n=== NOTE SEGMENT ===\n" + seg
              + "\n\n=== SURGICAL PATHOLOGY ===\n" + path)
    note = ""
    for attempt in range(3):
        try:
            content = _call(prompt, note)
            draft, err = parse_hpi_json(content or "")
            if draft and _valid(draft):
                draft["segment_id"] = sid
                return draft
            note = ("\n\nYour previous output was invalid JSON or missing required "
                    "fields/enums. Re-emit ONLY the JSON object per the schema.")
        except Exception as e:
            note = f"\n\n(retry after error: {str(e)[:80]})"
    return None


def main():
    train = Path(sys.argv[1])
    out = Path(sys.argv[2])
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 6

    ids = [m["segment_id"] for m in json.load(open(train / "manifest.json"))]
    if limit:
        ids = ids[:limit]
    labels, failed, done = [], [], 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(label_one, train, sid): sid for sid in ids}
        for fut in as_completed(futs):
            sid = futs[fut]
            try:
                d = fut.result()
            except Exception:
                d = None
            if d:
                labels.append(d)
            else:
                failed.append(sid)
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(ids)} ({len(failed)} failed)", flush=True)
    out.write_text(json.dumps({"labeled": len(labels), "failed": failed, "labels": labels}))
    print(f"GLM silver: {len(labels)} labeled, {len(failed)} failed -> {out}")


if __name__ == "__main__":
    main()
