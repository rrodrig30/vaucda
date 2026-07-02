# L1 Narrative Extractor — Milestone 0 (gold eval + harness)

Implements scope-doc milestone 0: a frozen gold-eval segment set, a teacher
draft-labeling pipeline for urologist review, deterministic per-class checks,
and a one-command eval. See `../../../docs/VAUCDA_L1_Extractor_Scope.md`.

## Pieces

| file | role |
|---|---|
| `router.py` | **(M1)** route a whole extract: narrative sections -> L1 segments (each flagged urologic/non_urologic), structured sections -> deterministic path (unchanged); SP pathology surfaced as L1 grade ref. `--validate` proves corpus coverage |
| `segments.py` | split a VistA extract into narrative note segments (L1's input unit; structured sections stay deterministic) |
| `schema.json` | the L1 output contract (span-grounded structured facts) |
| `sample_segments.py` | deterministic, stratified sampler → frozen gold segment set |
| `label_segments.workflow.js` | teacher draft-labeler (1 agent / segment → schema), for urologist review |
| `write_labels.py` | persist teacher drafts; resolve `source_quote` → `source_span` |
| `regex_baseline.py` | run today's extractors per segment in the L1 schema = the bar L1 must beat |
| `score.py` | per-field scorer (candidate vs gold): treatment-event P/R/F1, date/grade-group accuracy |
| `../deterministic_checks.py` | no-LLM per-class checks on generated notes (med-not-in-RXOP, PSA/treatment hallucination, grade-group undergrade) |

## Layout

```
tests/l1_gold/
  manifest.json            frozen sample (100 segments, deterministic)
  segments/<id>.txt        segment text (labeler/L1 input)
  segments/<id>.meta.json  metadata
  labels/<id>.json         GOLD labels (teacher draft -> urologist-corrected)
tests/l1_gold_regex/labels/<id>.json   regex-baseline candidate
tests/l1_<model>/labels/<id>.json      an L1 candidate
```

## Workflow

1. **Sample** (done): `python scripts/l1/sample_segments.py tests/l1_gold 100`
2. **Teacher draft-label** (done): run `label_segments.workflow.js` over the
   manifest ids, then `python scripts/l1/write_labels.py tests/l1_gold <result.json>`
3. **Urologist review** (the gating step) — NO JSON editing:
   - `python scripts/l1/review_report.py tests/l1_gold` → open
     `tests/l1_gold/review.html` in a browser.
   - Each note shows next to its extracted facts; highlighted text is the AI's
     evidence. Mark ✓ looks right / ✗ needs fix, and type the correction in
     plain English. Focus on the rules the pipeline gets wrong — biopsy-confirmed
     diagnosis_date (not earliest PSA), MAX grade_group, specific `agent`
     preserved (Lu-177/abiraterone not collapsed), start+end dates.
   - Click **Download review** → `review_verdicts.json`.
   - `python scripts/l1/apply_review.py tests/l1_gold review_verdicts.json`
     stamps approvals and lists the fixes to apply, then **freeze**.
4. **Baseline**: `python scripts/l1/regex_baseline.py tests/l1_gold tests/l1_gold_regex`
5. **Score** any candidate: `python scripts/l1/score.py tests/l1_gold tests/l1_gold_regex`

## One-command eval

`./scripts/l1/eval.sh <generated_note_dir> [candidate_label_dir]` runs the
deterministic per-class checks on generated notes and (if a candidate label dir
is given and gold is frozen) the per-field score. This is L1's yardstick —
deterministic, so it is immune to the LLM-judge variance that now exceeds
per-fix signal.

## Status — Milestone 0 COMPLETE
- **Gold FROZEN: v1.0** (schema_version 2), urologist-reviewed & approved
  2026-06-27. 99 segments; diagnoses 81 cancer / 147 benign / 15 indeterminate;
  141 imaging, 158 procedures, 169 treatments. Manifest + sha256:
  `scripts/l1/GOLD_FREEZE.json`; read-only snapshot:
  `tests/l1_gold/frozen/1.0/`.
- Built & validated: segmentation, stratified sampling, v2 schema
  (cancer-aware grading, multi-dx incl. indeterminate masses, imaging split,
  treatment→diagnosis links, pathology-augmented labeling), teacher labeler,
  span resolution, regex baseline, per-field scorer, deterministic checks,
  freeze tool.
- **Milestone 1 COMPLETE:** `router.py` routes every section (0 orphans across
  all 100 patients); narrative → L1 (2,504 segments, deterministic urologic
  flag 98% agreement with gold), structured path unchanged; SP pathology fed to
  L1. M4 wires this into `build_authoritative_patient_facts` behind a flag.
- **Milestone 2 COMPLETE:** silver training corpus (`SILVER_CORPUS.json`).
  Teacher = **glm-5.2:cloud** (local Ollama, off the Claude API). 819 segments
  (gold held out); 844 cancer / 1150 benign / 95 indeterminate diagnoses;
  1223 treatments, 759 imaging, 1584 procedures; 88% span-resolution; agreement
  tiers 757 high / 26 med / 36 low. → **`tests/l1_train/l1_sft.jsonl`** (819
  LoRA SFT chat pairs: instruction + segment + pathology → v2 JSON).
- **Next (Milestone 3):** LoRA fine-tune medgemma-27b on `l1_sft.jsonl`
  (weight by confidence tier), scored against the frozen gold with `score.py`;
  then M4 shadow-integration behind `VAUCDA_L1=1`.

- **Milestone 3 COMPLETE:** LoRA fine-tune of medgemma-27b on `l1_sft.jsonl`
  (`train/`). Adapters at `tests/l1_model/medgemma27b-l1-lora` (8192 seq, the
  promoted one) and `…-10k` (10240 seq). Gold scorecard (vs regex baseline):
  diagnoses R 0.15→0.67, treatment-event R 0.07→0.56, diagnosis-date 9%→90%.
  Grade-by-system (regex 0.91) and the procedure/imaging split are NOT promoted
  (regex ≥ L1 there). 8192 ≈ 10240 — long-context did not justify itself.

- **Milestone 4 COMPLETE — wired behind `VAUCDA_L1=1`:**
  `app/services/note_processing/l1/` (`runtime.py` = lazy 4-bit model singleton
  + per-segment inference using the byte-identical training prompt/parser;
  `enrich.py` = grounded, additive, monotonic merge into `PatientStatusFacts`).
  Hook: `build_authoritative_patient_facts` (the single shared-facts source for
  Stage 1 + Stage 2). Default OFF → pipeline is byte-for-byte the deterministic
  path. Merge promotes only diagnoses / treatment_events / diagnosis_date
  (where L1 beat regex on gold); every L1 record must ground to a verbatim
  source quote (hallucination net); status only upgrades away from UNCERTAIN;
  grade/procedures/imaging stay deterministic.

  **Enabling it:**
  ```bash
  # 1. the backend runtime needs the ML deps (the app venv normally lacks them):
  pip install torch --index-url https://download.pytorch.org/whl/cu124
  pip install transformers peft bitsandbytes accelerate python-dotenv
  # 2. flags (HF_TOKEN must be in .env for the gated base model):
  export VAUCDA_L1=1                 # turn the extractor on
  export VAUCDA_L1_ADAPTER=.../tests/l1_model/medgemma27b-l1-lora   # optional (default)
  export VAUCDA_L1_STRICT=1          # optional: raise instead of degrade-to-deterministic
  ```
  Input must be VistA format (the router segments VistA `SPN` narrative, matching
  the corpus); CPRS-native input is a safe no-op. If the ML deps or model are
  missing while the flag is on, enrichment logs and degrades to the deterministic
  facts (unless `VAUCDA_L1_STRICT=1`), so it can never take down note generation.
  Validated end-to-end on a real mCRPC patient: recovered the full narrative
  treatment trajectory (RP→IMRT→leuprolide→…→Lu-177→gamma-knife) the regex layer
  missed, flipping cancer_status→TREATED and treatment_naive→False.

  **Recommended next step before production:** run the 100-patient note-quality
  eval with `VAUCDA_L1=1` to measure the downstream note impact (the gold eval
  measures extraction, not rendered-note quality).
