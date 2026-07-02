#!/usr/bin/env python3
"""
Batch note generator for the Tumor clinic test set.

Replicates the /generate-express server flow (Stage 1 + Stage 2, no
calculators, RAG disabled for reproducibility) against the production
DB-configured models (gpt-oss:120b-cloud) so generated notes match what
the live app produces.

Usage:
    ./venv/bin/python scripts/batch_generate_notes.py <input_dir> <output_dir> [file1.txt file2.txt ...]

If specific filenames are given, only those are (re)generated; otherwise
every *.txt in <input_dir> (excluding the output/ subdir) is processed.
"""
import sys
import time
import traceback
from pathlib import Path

# CRITICAL: replicate app/main.py — load backend/.env into os.environ so
# VAUCDA_* feature flags read via os.environ.get() (VAUCDA_HPI_V2,
# VAUCDA_CONSISTENCY_CHECK, ...) match the production app. Pydantic
# settings does NOT populate os.environ, so without this the pipeline
# silently runs the v1 HPI path instead of production's v2.
from dotenv import load_dotenv as _load_dotenv
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
_load_dotenv(_ENV_PATH)

from app.services.note_processing.note_builder import (
    build_urology_note,
    build_authoritative_patient_facts,
)
from app.services.note_processing.note_identifier import identify_notes
from app.services.note_processing.stage2_builder import build_stage2_note
from app.services.llm_config_manager import LLMConfigManager, LLMTaskType

# Production config pulled from data/vaucda.db user f09a0349 preferences.
STAGE1_MODEL = "gpt-oss:120b-cloud"
STAGE2_MODEL = "gpt-oss:120b-cloud"
# Production user has source_format='vista' — input is a VistA CLINIC PREP
# EXTRACT, NOT CPRS. The VistA->CPRS normalizer must run first or every
# document-level extractor (PMH/PSH/MEDS/PATH) sees the wrong layout and
# returns empty, collapsing the v2 HPI to a "new patient" stub.
SOURCE_FORMAT = "vista"


def make_configs():
    mgr = LLMConfigManager()
    mgr._load_from_environment()
    mgr._loaded = True
    s1 = mgr.get_config(LLMTaskType.STAGE1)
    s2 = mgr.get_config(LLMTaskType.STAGE2)
    s1.provider, s1.model = "ollama", STAGE1_MODEL
    s2.provider, s2.model = "ollama", STAGE2_MODEL
    # Disable RAG: matches express routine-note path and avoids Neo4j dep.
    s2.use_rag = False
    s2.use_graphrag = False
    return s1, s2


import re as _re

# Default visit date if a file has no parseable clinic-header date.
DEFAULT_VISIT_DATE = "06/24/2026"


def _detect_visit_date(text: str) -> str:
    """Read the clinic-header visit date ("CLINIC : ... DATE: 6/24/2026")
    so each batch/file anchors age/IPSS/recency on its OWN visit date
    rather than a hardcoded one. Falls back to DEFAULT_VISIT_DATE."""
    m = _re.search(r"\bDATE:\s*(\d{1,2}/\d{1,2}/\d{4})", text[:4000])
    return m.group(1) if m else DEFAULT_VISIT_DATE


def generate_one(text: str, s1, s2) -> str:
    # Prepend the visit date so age/IPSS extractors anchor on the real
    # clinic date for THIS file (batches span 6/21, 6/24, 6/29).
    clinical_input = f"VISIT DATE: {_detect_visit_date(text)}\n\n{text}"
    # Phase 1: compute the authoritative facts ONCE and pass to both stages
    # so Stage 2's Assessment grounds on the same facts as the HPI.
    facts = build_authoritative_patient_facts(clinical_input, SOURCE_FORMAT)
    stage1 = build_urology_note(
        clinical_text=clinical_input, task_config=s1,
        source_format=SOURCE_FORMAT, patient_facts=facts,
    )
    notes_dict = identify_notes(text)
    gu_notes = notes_dict.get("gu_notes", [])
    non_gu_notes = notes_dict.get("non_gu_notes", [])
    final = build_stage2_note(
        stage1_note=stage1,
        gu_notes=gu_notes,
        non_gu_notes=non_gu_notes,
        ambient_transcript=None,
        calculator_results={},
        rag_content="",
        task_config=s2,
        note_type="clinic_note",
        patient_facts=facts,
    )
    return final


def main():
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    explicit = sys.argv[3:]
    if explicit:
        files = [in_dir / f for f in explicit]
    else:
        files = sorted(p for p in in_dir.glob("*.txt"))

    s1, s2 = make_configs()
    print(f"Stage1={s1.model}  Stage2={s2.model}  files={len(files)}", flush=True)

    for i, fp in enumerate(files, 1):
        out_fp = out_dir / fp.name
        # Resume support (VAUCDA_BATCH_RESUME=1): skip patients already done so a
        # run interrupted by a shared-GPU OOM can be re-invoked to finish the rest.
        import os as _os
        if (_os.getenv("VAUCDA_BATCH_RESUME", "0") in ("1", "true", "on")
                and out_fp.exists() and out_fp.stat().st_size > 500):
            print(f"[{i}/{len(files)}] SKIP {fp.name} (already done)", flush=True)
            continue
        t0 = time.time()
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
            note = generate_one(text, s1, s2)
            out_fp.write_text(note, encoding="utf-8")
            print(f"[{i}/{len(files)}] OK {fp.name} -> {len(note)} chars in {time.time()-t0:.0f}s", flush=True)
        except Exception as e:
            err = f"[{i}/{len(files)}] FAIL {fp.name}: {e}\n{traceback.format_exc()}"
            print(err, flush=True)
            (out_dir / (fp.stem + ".ERROR.txt")).write_text(err, encoding="utf-8")


if __name__ == "__main__":
    main()
