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
3. **Urologist review** (the gating step): correct `tests/l1_gold/labels/*.json`.
   Focus on the rules the pipeline gets wrong — biopsy-confirmed diagnosis_date
   (not earliest PSA), MAX grade_group, specific `agent` preserved
   (Lu-177/abiraterone not collapsed), start+end dates. Then **freeze**.
4. **Baseline**: `python scripts/l1/regex_baseline.py tests/l1_gold tests/l1_gold_regex`
5. **Score** any candidate: `python scripts/l1/score.py tests/l1_gold tests/l1_gold_regex`

## One-command eval

`./scripts/l1/eval.sh <generated_note_dir> [candidate_label_dir]` runs the
deterministic per-class checks on generated notes and (if a candidate label dir
is given and gold is frozen) the per-field score. This is L1's yardstick —
deterministic, so it is immune to the LLM-judge variance that now exceeds
per-fix signal.

## Status
- Built & validated: segmentation, sampling (100 segments / 65 patients),
  schema, teacher labeler, span resolution, regex baseline, scorer, checks.
- Pending (needs the urologist): review/freeze `tests/l1_gold/labels/`.
  Until then `score.py` runs against the teacher draft as a pipeline smoke test.
