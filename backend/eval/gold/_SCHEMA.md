# Gold spec schema (note-level eval)

One JSON file per patient in `eval/gold/` (filenames starting with `_` are
ignored). Each spec is the ground truth a generated note is scored against.
Add cases freely — the harness scores whatever has both a gold spec and a
generated note, and reports coverage.

```jsonc
{
  "patient_id": "07_FOSTER_2388",          // must be a substring of the note filename
  "source_file": "tests/.../07_FOSTER_2388.txt", // chart path, relative to repo root
  "required_sections": ["HPI", "ASSESSMENT", "PLAN"],  // headers that must be present + non-empty

  "primary_diagnosis": {                    // the note's lead must be centered here
    "organ": "prostate",                    // renal|bladder|prostate|penile|testicular|upper_tract|adrenal|urethral
    "malignancy": "cancer"                  // cancer | indeterminate | benign
  },

  "cancer_organs": ["prostate"],            // organs the patient genuinely has cancer in;
                                            // a cancer asserted for ANY other organ = cross-cancer leak
                                            // (the primary organ is always allowed automatically)

  "forbidden_diagnoses": ["metastatic prostate cancer"], // phrases that must NOT be positively asserted
  "forbidden_psa": [4.6, 5.1],              // known-wrong PSA values that must NOT appear (optional)

  "notes": "free-text rationale for the reviewer"
}
```

## Malignancy levels
- **cancer** — pathology-confirmed malignancy. The lead must name the organ AND use a cancer term.
- **indeterminate** — a mass/lesion not yet proven (unbiopsied renal mass, elevated PSA, **ASAP**, PI-RADS without positive biopsy). The lead must flag uncertainty and must NOT assert cancer.
- **benign** — the lead must NOT frame it as cancer.

## Metrics scored (see `scorers.py`)
| metric | passes when |
|---|---|
| `primary_diagnosis` | lead centered on the gold organ with the gold malignancy framing |
| `no_false_diagnosis` | no `forbidden_diagnoses` positively asserted (negated/family/hedged OK) |
| `no_cross_cancer` | no cancer asserted for an organ outside `cancer_organs` + primary |
| `psa_grounded` | every PSA value cited exists in the source PSA set (thresholds/ranges ignored); no `forbidden_psa` |
| `completeness` | all `required_sections` present and non-trivial |

Checks are deterministic (string/regex vs. note + source), so runs are reproducible.
