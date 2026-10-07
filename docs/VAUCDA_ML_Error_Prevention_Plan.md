# VAUCDA — ML for Error Prevention: Assessment & Implementation Plan

**Status:** Draft for review
**Author:** Claude Code session (note-quality debugging, Tumor clinic test set)
**Scope:** Reducing clinical-accuracy errors in the generated urology note
(HPI / CC / Assessment / Plan), grounded in measured error data from this
session.

---

## 0. Update log — empirical findings since v1 (Phase 1 + facts-accuracy fixes)

Three architectural/facts fixes were implemented and measured on Tumor-56
after the original plan, and they sharpen the thesis:

- **Phase 1 (shared authoritative facts object across Stage 1 & 2)** —
  IMPLEMENTED. Hallucinations 87→73 and Assessment findings 104→90, but
  context-blind recs rose 52→71 because both stages then propagate the facts
  object's *errors* faithfully. This is the empirical proof of the plan's core
  thesis: **shared facts is correct architecture and makes facts-accuracy the
  rate-limiter.**
- **treatment_active_status fix** (finite ADT course → completed) — recovered
  10 of the 19 context-blind regression and pushed the aggregate to a new best
  (total 395, critical 111).
- **RXOP authoritative-medication fix** (read only the VistA OUTPT-RX-ACTIVE
  list, not stale embedded med-rec blocks; Eligard/ADT exception) — the
  *targeted* class fell decisively (MEDICATIONS findings 8→3; "continue the
  wrong drug" context-blind 17→5 across the arc, −71%), and is clinically
  correct per the urologist. See [[project-vista-medication-authority]].

**Measurement finding (important):** the LLM-judge eval has run-to-run variance
of ≈±20 on total / ±15-23 on HPI & context-blind (an *unchanged* HPI dimension
ranged 140–163 across builds). That noise now EXCEEDS the per-fix signal, so
single deterministic fixes can only be validated on their *targeted sub-class*,
not the aggregate. Two consequences: (a) upgrade eval to **multi-run averaging
or deterministic per-class checks** before more single fixes; (b) this is the
strongest signal yet that the next real lever is **L1 (narrative extractor) —
fix many classes at once**, because one-at-a-time deterministic fixing has
reached diminishing returns relative to what we can measure.

**Refined deterministic-vs-ML boundary (validated this session):** structured
sources (RXOP meds, lab tables) → deterministic wins (RXOP fix); narrative
(treatment course, dates-in-prose, staging, risk) → L1 ML extractor; clinical
decision logic (Eligard intermittency, screening cessation) → deterministic
rules + domain knowledge, NOT a black box; verification → L3 NLI gate.

---

## 1. Executive summary

Three rounds of root-cause fixes on the 56-patient Tumor-clinic test set cut
critical findings ~18% and unusable notes ~37% (see §2). The fixes were all
**deterministic** (extractors, prompt grounding, guardrails). The residual
errors are now concentrated in two layers that deterministic code handles
poorly:

1. **Clinical information extraction** — parsing dates, treatments, status,
   risk/stage out of heterogeneous narrative (VistA numbered lists, free-text
   "s/p IMRT 2023", multi-encounter prose). This is the single largest error
   source and is fundamentally an NLP task, not a regex task.
2. **Grounding / verification** — catching when the LLM-synthesized note states
   something the source does not support (hallucination) or two sections
   disagree (Stage-1/Stage-2 contradiction).

**Recommendation:** a hybrid pipeline that (a) replaces the brittle regex
extraction layer with a **fine-tuned local clinical-extraction model**, (b)
keeps the existing **deterministic safety guardrails**, and (c) adds an
**ML verification gate** (natural-language inference / entailment) before a note
is finalized. The 56-patient assessment harness built this session doubles as
the **evaluation + labeling pipeline** for these models.

ML is explicitly **not** recommended for: cross-section reconciliation (an
architecture fix), safety-critical decisions (keep rule-gated), or "use a bigger
generator" (more ungrounded generation increased hallucinations in round 1).

---

## 2. Evidence base (measured this session)

All numbers are from the LLM-judge assessment harness
(`backend/scripts/assess_notes.workflow.js`), 56 patients, scored against source
records. Production config: `gpt-oss:120b-cloud`, `source_format=vista`,
`VAUCDA_HPI_V2=1`.

### Trajectory — Tumor-56 (findings)

| Metric | Baseline | Round 1 | Round 2 | Round 3 |
|---|---|---|---|---|
| Total findings | 441 | 438 | 412 | 416 |
| Critical findings | 137 | 127 | 113 | 118 |
| Unusable notes | 19 | 21 | 12 | 12 |

Rounds 1–2 produced durable gains (critical −24, unusable −37%); **round 3
plateaued** (within LLM-judge run-to-run noise) — direct evidence that
deterministic regex/prompt fixes are hitting diminishing returns on the
extraction/grounding error classes.

### Generalization — all 100 patients (fixed pipeline)

| Batch | N | Findings/pt | Critical/pt | Unusable |
|---|---|---|---|---|
| Tumor-56 (oncology) | 56 | 7.4 | 2.11 | 21% |
| loose-34 (Tumor re-exports) | 34 | 7.5 | 2.06 | 29% |
| Monday-10 (general GU, unseen) | 10 | 7.5 | 1.90 | 30% |
| **All 100** | 100 | **7.5** | **2.07** | **25%** |
| _Tumor-56 baseline (pre-fix)_ | 56 | _7.9_ | _2.45_ | _34%_ |

Error rate is uniform across clinic types (fixes generalize; non-oncology not
broken). But **0/100 notes rated "acceptable"** and category mix is dominated by
omission+hallucination+wrong_entry (493/745 = 66%) — the ML-addressable layers.

### Residual error taxonomy (round-2 snapshot) and ML applicability

| Category | Count | Primary layer | Best lever |
|---|---|---|---|
| omission | 102 | extraction | **ML extraction** |
| wrong_entry | 88 | extraction (dates/grade/status) | **ML extraction** |
| hallucination | 81 | grounding/synthesis | **ML verification gate** |
| context_blind_recommendation | 53 | facts staleness + guardrails | rules + extraction |
| stale_data | 39 | extraction (recency) | **ML extraction** |
| internal_contradiction | 32 | architecture (no reconciliation) | **architecture, not ML** |
| formatting | 15 | deterministic renderer | rules |

By section: HPI 154, Assessment 101, Plan 71, CC 15.

**Reading:** ~70% of residual findings (omission + wrong_entry + stale_data +
much of hallucination) trace to the extraction layer or to ungrounded
synthesis — exactly the two places ML is strong.

---

## 3. Where ML helps vs. where it does not

### ML is the right tool
- **Clinical NER + relation + temporal extraction.** Replace the regex cascade
  in `clinical_timeline.py` / `patient_status_facts.py` with a model that emits
  structured `(modality, date, status, evidence_span)` tuples and
  `(diagnosis, date, grade_group, stage, risk)` records.
- **Verification / hallucination detection.** A fine-tuned NLI model scoring
  each generated sentence as `supported | contradicted | unsupported` against
  retrieved source spans, gating the note.
- **Span-grounded structured output.** Every extracted fact carries a source
  character span (provenance), enabling deterministic post-checks.

### ML is the wrong tool (do NOT use)
- **Stage-1 ↔ Stage-2 reconciliation** (32 contradictions): architecture fix —
  a single authoritative `PatientFacts` object both stages consume. No model.
- **Safety decisions** (stop PSA, continue/stop a drug): keep
  deterministic/rule-gated (`age_guardrail`, treatment-status reconciliation).
  A black-box must never silently discontinue cancer monitoring.
- **Bigger generator as a fix:** round 1 showed more ungrounded generation
  raised hallucinations 75→102. Grounding, not generation, is the lever.

---

## 4. Optimal target architecture

Current pipeline (simplified):

```
raw note → VistA→CPRS normalize → regex extractors → patient_status_facts
         → Stage-1 section agents (LLM) → Stage-2 A&P (LLM) → heuristic verify
```

Target hybrid pipeline:

```
raw note → normalize
        → [L1] ML Clinical Extractor  → structured PatientFacts (+source spans)
        → [L2] Deterministic guardrails & reconciliation (single facts object)
        → Stage-1 / Stage-2 LLM synthesis (constrained, fact-grounded)
        → [L3] ML Verification Gate (NLI: each claim vs source spans)
              → pass → note ;  fail → targeted regenerate / flag for review
```

- **L1 — Clinical Extractor (new, ML).** Highest ROI. Fine-tuned local model
  producing the structured facts the regex layer produces today, but robust to
  format. Outputs JSON with provenance spans.
- **L2 — Guardrails & reconciliation (deterministic, keep/extend).** Treatment
  active/discontinued, age/life-expectancy, single authoritative facts object
  shared by both stages (kills the 32 contradictions). Deterministic and
  auditable for safety/HIPAA.
- **L3 — Verification Gate (new, ML).** NLI/entailment check per generated
  claim against extractor source spans; block or flag unsupported claims.

---

## 5. Model selection (fits existing stack: local, HIPAA, H100)

| Role | Recommended | Rationale | Alternatives |
|---|---|---|---|
| L1 Clinical Extractor | Fine-tune **medgemma:27b** (already local) via LoRA to emit the facts schema | Medical-domain pretraining; local = HIPAA-safe; H100 fits LoRA | `gpt-oss:120b-cloud` few-shot as a bootstrap teacher; GatorTron/ClinicalBERT for pure NER if latency-critical |
| L1 (bootstrap) | `gpt-oss:120b-cloud` for synthetic-label generation | Already in use; teacher for distillation | Claude API (if cloud PHI policy allows) |
| L3 Verification (NLI) | Fine-tuned **DeBERTa-v3-large MNLI** or a small medgemma classifier head | Cheap, fast, runs per-sentence | LLM-as-judge (current harness) for offline eval only — too slow/expensive in-line |
| Embeddings (span retrieval for L3) | existing `sentence-transformers` + Neo4j vector | already in stack | — |

Notes: keep everything **local** for PHI. The cloud models are acceptable as
*offline teachers* for label generation but should not be required at inference.

---

## 6. The data flywheel (this is the unlock)

The assessment harness already produces **structured, evidence-cited findings**.
That is a labeling engine:

1. Run `assess_notes.workflow.js` over current + future clinic batches → graded
   findings (category, section, evidence_source, evidence_note, severity).
2. Convert findings + the deterministic extractor outputs into supervised
   training pairs:
   - **Extraction labels:** corrected `(modality, date, status, span)` tuples
     (findings flag the wrong ones; source spans give the right ones).
   - **Verification labels:** `(claim, source_span) → supported/contradicted`
     directly from hallucination / contradiction findings.
3. Fine-tune L1 and L3; re-run the harness; measure; iterate.

The same harness is the **eval set** — so every model change is measured the
way these three rounds were.

---

## 7. Phased implementation plan

Effort estimates are rough engineering-days for one ML engineer; they assume the
existing repo, the H100, and the local medgemma models.

### Phase 0 — Foundation & eval harness hardening (3–5 d)
- Freeze the 56-patient set as a versioned **gold eval**; add 1–2 more clinic
  batches for diversity (bladder/kidney/stone-heavy).
- Define the **canonical `PatientFacts` JSON schema** (the contract for L1/L2).
- Promote `assess_notes.workflow.js` into a repeatable eval CLI with stored
  baselines (it already emits the right structure).
- **Exit criteria:** one command produces the category/section comparison table.

### Phase 1 — Architecture fix: single authoritative facts object (3–5 d, no ML)
- Make Stage-1 and Stage-2 consume ONE `PatientFacts` instance; remove
  independent re-derivation in `assessment_agent` / `plan_agent`.
- **Targets:** internal_contradiction 32 → <10; some wrong_entry.
- Do this first — it de-risks ML by giving both stages a single input to ground
  against, and it needs no model.

### Phase 2 — L1 Clinical Extractor (10–15 d)
- **2a.** Generate synthetic labels with `gpt-oss:120b-cloud` as teacher over a
  large unlabeled clinic corpus; correct against assessment findings.
- **2b.** LoRA fine-tune `medgemma:27b` to emit the `PatientFacts` schema with
  source spans. Constrained/JSON decoding (extend the existing v2 JSON pattern).
- **2c.** Shadow-mode: run ML extractor alongside regex; diff on the gold eval;
  promote per-field once it beats regex.
- **Targets:** omission 102, wrong_entry 88, stale_data 39 → large reductions
  (these are the extraction-bound classes).
- **Risk control:** keep regex as fallback; per-field A/B; never ship a field
  that regresses on gold.

### Phase 3 — L3 Verification Gate (7–10 d)
- Build the claim-segmenter (sentence/clause) + span retriever (existing
  embeddings).
- Fine-tune NLI on verification labels from the harness; calibrate a threshold
  that maximizes caught-hallucinations at a fixed false-block rate.
- Wire as a gate: unsupported claim → targeted regenerate (bounded retries) →
  else flag for provider review (never silently drop clinical content).
- **Targets:** hallucination 81 → large reduction; catches residual wrong_entry.

### Phase 4 — Continuous loop & monitoring (ongoing)
- Scheduled harness runs on new batches; drift dashboard by category/section;
  periodic re-fine-tune from accumulated labels.

**Suggested order rationale:** Phase 1 (cheap, architectural) → Phase 2 (biggest
error mass) → Phase 3 (catches what extraction+grounding still miss).

---

## 8. Success metrics (use the harness)
- Critical findings per 56-note eval: 113 → target <60.
- Unusable notes: 12 → target ≤3.
- Hallucination + wrong_entry: 169 → target <80.
- Internal contradictions: 32 → <10 (Phase 1 alone).
- Per-field extraction precision/recall vs gold spans (new, L1).
- Verification gate: % hallucinations caught at <X% false-block rate (L3).

---

## 9. Risks, compliance, rollback
- **HIPAA / PHI:** all inference models local (medgemma + H100). Cloud models
  only as offline teachers on de-identified or policy-approved data; not on the
  inference path.
- **Silent failure / over-trust:** L1/L3 must emit confidence + provenance;
  low-confidence → fall back to deterministic path or flag, never fabricate.
- **Safety:** treatment-stop / screening decisions stay deterministic
  (`age_guardrail`, status reconciliation). ML informs, rules decide.
- **Rollback:** every ML layer ships behind a flag (mirror `VAUCDA_HPI_V2`),
  with the deterministic path as fallback; per-field promotion gated on gold.
- **Training-data leakage:** keep the gold eval out of training; version both.

---

## 10. Open questions for review
1. PHI policy: may de-identified notes be sent to a cloud teacher for label
   bootstrapping, or must labeling also be fully local?
2. Latency budget at inference for L1 (27B local) + L3 — acceptable per note?
3. Is there an existing labeled corpus (coded problem lists, tumor-registry
   data) we can use to seed L1 beyond synthetic labels?
4. Build vs. buy for clinical NER (fine-tune medgemma vs. licensed clinical-NLP)?
5. Appetite for Phase 1 (architecture) before any ML — recommended, but it
   touches Stage-2 prompt flow.
