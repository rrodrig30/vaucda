# VAUCDA — L1 Schema v2 Implementation Plan (urologist-review feedback)

**Status:** Plan for review (no code changes yet)
**Trigger:** urologist review of the 100-segment L1 gold draft.
**Standard:** rules.txt — real implementation only; COT + TOT analysis below.

---

## 1. Chain-of-Thought — problem identification & root cause

The reviewer found **no hallucinations** (extraction is faithful) but five
structural schema/pipeline defects, each confirmed against the 99 draft labels:

| # | Defect | Quantified | Root cause |
|---|---|---|---|
| D1 | Imaging studies listed as "procedures" | 125/268 procedures (47%) are CT/MRI/PET/bone-scan | schema has one `procedures` bucket; no `imaging` category, so diagnostics and interventions are conflated |
| D2 | Grading is prostate-only | 16 RCC + 1 bladder dx lose their grade (e.g. "ccRCC, GRADE 1" → dropped) | schema grade fields are `gleason`/`grade_group` only — no Fuhrman/ISUP (RCC) or WHO low/high (bladder) |
| D3 | One diagnosis per patient | ≥3 segments name two urologic cancers but get a single `diagnosis` | `diagnosis` is a single object, not a list |
| D4 | Diagnoses incomplete / missing | 16 null, 40 without grade | partly D2 (non-prostate grade unrepresentable); partly labeler not required to emit a dx per named cancer |
| D5 | Non-urologic tumor boards extracted | present in full corpus | no preprocessing filter; segment router keeps every SPN note |
| D6 | `procedures` also captures LABS and EXAM findings | reviewer: cultures, Urorisk 24-hr urine, **DRE** appear as procedures | `procedures` is an unconstrained bucket; labs are structured (deterministic) and exam findings are not L1 facts |
| D7 | Diagnoses limited to cancers | reviewer flagged missing ED, renal mass, urolithiasis, complex renal cyst | the diagnosis frame must capture ALL urologic diagnoses (cancer + benign), not only cancers |

These are **contract** defects (the schema can't represent the clinical
reality), not extraction-accuracy defects. They must be fixed BEFORE the gold
is frozen, or the gold encodes the wrong shape.

## 2. Solution design — L1 schema v2 (incorporates reviewer decisions)

### 2.1 `diagnoses[]` — every urologic diagnosis, cancer + benign (D3, D4, D7)
`diagnosis` (object) → `diagnoses` (array). Each entry is a self-contained
urologic diagnosis — **cancers AND benign conditions** (ED, BPH, urolithiasis,
renal mass/cyst, hydronephrosis, etc.). Each has an `id` (so treatments can
reference it), `category` (`cancer` | `benign`), `name`/`site`, `diagnosis_date`,
optional `stage_tnm`, optional `grade`, optional `risk`, and `source_span`.
Cancers populate grade/stage; benign diagnoses leave them null.

### 2.2 Cancer-context-aware grading (D2) — reviewer decisions applied
`grade.system` is selected by cancer type; only the relevant fields populate:

| Cancer | grade.system | fields |
|---|---|---|
| prostate | `gleason-isup` | `gleason` ("4+4"), `grade_group` (1–5) |
| renal cell (RCC) | **`fuhrman`** | `nuclear_grade` (1–4) |
| urothelial / bladder | `who` | `who_grade` ("low-grade"/"high-grade") **AND `bladder_stage`** (Ta/T1/CIS/T2+/MIBC) — capture BOTH |
| other | `other` | `value` (free text) |

```jsonc
"grade": {
  "system": "gleason-isup | fuhrman | who | other | null",
  "gleason": null, "grade_group": null,     // prostate
  "nuclear_grade": null,                    // RCC Fuhrman (1-4)
  "who_grade": null, "bladder_stage": null, // bladder: grade AND stage
  "value": null                             // catch-all
}
```

### 2.3 Treatments link to their diagnosis (decision #3)
Each `treatment_events[]` entry gains `for_diagnosis` = the `diagnoses[].id` it
targets (e.g. active-surveillance → the RCC, prostatectomy → the prostate
cancer). No more treatments listed "without regard for which cancer."

### 2.4 `procedures` = interventions only; new `imaging[]`; labs/exam excluded (D1, D6)
- New top-level `imaging[]` (modality, date, impression, span):
  CT/MRI/US/PET/PSMA-PET/bone-scan/x-ray/NM.
- `procedures[]` redefined as **interventions only**: biopsy, cystoscopy,
  TURBT, prostatectomy, ablation, stent, nephrectomy, ureteroscopy…
- **Labs** (cultures, Urorisk 24-hr urine, PSA, etc.) and **exam findings**
  (DRE) are NOT L1 facts — labs are structured/deterministic, exam is the PE
  agent's job. The labeler must NOT place them in `procedures`.

