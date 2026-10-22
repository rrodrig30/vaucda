# VAUCDA — L1 Narrative Clinical Extractor: Scope & Design

**Status:** Scoping draft for review
**Depends on:** `VAUCDA_ML_Error_Prevention_Plan.md` (L1 = the ML facts extractor)
**Grounded in:** the Tumor-56/100 assessment data and the current
`patient_status_facts` / `clinical_timeline` code.

---

## 1. Why L1 (the precise problem)

Phase 1 (shared authoritative facts) proved that **facts accuracy is the
rate-limiter**: once Stage 1 and Stage 2 consume one facts object, every error
in that object propagates faithfully to the note. Deterministic fixing of the
facts layer (~96 regex patterns across `clinical_timeline.py` (49) and
`patient_status_facts.py` (47)) has reached the point where the per-fix signal
is below the LLM-judge's noise floor (~±20). The residual errors are
concentrated in **narrative extraction** — the part regex does worst — and they
recur across the corpus:

| Residual error class (from assessments) | Example | Current cause |
|---|---|---|
| Date mis-pairing | biopsy "results-notification" date (3/11) shown as the procedure date (3/10); treatment date borrowed from a neighbor; **start date rendered as completion** | window-based date association |
| Missed staging | `cT3bN0M0`, `N1`, PSMA-positive nodes dropped | no staging extractor |
| Wrong risk / grade group | took a middle/lowest biopsy core (GG2) instead of the **max** (GG4); blind to prostatectomy path | derived-GG heuristic |
| Multi-event timeline collapse | two radiation courses merged; 2nd ablation dropped; Lu-177 labeled "radiation"; biopsy labeled "chemo" | modality/date heuristics |
| Diagnosis-date anchoring | earliest elevated-PSA date used as "diagnosis date" | nearest-date heuristic |

These are exactly what a span-grounded clinical extraction model does well, and
what regex cannot. **L1 replaces the narrative-extraction layer; it does NOT
touch structured sources.**

## 2. Scope boundary (what L1 is and is NOT)

**L1 DOES** extract structured facts from **narrative free-text** segments
(oncology-consult HPIs, urology note bodies, treatment narratives):
treatment events, diagnosis, staging, grade/risk, procedures + findings — each
with a **source span** (provenance).

**L1 does NOT**:
- Touch structured sources — RXOP medications, lab tables, demographics,
  problem-list codes stay **deterministic** (the RXOP fix showed structured
  parsing wins; ML there only adds risk).
- Make clinical decisions — Eligard-intermittency, screening-cessation, what to
  continue stay **rule-based** (`age_guardrail`, treatment_active_status, the
  RXOP/Eligard rules). L1 supplies facts; rules + L3 decide and verify.
- Synthesize prose — that is the existing Stage-1/Stage-2 LLMs.

## 3. The input-size constraint (drives the architecture)

Inputs are large VistA clinic-prep extracts: **median 156 KB, max 455 KB
(~110K tokens), mean 177 KB.** A 27B local model cannot reliably ingest a whole
extract. Therefore L1 is **section-routed**, not whole-document:

```
raw extract
  → normalizer splits sections (already exists: source_normalizers)
  → STRUCTURED sections (RXOP, CH/SLT labs, PLL problem list, DEM) → deterministic extractors (unchanged)
  → NARRATIVE sections (SPN/oncology consults, GU note HPIs/A&P) → L1 per segment
  → merge + dedup → PatientStatusFacts (+ provenance spans)
```

Each narrative segment (a single consult/HPI, typically 1–8 KB) fits in context
comfortably. Merge/dedup across segments is deterministic (same machinery that
already dedups timeline events). This also bounds cost: L1 runs on a few small
segments, not 177 KB.

## 4. I/O contract

**Input (per segment):** `{section_title, date_of_note, text}` — one narrative
note body.

**Output (per segment):** JSON, validated by schema, every record carrying a
`source_span` (char offsets into the segment) for provenance/verification:

```jsonc
{
  "diagnosis": {                       // null if none in this segment
    "cancer_type": "prostate adenocarcinoma",
    "diagnosis_date": "2008-09",       // ISO; biopsy-confirmed date, NOT earliest PSA
    "gleason": "4+4", "grade_group": 4,// MAX across cores
    "stage_tnm": "cT3bN0M0",           // explicit TNM if present
    "risk": "very-high",               // only if source-stated or derivable
    "source_span": [120, 240]
  },
  "treatment_events": [{
    "modality": "prostatectomy|radiation|ADT|ARSI|chemotherapy|brachytherapy|focal|radioligand|immunotherapy|...",
    "agent": "leuprolide",             // specific drug when named (preserves Lu-177, abiraterone, etc.)
    "start_date": "2012-08", "end_date": "2014-07",  // BOTH when a range is documented
    "status": "started|completed|ongoing|discontinued|declined",
    "intent": "definitive|adjuvant|salvage|palliative",
    "source_span": [300, 360]
  }],
  "procedures": [{ "type": "biopsy|cystoscopy|...", "date": "2022-11-16",
                   "finding": "GG1 in 2/12 cores", "source_span": [..] }],
  "metastases": [{ "site": "liver|bone|node|brain", "date": "2024-01", "source_span": [..] }]
}
```

Key schema choices that directly kill the residual error classes:
- **`start_date` AND `end_date`** → no more start-as-completion.
- **`agent` separate from `modality`** → Lu-177/abiraterone preserved, not bucketed to "radiation".
- **`grade_group` = MAX**, **`stage_tnm` explicit** → fixes risk/staging misses.
- **`source_span` on every record** → enables the L3 verification gate and a
  deterministic "is this date actually next to this event?" check.

