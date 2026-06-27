export const meta = {
  name: 'l1-teacher-label',
  description: 'Teacher draft-labels L1 narrative segments into the structured extraction schema for urologist review',
  phases: [{ title: 'Label' }],
}

// args = { goldDir, segmentIds: ["<id>", ...] }
const A = typeof args === 'string' ? JSON.parse(args) : args
const goldDir = A.goldDir
const ids = A.segmentIds

// Extraction schema (mirrors schema.json but uses source_quote — a verbatim
// snippet — instead of char offsets, which a deterministic step converts to
// spans far more reliably than an LLM can emit offsets).
const EXTRACT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['diagnosis', 'treatment_events', 'procedures', 'metastases'],
  properties: {
    diagnosis: {
      type: ['object', 'null'], additionalProperties: false,
      required: ['cancer_type', 'source_quote'],
      properties: {
        cancer_type: { type: 'string' },
        diagnosis_date: { type: ['string', 'null'], description: 'ISO; biopsy-confirmed date, NOT earliest elevated-PSA date' },
        gleason: { type: ['string', 'null'] },
        grade_group: { type: ['integer', 'null'], description: 'MAX grade group across cores' },
        stage_tnm: { type: ['string', 'null'] },
        risk: { type: ['string', 'null'], enum: ['low', 'favorable-intermediate', 'unfavorable-intermediate', 'high', 'very-high', null] },
        source_quote: { type: 'string', description: 'verbatim snippet from the segment supporting this' },
      },
    },
    treatment_events: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['modality', 'status', 'source_quote'],
        properties: {
          modality: { type: 'string', enum: ['prostatectomy', 'radiation', 'brachytherapy', 'focal', 'ADT', 'ARSI', 'chemotherapy', 'radioligand', 'immunotherapy', 'active-surveillance', 'nephrectomy', 'cystectomy', 'TURBT', 'other'] },
          agent: { type: ['string', 'null'], description: 'specific drug/technique (leuprolide, abiraterone, Lu-177 PSMA, IMRT) — never collapse into modality' },
          start_date: { type: ['string', 'null'] },
          end_date: { type: ['string', 'null'], description: 'populate when a course range is documented so a START date is never shown as completion' },
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
          date: { type: ['string', 'null'], description: 'PROCEDURE/collection date, NOT the results-notification/sign-out date' },
          finding: { type: ['string', 'null'] },
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

Read that file, then extract per the schema. RULES (these encode the errors the downstream pipeline makes — get them right):
- diagnosis_date = the BIOPSY-CONFIRMED diagnosis date, NOT the earliest elevated-PSA date.
- grade_group = the MAXIMUM grade group across all cores (never a lower/representative core).
- For each treatment: keep the SPECIFIC agent (leuprolide, abiraterone, Lu-177 PSMA, IMRT) in 'agent' AND the class in 'modality' — never collapse Lu-177 to "radiation" or abiraterone to "chemotherapy". ARSI = abiraterone/enzalutamide/apalutamide/darolutamide. radioligand = Lu-177/Pluvicto.
- If a treatment has a documented date RANGE, fill BOTH start_date and end_date (so a start date is never mistaken for completion).
- procedure date = the PROCEDURE/collection date, NOT the results-notification/sign-out/secure-message date.
- Every record needs a verbatim source_quote copied EXACTLY from the segment (used to locate provenance). Only extract what is explicitly in THIS segment; emit empty arrays / null when absent. Do NOT infer beyond the text.

Dates ISO (YYYY, YYYY-MM, or YYYY-MM-DD). Return ONLY the structured object.`

const results = await pipeline(
  ids,
  (id) => agent(PROMPT(id), { label: `label:${id}`, phase: 'Label', schema: EXTRACT_SCHEMA })
    .then((draft) => ({ id, ok: !!draft, draft }))
)

// Return the labels to the caller (the runner writes them to disk).
const ok = results.filter(Boolean)
return {
  labeled: ok.filter((r) => r.ok).length,
  failed: ok.filter((r) => !r.ok).map((r) => r.id),
  labels: ok.filter((r) => r.ok).map((r) => ({ segment_id: r.id, ...r.draft })),
}