### 2.5 Non-urologic notes: FLAG and KEEP (decision #4, D5)
`segments.py` does NOT drop non-urologic segments. Instead it tags each segment
`primary_context` = `urologic` | `non_urologic` (e.g. a lung-cancer tumor
board). L1 still extracts the **cross-specialty facts that matter to urology**
from flagged segments — systemic chemotherapy, radiation details, recent
hospitalizations, palliative-care decisions — but does NOT mint a primary
urologic diagnosis from them. The flag lets downstream weight/route them
correctly. (Reviewer: these notes "often have information relevant like
chemotherapy, radiation therapy details, recent hospitalizations, or palliative
care decisions.")

## 3. Implementation plan (phased; files; real code only)

**Phase A — schema v2 (contract).** `scripts/l1/schema.json`: `diagnoses[]`,
`grade{}`, `imaging[]`, redefined `procedures`. Bump a `schema_version`.

**Phase B — labeler + router.**
- `label_segments.workflow.js`: mirror v2 schema; prompt adds the
  cancer-specific grading table, "emit ONE diagnosis per distinct urologic
  diagnosis (cancer AND benign — ED/BPH/stones/cysts/masses)", "link each
  treatment to its diagnosis via `for_diagnosis`", "imaging → `imaging`, never
  `procedures`; labs and DRE/exam are NOT facts here".
- `segments.py`: add a `primary_context` tagger (urologic | non_urologic) that
  FLAGS (never drops) each segment; log the flag for audit.

**Phase C — re-label (cheap, ~2M tokens).** Re-run the teacher over the same
100 segments under v2; `write_labels.py` updated for `diagnoses[]`/`imaging[]`.
The v1 drafts are discarded (never frozen), so no migration debt.

**Phase D — downstream consumers.**
- `review_report.py`: render **one diagnosis card per cancer**, grade shown
  per its system (Gleason/GG, Fuhrman, WHO), and a separate **Imaging** table
  distinct from Procedures. PSA/meds context panel unchanged.
- `score.py`: score `diagnoses` by matching on (cancer_type/site); grade
  accuracy per system; separate imaging vs procedure P/R/F1.
- `regex_baseline.py`: map current extractors to v2 (diagnoses list; prostate
  grade only — its known limitation becomes a measured gap).
- Downstream production mapping (`PatientStatusFacts`) is unaffected for now —
  L1 is still shadow/eval-only (scope-doc integration is a later milestone).

**Phase E — urologist re-review** of the v2 drafts (same HTML flow), then
**freeze**.

## 4. Testing & validation strategy (rules.txt)
- Schema: JSON-Schema-validate every label; CI check that no `procedures`
  entry matches the imaging vocabulary and vice-versa.
- Deterministic re-run of the §1 quantification script: imaging-as-procedure
  must drop to ~0%; RCC/bladder dx must carry a non-null grade; multi-cancer
  segments must yield ≥2 diagnoses.
- `score.py` per-field metrics on the re-labeled set vs the (re-reviewed) gold.
- Procedures/imaging separation: CI check that no `procedures` entry matches the
  imaging vocabulary, and no labs/DRE token appears in `procedures`.
- Non-urologic flag: assert non_urologic segments are tagged (not dropped) and
  mint no primary urologic diagnosis; cross-specialty treatment facts retained.

## 5. Risk assessment & mitigation
- **Mis-flagging context (D5):** flag-and-keep means a wrong `primary_context`
  never deletes data — worst case is a routing hint; logged for audit and
  easily corrected. (We deliberately do NOT drop, per reviewer.)
- **Grade-system misassignment:** system is keyed off cancer_type with an
  `other`/`value` fallback so nothing is lost even on unusual primaries.
- **Re-label cost / churn:** small (100 short segments); v1 never frozen so no
  migration.
- **Bladder under-representation (n=1):** WHO/stage fields built now but the
  gold has thin bladder coverage — flag for targeted sampling in M2 silver.

## 6. Tree-of-Thought evaluation
- **Reliability:** v2 represents the true clinical shape (multi-cancer,
  per-cancer grade), removing the contract defects that forced wrong labels.
- **Efficiency:** one cheap re-label; downstream changes are localized to the
  l1/ tooling; no production-path impact yet.
- **Completeness:** addresses all five reviewer findings end-to-end (schema →
  labeler → router → review → score), with deterministic acceptance checks.
- **Scalability:** the grade-by-system pattern and `imaging`/`procedures` split
  generalize to testicular/penile/adrenal without further schema churn.
- **Compliance (rules.txt):** real implementation only; no mocks; every
  segment drop and grade fallback is logged (no silent truncation); changes are
  measured against deterministic checks before/after.

## 7. Decisions — RESOLVED (urologist, 2026-06-27)
1. **RCC grade = Fuhrman** (`grade.system="fuhrman"`, `nuclear_grade` 1-4).
2. **Bladder = stage AND grade** (`who_grade` + `bladder_stage`).
3. **Multi-cancer: treatments attached to a specific cancer** -> `for_diagnosis`
   reference on each treatment event (see 2.3).
4. **Non-urologic notes: FLAG and KEEP** (not drop) - extract cross-specialty
   chemo/radiation/hospitalization/palliative facts; tag `primary_context` (2.5).

Additional reviewer findings folded in: D6 (labs/DRE wrongly in procedures ->
excluded), D7 (diagnoses must include benign urologic conditions).
