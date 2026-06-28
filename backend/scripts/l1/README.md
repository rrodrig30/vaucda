# L1 Narrative Extractor — Milestone 0 (gold eval + harness)

Implements scope-doc milestone 0: a frozen gold-eval segment set, a teacher
draft-labeling pipeline for urologist review, deterministic per-class checks,
and a one-command eval. See `../../../docs/VAUCDA_L1_Extractor_Scope.md`.

## Pieces

| file | role |
|---|---|
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
- **Next (Milestones 1–3):** section router into the production pipeline →
  teacher silver-label corpus (the 925 treatment-narrative segments) → LoRA
  fine-tune medgemma-27b, scored against this frozen gold with `score.py`.
