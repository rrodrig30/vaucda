export const meta = {
  name: 'l1-teacher-label',
  description: 'Teacher draft-labels L1 narrative segments into the v2 structured schema for urologist review',
  phases: [{ title: 'Label' }],
}

// args = { goldDir, segmentIds: ["<id>", ...] }
const A = typeof args === 'string' ? JSON.parse(args) : args
const goldDir = A.goldDir
const ids = A.segmentIds

// v2 extraction schema (source_quote variant; a deterministic step converts
// quotes -> spans). Mirrors scripts/l1/schema.json.
const GRADE = {
  type: ['object', 'null'], additionalProperties: false,
  properties: {
    system: { type: ['string', 'null'], enum: ['gleason-isup', 'fuhrman', 'who', 'other', null] },
    gleason: { type: ['string', 'null'] },
    grade_group: { type: ['integer', 'null'] },
    nuclear_grade: { type: ['integer', 'null'], description: 'RCC Fuhrman 1-4' },
    who_grade: { type: ['string', 'null'], enum: ['low-grade', 'high-grade', null] },
    bladder_stage: { type: ['string', 'null'], description: 'Ta/T1/CIS/T2/MIBC' },
    value: { type: ['string', 'null'] },
  },
}
const EXTRACT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['primary_context', 'diagnoses', 'treatment_events', 'procedures', 'imaging', 'metastases'],
  properties: {
    primary_context: { type: 'string', enum: ['urologic', 'non_urologic'] },
    diagnoses: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['id', 'category', 'name', 'source_quote'],
        properties: {
          id: { type: 'string', description: "short ref e.g. 'dx1'" },
          category: { type: 'string', enum: ['cancer', 'benign', 'indeterminate'], description: 'cancer=pathology-confirmed; benign=known-benign condition; indeterminate=mass/lesion of unknown pathology (unbiopsied). NEVER benign for an unbiopsied mass.' },
          name: { type: 'string' },
          site: { type: ['string', 'null'] },
          diagnosis_date: { type: ['string', 'null'], description: 'ISO; biopsy-confirmed, NOT earliest PSA date' },
          stage_tnm: { type: ['string', 'null'] },
          grade: GRADE,
          risk: { type: ['string', 'null'] },
          source_quote: { type: 'string' },
        },
      },
    },
    treatment_events: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['modality', 'status', 'source_quote'],
        properties: {
          for_diagnosis: { type: ['string', 'null'], description: 'the diagnoses[].id this treatment targets' },
          modality: { type: 'string', enum: ['prostatectomy', 'radiation', 'brachytherapy', 'focal', 'ADT', 'ARSI', 'chemotherapy', 'radioligand', 'immunotherapy', 'active-surveillance', 'nephrectomy', 'partial-nephrectomy', 'cystectomy', 'TURBT', 'intravesical', 'other'] },
          agent: { type: ['string', 'null'] },
          start_date: { type: ['string', 'null'] },
          end_date: { type: ['string', 'null'] },
          status: { type: 'string', enum: ['started', 'ongoing', 'completed', 'discontinued', 'declined', 'planned'] },
          intent: { type: ['string', 'null'], enum: ['definitive', 'adjuvant', 'neoadjuvant', 'salvage', 'palliative', 'maintenance', null] },
          source_quote: { type: 'string' },
        },
      },
    },
    procedures: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['type', 'source_quote'],
        properties: {
          type: { type: 'string' },
          date: { type: ['string', 'null'], description: 'procedure/collection date, NOT results-notification date' },
          finding: { type: ['string', 'null'] },
          source_quote: { type: 'string' },
        },
      },
    },
    imaging: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['modality', 'source_quote'],
        properties: {
          modality: { type: 'string' },
          date: { type: ['string', 'null'] },
          impression: { type: ['string', 'null'] },
          source_quote: { type: 'string' },
        },
      },
    },
    metastases: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['site', 'source_quote'],
        properties: {
          site: { type: 'string' },
          date: { type: ['string', 'null'] },
          source_quote: { type: 'string' },
        },
      },
    },
  },
}

