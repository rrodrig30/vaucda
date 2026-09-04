# VAUCDA note-level eval harness

An **architecture-agnostic** accuracy eval for generated clinic notes. It scores
a note's *output* against a per-patient gold spec, so it fairly A/Bs any
approach — today's hybrid, a holistic composer, a different model — on the
identical gold set. This is the instrument that turns "is it better?" into a
number instead of a hunch.

## What it measures
Five clinically-motivated metrics (see `gold/_SCHEMA.md`):
`primary_diagnosis`, `no_false_diagnosis`, `no_cross_cancer`, `psa_grounded`,
`completeness`. All deterministic → reproducible.

## Run it
From `backend/`:

```bash
# score a directory of already-generated notes (fast, no LLM/GPU)
python -m eval.run_eval --notes <notes_dir> --label current --json out.json

# generate notes with the current pipeline, then score (needs LLM; slow)
python -m eval.run_eval --generate --out-notes /tmp/notes --label current
```

Notes are matched to gold by `patient_id` appearing in the note filename.
Exit code is non-zero if any scored patient fails any metric (CI-friendly).

## A/B two architectures
```bash
python -m eval.run_eval --notes notes_A --label hybrid   --json A.json
python -m eval.run_eval --notes notes_B --label holistic --json B.json
# compare the two JSON scorecards
```

## Add a gold case
Drop a JSON in `gold/` per `gold/_SCHEMA.md`. Only patients with both a gold
spec and a generated note are scored; the summary reports coverage, so gold can
grow incrementally. Verify each gold against the source chart before adding it.

## Baseline (as seeded)
9 verified cases (7 Monday clinic + CASTANEDA penile + ASHFORD renal). On the
existing outputs the harness scores 44/45 metrics; the single real finding is
`09_CATTANACH_1548` — the note asserts "diagnosed with prostate cancer" when
the biopsy showed **ASAP** (atypical, not cancer) with a repeat biopsy planned.
That defect was surfaced automatically on the first run — the point of the tool.

`notes_current/` holds the scored snapshot; regenerate with `--generate` for a
clean single-architecture baseline when the GPU is free.