This is a strict superset of today's `TimelineEvent`/`PatientStatusFacts`, so
the merge layer maps cleanly onto the existing contract (no Stage-1/Stage-2
changes needed).

## 5. Model & training approach

- **Model:** LoRA fine-tune of **`medgemma:27b`** (already local; medical
  pretraining; H100 fits LoRA). Constrained/JSON decoding (extend the existing
  HPI-v2 JSON-schema pattern). Runs locally → HIPAA-safe.
- **Bootstrap teacher:** `gpt-oss:120b-cloud` (already in use) generates silver
  structured labels over a large unlabeled narrative-segment corpus.
- **Weak supervision / agreement gating:** today's deterministic extractors are
  high-precision on the easy cases — where teacher and regex **agree**, accept
  as silver-gold; where they **disagree**, that's a hard case → route to review
  (these disagreements are also exactly the assessment-flagged cases).
- **Gold:** urologist spot-review of a stratified sample (~100 segments) for a
  held-out eval set; never train on it.

## 6. Training-data flywheel (already half-built)

The multi-agent assessment harness (`assess_notes.workflow.js`) already emits
structured, evidence-cited findings ("biopsy results-date used as procedure
date", "GG2 core used instead of GG4"). Pipeline:

1. Teacher extracts silver labels on narrative segments.
2. Agreement-gate vs deterministic extractors → high-confidence silver.
3. Assessment findings → targeted corrections on the disagreement set.
4. Fine-tune L1; re-run harness + deterministic checks; iterate.

The harness is both the **label source** and the **eval** — same loop that
produced the measured arc in this repo.

## 7. Integration & rollback

- New module `note_processing/extractors/l1_narrative_extractor.py` behind a
  flag (`VAUCDA_L1=1`, mirroring `VAUCDA_HPI_V2`).
- `build_authoritative_patient_facts()` (Phase 1's single entry point) gains an
  L1 path: when enabled, narrative facts come from L1; structured facts stay
  deterministic; results merge into the same `PatientStatusFacts`.
- **Shadow mode first:** run L1 alongside regex, diff on the gold eval, promote
  **per-field** only when L1 ≥ regex. Deterministic path remains the fallback;
  low-confidence/empty L1 output falls back to regex.

## 8. Evaluation (fix the noise problem first)

Because the LLM-judge noise (~±20) now exceeds per-fix signal, L1 is evaluated
on **deterministic, span-checkable metrics**, not just the judge:

- **Per-field extraction P/R/F1 vs the gold segments** (diagnosis_date,
  grade_group, each treatment event's date/modality/status, TNM).
- **Deterministic per-class checks** (buildable now, independent of L1):
  - date-provenance: is each event's date within its `source_span`? (kills
    date-mis-pairing)
  - grade-group = max core?
  - med-continuation: does the Plan continue a drug absent from RXOP?
- **Harness, averaged over 3 runs** for the aggregate trend (variance ↓ ~1.7×).

Success target: narrative-driven classes (date wrong_entry, staging/risk
omission, timeline hallucination) down ≥50% on the deterministic metrics;
aggregate critical findings < 60 (from 111–120) once L1 + L3 land.

## 9. Milestones (rough engineering-days, 1 ML eng + H100)

| # | Milestone | Days | Exit criteria |
|---|---|---|---|
| 0 | Freeze gold eval (100 segments, urologist-reviewed) + deterministic per-class checks | 4–6 | one-command eval with stored baselines |
| 1 | Section-router: narrative vs structured segmentation over the normalizer | 3–5 | every segment routed; structured path unchanged |
| 2 | Teacher silver-label corpus + agreement gating | 5–7 | labeled segment set with confidence tiers |
| 3 | LoRA fine-tune medgemma-27b → schema w/ spans; constrained decode | 7–10 | beats regex per-field on gold |
| 4 | Shadow integration into `build_authoritative_patient_facts`, per-field promotion | 4–6 | L1 facts flow to both stages behind flag |
| 5 | Re-measure (deterministic checks + 3-run harness); tune | 3–4 | targeted classes ↓ ≥50% |

≈ 26–38 engineering-days to a measured, shadow-validated L1.

## 10. Risks & mitigations

- **Hallucinated extractions** → every record needs a `source_span`; reject
  records whose claimed value isn't in the span (deterministic gate). L3 NLI is
  the second net.
- **Whole-document context blowup** → section-routing (§3); never feed >1 segment.
- **Domain edge cases (Eligard intermittency, ASAP, Phoenix)** → keep as
  deterministic post-rules over L1's facts, not learned.
- **Label noise from the teacher** → agreement-gating + urologist gold; train
  only on high-confidence silver + corrected hard cases.
- **Latency** (27B local per segment × few segments) → measure in milestone 4;
  cache per-segment; segments are small.
- **Regression risk** → flag + shadow + per-field promotion + regex fallback.

## 11. Open decisions (need your input)

1. **PHID/labeling policy:** may de-identified narrative segments go to the
   `gpt-oss` teacher (it's local Ollama-cloud) for silver labels, or must
   labeling be fully on-box?
2. **Gold set size/ownership:** who does the ~100-segment urologist review, and
   on what timeline?
3. **Model pick:** commit to medgemma-27b LoRA, or evaluate a smaller encoder
   (GatorTron/ClinicalBERT) for the pure span-NER fields to cut latency?
4. **Scope of v1 L1:** prostate-only first (the bulk of the corpus), or include
   RCC/bladder narrative from the start?
5. **Eval cadence:** stand up the deterministic per-class checks **before** L1
   (recommended — they're useful immediately and are L1's real yardstick)?