const PROMPT = (id) => `You are a meticulous urologic-oncology data abstractor creating GOLD-STANDARD training labels. Extract structured clinical facts from ONE narrative note segment.

Segment text file: ${goldDir}/segments/${id}.txt

ALSO read the patient's pathology reference (definitive grades often live here, NOT in the consult narrative):
Surgical pathology file: ${goldDir}/segments/${id}.pathology.txt

Read BOTH files, then extract per the schema. RULES (these encode the exact errors to avoid — follow precisely):

DIAGNOSIS CATEGORY (clinical/benefits-critical):
- category="cancer" only when pathology/biopsy CONFIRMS malignancy (check the SP pathology file).
- category="indeterminate" for a mass/lesion of UNKNOWN pathology (e.g. an UNBIOPSIED renal mass). Name it "renal mass of uncertain significance" (or "... of unknown pathology"). NEVER call an unbiopsied/unconfirmed mass "benign" — that has VA service-connection/benefits implications.
- category="benign" only for conditions KNOWN benign (ED, BPH/LUTS, urolithiasis, simple cyst, stricture).

GRADE — ALWAYS SEARCH THE PATHOLOGY:
- Before leaving a cancer's grade empty, SEARCH the SP pathology file (and the segment) for it — prostate Gleason/Grade Group, RCC Fuhrman nuclear grade, bladder WHO grade. A mass that the pathology proves malignant becomes category="cancer" WITH its grade.
- If no grade information exists anywhere, leave grade null (do not invent one).

PRIMARY CONTEXT:
- Set primary_context = "non_urologic" if this note's primary cancer is NOT urologic (e.g. a lung/colon/breast tumor-board note; VistA downloads all tumor-board notes, not just urologic). For such notes, STILL capture cross-specialty facts relevant to urology (systemic chemotherapy, radiation, recent hospitalization, palliative-care decisions) as treatment_events, but do NOT create a urologic cancer diagnosis. Otherwise "urologic".

DIAGNOSES (one entry per DISTINCT urologic diagnosis — cancers AND benign):
- Include benign urologic diagnoses too: erectile dysfunction, BPH/LUTS, urolithiasis/nephrolithiasis, renal mass, complex renal cyst, hydronephrosis, stricture, etc. (category="benign", grade=null).
- A patient may have MORE THAN ONE cancer (e.g. prostate + RCC) — emit a separate diagnosis for each, with its own id (dx1, dx2, ...).
- diagnosis_date = the BIOPSY-CONFIRMED date for cancers, NOT the earliest elevated-PSA date.
- GRADE is CANCER-SPECIFIC — set grade.system and ONLY the matching fields:
    * prostate    -> system "gleason-isup": gleason ("4+4") + grade_group (MAX core, 1-5)
    * renal (RCC) -> system "fuhrman": nuclear_grade (1-4)   [NOT Gleason]
    * bladder/urothelial -> system "who": who_grade ("low-grade"/"high-grade") AND bladder_stage (Ta/T1/CIS/T2/MIBC) — capture BOTH
    * other -> system "other": value (free text)

TREATMENTS:
- Link each treatment to the cancer it targets via for_diagnosis = that diagnosis's id (e.g. active-surveillance for the RCC, prostatectomy for the prostate cancer). Never list a treatment without its cancer when >1 diagnosis exists.
- Keep the SPECIFIC agent (leuprolide, abiraterone, Lu-177 PSMA, IMRT, BCG) in 'agent' AND the class in 'modality' — never collapse Lu-177 to "radiation" or abiraterone to "chemotherapy". ARSI = abiraterone/enzalutamide/apalutamide/darolutamide. radioligand = Lu-177/Pluvicto.
- If a treatment has a documented date RANGE, fill BOTH start_date and end_date.

PROCEDURES vs IMAGING vs (excluded) LABS/EXAM:
- procedures = INTERVENTIONS ONLY: biopsy, cystoscopy, TURBT, prostatectomy, ablation/cryoablation, stent, ureteroscopy, nephrectomy, etc.
- imaging[] = CT, MRI, US, PET, PSMA-PET, bone scan, x-ray, NM — put ALL imaging here, NEVER in procedures.
- Do NOT put LABS (cultures, 24-hr urine / Urorisk, PSA values) or EXAM findings (DRE) anywhere — they are not L1 facts.
- procedure/imaging date = the PROCEDURE/study date, NOT the results-notification/sign-out/secure-message date.

PROVENANCE: every record needs a verbatim source_quote copied EXACTLY from the segment. Only extract what is explicitly in THIS segment; emit empty arrays when absent. Dates ISO (YYYY[-MM[-DD]]). Return ONLY the structured object.`

const results = await pipeline(
  ids,
  (id) => agent(PROMPT(id), { label: `label:${id}`, phase: 'Label', schema: EXTRACT_SCHEMA })
    .then((draft) => ({ id, ok: !!draft, draft }))
)

const ok = results.filter(Boolean)
return {
  labeled: ok.filter((r) => r.ok).length,
  failed: ok.filter((r) => !r.ok).map((r) => r.id),
  labels: ok.filter((r) => r.ok).map((r) => ({ segment_id: r.id, ...r.draft })),
}
